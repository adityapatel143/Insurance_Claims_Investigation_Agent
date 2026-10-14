"""In-memory fakes for the Protocols in `services/ports.py` (AWS boundaries only)."""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from claims_investigator.errors import RequestValidationError, ToolCallError
from claims_investigator.models.api import ClaimSubmission
from claims_investigator.models.common import ClaimType, DocumentType
from claims_investigator.models.findings import RetrievedChunk, SourceType
from claims_investigator.models.jobs import FailureCategory, JobRecord, JobStatus
from claims_investigator.models.messages import InvestigationMessage, RuntimeInvocation
from claims_investigator.services.jobs import JobService, derive_job_id, request_hash
from claims_investigator.services.ports import (
    JobUpdate,
    MemoryContext,
    ObjectMetadata,
    PresignedPost,
    SearchHit,
)
from claims_investigator.services.retrieval import RetrievalService
from claims_investigator.storage_keys import intake_document_key, submission_key
from claims_investigator.tools import schemas as s
from claims_investigator.tools.dispatcher import ToolDispatcher

FIXTURES = Path(__file__).parent / "fixtures"
PRINCIPAL = "arn:aws:sts::111122223333:assumed-role/example-analyst/session"
CLAIM_ID = "CLM-SYN-0001"
CORRELATION_ID = "corr-synthetic-0001"


class FixedClock:
    def __init__(self, now: datetime | None = None) -> None:
        self.now = now or datetime(2025, 5, 5, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class InMemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.presigned_posts: list[tuple[str, str, int, int]] = []

    def presign_post(
        self, key: str, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedPost:
        self.presigned_posts.append((key, content_type, max_bytes, expires_in))
        return PresignedPost(url="https://example.invalid/upload", fields={"key": key})

    def presign_get(self, key: str, expires_in: int) -> str:
        return f"https://example.invalid/{key}?expires={expires_in}"

    def head(self, key: str) -> ObjectMetadata | None:
        item = self.objects.get(key)
        return ObjectMetadata(key, len(item[0]), item[1]) if item else None

    def get_bytes(self, key: str, max_bytes: int) -> bytes:
        data = self.objects[key][0]
        if len(data) > max_bytes:
            raise RequestValidationError("object exceeds the maximum readable size")
        return data

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def move(self, source_key: str, destination_key: str) -> None:
        self.objects[destination_key] = self.objects.pop(source_key)


class InMemoryJobRepository:
    def __init__(self) -> None:
        self.jobs: dict[UUID, JobRecord] = {}

    def create(self, job: JobRecord) -> bool:
        if job.job_id in self.jobs:
            return False
        self.jobs[job.job_id] = job
        return True

    def get(self, job_id: UUID) -> JobRecord | None:
        return self.jobs.get(job_id)

    def transition(
        self,
        job_id: UUID,
        expected: JobStatus,
        target: JobStatus,
        now: datetime,
        update: JobUpdate,
    ) -> bool:
        job = self.jobs.get(job_id)
        if job is None or job.status is not expected:
            return False
        changes = {f.name: getattr(update, f.name) for f in fields(update)}
        changes = {k: v for k, v in changes.items() if v is not None}
        self.jobs[job_id] = job.model_copy(
            update={**changes, "status": target, "updated_at": now, "dispatch_lease_until": None}
        )
        return True

    def acquire_dispatch_lease(self, job_id: UUID, now: datetime, lease_until: datetime) -> bool:
        job = self.jobs.get(job_id)
        if job is None or job.status is not JobStatus.QUEUED:
            return False
        if job.dispatch_lease_until is not None and job.dispatch_lease_until >= now:
            return False
        self.jobs[job_id] = job.model_copy(update={"dispatch_lease_until": lease_until})
        return True

    def release_dispatch_lease(self, job_id: UUID) -> None:
        if job_id in self.jobs:
            self.jobs[job_id] = self.jobs[job_id].model_copy(update={"dispatch_lease_until": None})

    def record_enqueue(self, job_id: UUID) -> int:
        job = self.jobs[job_id]
        self.jobs[job_id] = job.model_copy(update={"enqueue_count": job.enqueue_count + 1})
        return job.enqueue_count + 1


class FakeQueue:
    def __init__(self, fail: bool = False) -> None:
        self.messages: list[InvestigationMessage] = []
        self.fail = fail

    def send(self, message: InvestigationMessage) -> str:
        if self.fail:
            raise RuntimeError("queue unavailable")
        self.messages.append(message)
        return f"msg-{len(self.messages)}"


class FakeInvoker:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, RuntimeInvocation]] = []
        self.error = error

    def invoke(self, session_id: str, payload: RuntimeInvocation) -> None:
        self.calls.append((session_id, payload))
        if self.error:
            raise self.error


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.1, 0.2, 0.3]


class FakeVectorSearch:
    def __init__(self, hits: Sequence[SearchHit] = ()) -> None:
        self.hits = list(hits)
        self.calls: list[tuple[str, SourceType, ClaimType, int]] = []

    def hybrid_search(
        self,
        query_text: str,
        query_vector: Sequence[float],
        source_type: SourceType,
        claim_type: ClaimType,
        top_k: int,
    ) -> list[SearchHit]:
        self.calls.append((query_text, source_type, claim_type, top_k))
        return [h for h in self.hits if h.source_type is source_type][:top_k]


class FakeMemoryStore:
    def __init__(self, error: Exception | None = None) -> None:
        self.summaries: list[tuple[str, str, str]] = []
        self.error = error

    def load(self, actor_id: str, session_id: str) -> MemoryContext:
        if self.error:
            raise self.error
        return MemoryContext(preferences=["prefers concise reports"])

    def save_session_summary(self, actor_id: str, session_id: str, summary: str) -> None:
        if self.error:
            raise self.error
        self.summaries.append((actor_id, session_id, summary))


Response = BaseModel | Exception | Callable[[str], BaseModel]


class FakeStructuredModel:
    """Returns a configured response per output model name, or raises a configured error."""

    def __init__(self, responses: dict[str, Response]) -> None:
        self.responses = responses
        self.prompts: list[tuple[str, str]] = []

    def generate[T: BaseModel](
        self, system_prompt: str, prompt: str, output_model: type[T], cancel: Event
    ) -> T:
        self.prompts.append((output_model.__name__, prompt))
        response = self.responses[output_model.__name__]
        if isinstance(response, Exception):
            raise response
        value = response if isinstance(response, BaseModel) else response(prompt)
        assert isinstance(value, output_model)
        return value


def hit(
    chunk_id: str, source_type: SourceType = SourceType.GUIDANCE, score: float = 1.0
) -> SearchHit:
    return SearchHit(
        document_id=chunk_id.split("#", 1)[0],
        chunk_id=chunk_id,
        source_type=source_type,
        source_uri=f"s3://example-bucket/sample-data/{chunk_id}.md",
        title=f"Synthetic {chunk_id}",
        text=f"SYNTHETIC guidance text for {chunk_id}. Verify repair estimates against invoices.",
        score=score,
    )


@dataclass
class DocSpec:
    document_type: DocumentType
    file_name: str
    content_type: str
    body: bytes
    document_id: UUID = field(default_factory=uuid4)


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / "documents" / name).read_bytes()


def standard_docs() -> list[DocSpec]:
    return [
        DocSpec(
            DocumentType.CLAIM_FORM, "claim_form.txt", "text/plain", fixture_bytes("claim_form.txt")
        ),
        DocSpec(
            DocumentType.REPAIR_ESTIMATE,
            "repair_estimate.csv",
            "text/csv",
            fixture_bytes("repair_estimate.csv"),
        ),
        DocSpec(
            DocumentType.INCIDENT_REPORT,
            "incident_report.json",
            "application/json",
            fixture_bytes("incident_report.json"),
        ),
    ]


def make_submission(docs: Sequence[DocSpec] | None = None, **overrides: Any) -> ClaimSubmission:
    docs = standard_docs() if docs is None else docs
    data: dict[str, Any] = {
        "client_request_id": "0b9a6c1e-2f3d-4e5f-8a7b-9c0d1e2f3a4b",
        "claim_id": CLAIM_ID,
        "policy_reference": "POL-SYN-1001",
        "claim_type": "AUTO",
        "incident_date": "2025-05-02",
        "reported_date": "2025-05-04",
        "claimed_amount": "1250.00",
        "currency": "USD",
        "incident_description": "SYNTHETIC: low-speed collision in a car park damaged the bumper.",
        "documents": [
            {
                "document_id": str(d.document_id),
                "object_key": intake_document_key(CLAIM_ID, d.document_id, d.file_name),
                "document_type": d.document_type.value,
                "content_type": d.content_type,
            }
            for d in docs
        ],
    }
    data.update(overrides)
    return ClaimSubmission.model_validate(data)


def upload_docs(store: InMemoryObjectStore, docs: Sequence[DocSpec]) -> None:
    for d in docs:
        key = intake_document_key(CLAIM_ID, d.document_id, d.file_name)
        store.put_bytes(key, d.body, d.content_type)


def make_job(
    submission: ClaimSubmission,
    clock: FixedClock,
    status: JobStatus = JobStatus.QUEUED,
    **overrides: Any,
) -> JobRecord:
    job_id = derive_job_id(PRINCIPAL, submission.claim_id, submission.client_request_id)
    data: dict[str, Any] = {
        "job_id": job_id,
        "claim_id": submission.claim_id,
        "correlation_id": CORRELATION_ID,
        "status": status,
        "request_hash": request_hash(submission),
        "submitter_principal": PRINCIPAL,
        "submission_key": submission_key(submission.claim_id, job_id),
        "document_count": len(submission.documents),
        "created_at": clock(),
        "updated_at": clock(),
    }
    data.update(overrides)
    return JobRecord.model_validate(data)


def make_message(job: JobRecord, submission: ClaimSubmission) -> InvestigationMessage:
    return InvestigationMessage(
        job_id=job.job_id,
        claim_id=job.claim_id,
        correlation_id=job.correlation_id,
        submission_key=job.submission_key,
        document_references=submission.documents,
        submitted_at=job.created_at,
    )


class DispatcherBackedTools:
    """`InvestigationTools` implemented by calling the real tools dispatcher in-process."""

    def __init__(
        self, dispatcher: ToolDispatcher, before_call: Callable[[str], None] | None = None
    ):
        self.dispatcher = dispatcher
        self.calls: list[str] = []
        self.before_call = before_call

    def _call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(tool)
        try:
            if self.before_call:
                self.before_call(tool)
            result = self.dispatcher.dispatch(tool, json.loads(json.dumps(arguments)))
        except Exception as exc:
            raise ToolCallError(f"{tool} failed") from exc
        return result.model_dump(mode="json")

    @staticmethod
    def _ids(request: s.ToolRequest) -> dict[str, Any]:
        return request.model_dump(mode="json")

    def mark_processing(self, request: s.ToolRequest, deadline: datetime) -> None:
        args = {**self._ids(request), "status": "PROCESSING"}
        self._call(s.UPDATE_JOB_STATUS, {**args, "processing_deadline": deadline.isoformat()})

    def mark_failed(self, request: s.ToolRequest, category: FailureCategory) -> None:
        args = {**self._ids(request), "status": "FAILED", "failure_category": str(category)}
        self._call(s.UPDATE_JOB_STATUS, args)

    def get_claim_document_metadata(self, request: s.ToolRequest) -> list[s.DocumentMetadata]:
        data = self._call(s.GET_CLAIM_DOCUMENT_METADATA, self._ids(request))
        return s.DocumentMetadataResult.model_validate(data).documents

    def get_policy_guidance(
        self, request: s.ToolRequest, claim_type: ClaimType, query: str
    ) -> list[RetrievedChunk]:
        args = {**self._ids(request), "claim_type": str(claim_type), "query": query}
        return s.RetrievalResult.model_validate(self._call(s.GET_POLICY_GUIDANCE, args)).chunks

    def search_similar_claims(
        self, request: s.ToolRequest, claim_type: ClaimType, query: str
    ) -> list[RetrievedChunk]:
        args = {**self._ids(request), "claim_type": str(claim_type), "query": query}
        return s.RetrievalResult.model_validate(self._call(s.SEARCH_SIMILAR_CLAIMS, args)).chunks

    def persist_investigation_findings(
        self, request: s.ToolRequest, result_json: str, report_markdown: str
    ) -> s.PersistFindingsResult:
        args = {
            **self._ids(request),
            "result_json": result_json,
            "report_markdown": report_markdown,
        }
        return s.PersistFindingsResult.model_validate(
            self._call(s.PERSIST_INVESTIGATION_FINDINGS, args)
        )


@dataclass
class World:
    """A wired set of fakes for service-level and pipeline tests."""

    clock: FixedClock = field(default_factory=FixedClock)
    store: InMemoryObjectStore = field(default_factory=InMemoryObjectStore)
    repo: InMemoryJobRepository = field(default_factory=InMemoryJobRepository)
    search: FakeVectorSearch = field(
        default_factory=lambda: FakeVectorSearch(
            [
                hit("guidance-auto-001#c0"),
                hit("historical-auto-007#c0", SourceType.HISTORICAL_CLAIM),
            ]
        )
    )

    @property
    def jobs(self) -> JobService:
        return JobService(self.repo, self.clock)

    def dispatcher(self, threshold: float = 0.7) -> ToolDispatcher:
        retrieval = RetrievalService(self.search, FakeEmbedder(), top_k=5)
        return ToolDispatcher(self.jobs, self.store, retrieval, threshold, self.clock)

    def seed_job(
        self,
        docs: Sequence[DocSpec] | None = None,
        status: JobStatus = JobStatus.QUEUED,
        **overrides: Any,
    ) -> tuple[ClaimSubmission, JobRecord]:
        docs = standard_docs() if docs is None else docs
        submission = make_submission(docs, **overrides)
        upload_docs(self.store, docs)
        job = make_job(submission, self.clock, status)
        self.repo.create(job)
        self.store.put_bytes(
            job.submission_key, submission.model_dump_json().encode(), "application/json"
        )
        return submission, job

    def invocation(
        self, job: JobRecord, submission: ClaimSubmission, deadline_s: float = 1800
    ) -> RuntimeInvocation:
        return RuntimeInvocation(
            job_id=job.job_id,
            claim_id=job.claim_id,
            correlation_id=job.correlation_id,
            submission_key=job.submission_key,
            document_references=submission.documents,
            actor_id="a" * 64,
            processing_deadline=self.clock() + timedelta(seconds=deadline_s),
        )


def with_status(job: JobRecord, status: JobStatus, **changes: Any) -> JobRecord:
    return job.model_copy(update={"status": status, **changes})
