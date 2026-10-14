"""Server-side implementation of the approved Gateway tools (runs in the tools Lambda)."""

import logging
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from claims_investigator import metrics
from claims_investigator.errors import (
    ForbiddenError,
    JobTransitionError,
    ToolArgumentError,
)
from claims_investigator.logging import get_logger, log_event
from claims_investigator.models.api import ClaimSubmission
from claims_investigator.models.findings import SourceType
from claims_investigator.models.jobs import JobRecord, JobStatus
from claims_investigator.models.result import InvestigationResult
from claims_investigator.services.human_review import minimum_review_reasons
from claims_investigator.services.jobs import JobService
from claims_investigator.services.ports import Clock, JobUpdate, ObjectStore, utc_now
from claims_investigator.services.retrieval import RetrievalService
from claims_investigator.storage_keys import report_json_key, report_markdown_key
from claims_investigator.tools import schemas as s

_LOG = get_logger(__name__)
MAX_SUBMISSION_BYTES = 64 * 1024
_REPORT_STATUSES = frozenset({JobStatus.COMPLETED, JobStatus.REVIEW_REQUIRED})


class ToolDispatcher:
    def __init__(
        self,
        jobs: JobService,
        store: ObjectStore,
        retrieval: RetrievalService,
        review_confidence_threshold: float,
        clock: Clock = utc_now,
    ) -> None:
        self._jobs = jobs
        self._store = store
        self._retrieval = retrieval
        self._threshold = review_confidence_threshold
        self._clock = clock
        self._routes: dict[str, Callable[[Mapping[str, Any]], BaseModel]] = {
            s.GET_CLAIM_DOCUMENT_METADATA: self._document_metadata,
            s.GET_POLICY_GUIDANCE: lambda a: self._retrieve(a, SourceType.GUIDANCE),
            s.SEARCH_SIMILAR_CLAIMS: lambda a: self._retrieve(a, SourceType.HISTORICAL_CLAIM),
            s.PERSIST_INVESTIGATION_FINDINGS: self._persist,
            s.UPDATE_JOB_STATUS: self._update_status,
        }

    def dispatch(self, tool_name: str, arguments: Mapping[str, Any]) -> BaseModel:
        route = self._routes.get(tool_name)
        if route is None:
            raise ToolArgumentError("unknown tool")
        return route(arguments)

    def _job(self, request: s.ToolRequest, allowed: frozenset[JobStatus]) -> JobRecord:
        job = self._jobs.get_for_claim(request.claim_id, request.job_id)
        if job.correlation_id != request.correlation_id:
            raise ForbiddenError("correlation_id does not match the job")
        if job.status not in allowed:
            raise JobTransitionError(f"job is {job.status}")
        return job

    def _document_metadata(self, arguments: Mapping[str, Any]) -> BaseModel:
        request = s.DocumentMetadataRequest.model_validate(arguments)
        job = self._job(request, frozenset({JobStatus.PROCESSING}))
        submission = ClaimSubmission.model_validate_json(
            self._store.get_bytes(job.submission_key, MAX_SUBMISSION_BYTES)
        )
        documents = []
        for doc in submission.documents:
            meta = self._store.head(doc.object_key)
            documents.append(
                s.DocumentMetadata(
                    document_id=doc.document_id,
                    document_type=doc.document_type,
                    content_type=doc.content_type,
                    object_key=doc.object_key,
                    present=meta is not None,
                    size_bytes=meta.size_bytes if meta else 0,
                )
            )
        return s.DocumentMetadataResult(documents=documents)

    def _retrieve(self, arguments: Mapping[str, Any], source_type: SourceType) -> BaseModel:
        request = s.RetrievalRequest.model_validate(arguments)
        self._job(request, frozenset({JobStatus.PROCESSING}))
        chunks = self._retrieval.retrieve(request.query, source_type, request.claim_type)
        log_event(_LOG, logging.INFO, "retrieval_completed", hits=len(chunks))
        return s.RetrievalResult(chunks=chunks)

    def _persist(self, arguments: Mapping[str, Any]) -> BaseModel:
        request = s.PersistFindingsRequest.model_validate(arguments)
        json_key = report_json_key(request.claim_id, request.job_id)
        md_key = report_markdown_key(request.claim_id, request.job_id)
        job = self._job(request, frozenset({JobStatus.PROCESSING, *_REPORT_STATUSES}))
        if job.status in _REPORT_STATUSES:
            if job.report_key != json_key:
                raise JobTransitionError(f"job is {job.status}")
            return s.PersistFindingsResult(
                status=job.status, report_key=json_key, report_markdown_key=md_key
            )

        try:
            result = InvestigationResult.model_validate_json(request.result_json)
        except ValidationError as exc:
            raise ToolArgumentError(
                "result_json failed validation",
                tuple(f"{'.'.join(map(str, e['loc']))}: {e['type']}" for e in exc.errors()),
            ) from exc
        if (result.job_id, result.claim_id, result.correlation_id) != (
            job.job_id,
            job.claim_id,
            job.correlation_id,
        ):
            raise ToolArgumentError("result identifiers do not match the job")
        required = minimum_review_reasons(result, self._threshold)
        if required and not result.human_review_required:
            raise ToolArgumentError(
                "result must require human review", tuple(str(r) for r in required)
            )

        self._store.put_bytes(json_key, result.model_dump_json().encode(), "application/json")
        self._store.put_bytes(md_key, request.report_markdown.encode(), "text/markdown")
        now = self._clock()
        self._jobs.transition(
            job.job_id,
            JobStatus.PROCESSING,
            result.status,
            JobUpdate(
                completed_at=now,
                report_key=json_key,
                report_markdown_key=md_key,
                human_review_required=result.human_review_required,
                anomaly_signal_count=len(result.anomaly_signals),
            ),
        )
        metrics.emit(f"Jobs{result.status.title().replace('_', '')}", 1)
        metrics.emit("JobDuration", (now - job.created_at).total_seconds(), "Seconds")
        return s.PersistFindingsResult(
            status=result.status, report_key=json_key, report_markdown_key=md_key
        )

    def _update_status(self, arguments: Mapping[str, Any]) -> BaseModel:
        request = s.UpdateJobStatusRequest.model_validate(arguments)
        job = self._job(request, frozenset(JobStatus))
        if job.status is request.status:
            return s.UpdateJobStatusResult(status=job.status, changed=False)
        now = self._clock()
        if request.status is JobStatus.PROCESSING:
            update = JobUpdate(dispatched_at=now, processing_deadline=request.processing_deadline)
        else:
            update = JobUpdate(completed_at=now, failure_category=request.failure_category)
            metrics.emit("JobsFailed", 1)
        self._jobs.transition(job.job_id, job.status, request.status, update)
        return s.UpdateJobStatusResult(status=request.status, changed=True)
