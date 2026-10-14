"""Claim intake: document validation, quarantine, idempotent job creation, and enqueue."""

from collections.abc import Sequence
from datetime import timedelta

from claims_investigator.errors import (
    DependencyUnavailableError,
    DocumentRejectedError,
    IdempotencyConflictError,
)
from claims_investigator.models.api import ClaimAccepted, ClaimSubmission, DocumentReference
from claims_investigator.models.jobs import JobRecord, JobStatus
from claims_investigator.models.messages import InvestigationMessage
from claims_investigator.services.jobs import JobService, derive_job_id, request_hash
from claims_investigator.services.ports import Clock, ObjectStore, QueuePublisher, utc_now
from claims_investigator.services.uploads import UploadPolicy
from claims_investigator.storage_keys import quarantine_key, submission_key

NOT_FOUND = "object not found"


def status_path(claim_id: str, job_id: object) -> str:
    return f"/claims/{claim_id}/jobs/{job_id}"


class IntakeService:
    def __init__(
        self,
        store: ObjectStore,
        jobs: JobService,
        queue: QueuePublisher,
        policy: UploadPolicy,
        *,
        job_ttl_days: int = 0,
        clock: Clock = utc_now,
    ) -> None:
        self._store = store
        self._jobs = jobs
        self._queue = queue
        self._policy = policy
        self._job_ttl_days = job_ttl_days
        self._clock = clock

    def submit(
        self, submission: ClaimSubmission, principal: str, correlation_id: str
    ) -> ClaimAccepted:
        self._validate_documents(submission.documents)
        job_id = derive_job_id(principal, submission.claim_id, submission.client_request_id)
        digest = request_hash(submission)

        existing = self._jobs.get(job_id)
        if existing is not None:
            return self._replay(existing, digest, submission.documents)

        now = self._clock()
        key = submission_key(submission.claim_id, job_id)
        self._store.put_bytes(key, submission.model_dump_json().encode(), "application/json")
        job = JobRecord(
            job_id=job_id,
            claim_id=submission.claim_id,
            correlation_id=correlation_id,
            status=JobStatus.QUEUED,
            request_hash=digest,
            submitter_principal=principal,
            submission_key=key,
            document_count=len(submission.documents),
            created_at=now,
            updated_at=now,
            expires_at=self._expiry_epoch(now.timestamp()),
        )
        if not self._jobs.create(job):
            raced = self._jobs.get(job_id)
            if raced is None:
                raise DependencyUnavailableError("job creation raced and could not be read back")
            return self._replay(raced, digest, submission.documents)
        self._enqueue(job, submission.documents)
        return _accepted(job)

    def _replay(
        self, job: JobRecord, digest: str, documents: Sequence[DocumentReference]
    ) -> ClaimAccepted:
        if job.request_hash != digest:
            raise IdempotencyConflictError("client_request_id was reused with a different request")
        if job.status is JobStatus.QUEUED:
            self._enqueue(job, documents)
        return _accepted(job)

    def _enqueue(self, job: JobRecord, documents: Sequence[DocumentReference]) -> None:
        attempt = self._jobs.record_enqueue(job.job_id)
        self._queue.send(
            InvestigationMessage(
                job_id=job.job_id,
                claim_id=job.claim_id,
                correlation_id=job.correlation_id,
                submission_key=job.submission_key,
                document_references=list(documents),
                submitted_at=job.created_at,
                attempt=attempt,
            )
        )

    def _validate_documents(self, documents: Sequence[DocumentReference]) -> None:
        problems: list[str] = []
        for doc in documents:
            reason = self._rejection_reason(doc)
            if reason is None:
                continue
            problems.append(f"{doc.document_id}: {reason}")
            if reason != NOT_FOUND:
                self._store.move(doc.object_key, quarantine_key(doc.object_key))
        if problems:
            raise DocumentRejectedError("one or more documents were rejected", tuple(problems))

    def _rejection_reason(self, doc: DocumentReference) -> str | None:
        if doc.content_type not in self._policy.allowed_content_types:
            return "declared content type not allowed"
        meta = self._store.head(doc.object_key)
        if meta is None:
            return NOT_FOUND
        if not 0 < meta.size_bytes <= self._policy.max_upload_bytes:
            return "object size outside allowed range"
        if meta.content_type.split(";")[0].strip().lower() != doc.content_type:
            return "stored content type does not match declared type"
        return None

    def _expiry_epoch(self, now_epoch: float) -> int | None:
        if self._job_ttl_days <= 0:
            return None
        return int(now_epoch + timedelta(days=self._job_ttl_days).total_seconds())


def _accepted(job: JobRecord) -> ClaimAccepted:
    return ClaimAccepted(
        job_id=job.job_id,
        claim_id=job.claim_id,
        correlation_id=job.correlation_id,
        status=job.status,
        status_url=status_path(job.claim_id, job.job_id),
    )
