"""Job identity, lookup, and guarded status transitions."""

import hashlib
from datetime import datetime
from uuid import UUID, uuid5

from claims_investigator import metrics
from claims_investigator.errors import JobTransitionError, NotFoundError
from claims_investigator.models.api import ClaimSubmission
from claims_investigator.models.jobs import (
    FailureCategory,
    JobRecord,
    JobStatus,
    can_transition,
)
from claims_investigator.services.ports import Clock, JobRepository, JobUpdate, utc_now

JOB_ID_NAMESPACE = UUID("6f7c1a52-3f0e-4d8e-9a57-2b8f0d4c9e11")


def derive_job_id(principal: str, claim_id: str, client_request_id: UUID) -> UUID:
    return uuid5(JOB_ID_NAMESPACE, f"{principal}|{claim_id}|{client_request_id}")


def request_hash(submission: ClaimSubmission) -> str:
    return hashlib.sha256(submission.model_dump_json().encode()).hexdigest()


def runtime_session_id(job_id: UUID) -> str:
    return f"claims-job-{job_id}"


class JobService:
    def __init__(self, repository: JobRepository, clock: Clock = utc_now) -> None:
        self._repo = repository
        self._clock = clock

    def create(self, job: JobRecord) -> bool:
        return self._repo.create(job)

    def get(self, job_id: UUID) -> JobRecord | None:
        return self._repo.get(job_id)

    def record_enqueue(self, job_id: UUID) -> int:
        return self._repo.record_enqueue(job_id)

    def get_for_claim(self, claim_id: str, job_id: UUID) -> JobRecord:
        job = self._repo.get(job_id)
        if job is None or job.claim_id != claim_id:
            raise NotFoundError("job not found")
        return job

    def transition(
        self, job_id: UUID, expected: JobStatus, target: JobStatus, update: JobUpdate
    ) -> None:
        if not can_transition(expected, target):
            raise JobTransitionError(f"transition {expected} -> {target} is not allowed")
        if not self._repo.transition(job_id, expected, target, self._clock(), update):
            raise JobTransitionError(f"job is no longer {expected}")

    def expire_if_overdue(self, job: JobRecord) -> JobRecord:
        """Fail a PROCESSING job whose deadline has passed; no background sweeper is needed."""
        now = self._clock()
        if job.status is not JobStatus.PROCESSING or not _is_past(job.processing_deadline, now):
            return job
        if self._repo.transition(
            job.job_id,
            JobStatus.PROCESSING,
            JobStatus.FAILED,
            now,
            JobUpdate(completed_at=now, failure_category=FailureCategory.TIMEOUT),
        ):
            metrics.emit("JobsFailed", 1)
        return self._repo.get(job.job_id) or job


def _is_past(deadline: datetime | None, now: datetime) -> bool:
    return deadline is not None and deadline < now
