"""Job status lookup with timeout derivation and owner-only report URLs."""

from datetime import timedelta
from uuid import UUID

from claims_investigator.models.api import JobStatusResponse
from claims_investigator.models.jobs import JobStatus
from claims_investigator.services.jobs import JobService
from claims_investigator.services.ports import Clock, ObjectStore, utc_now

REPORT_STATUSES = frozenset({JobStatus.COMPLETED, JobStatus.REVIEW_REQUIRED})


class StatusService:
    def __init__(
        self,
        jobs: JobService,
        store: ObjectStore,
        report_url_expiry_seconds: int,
        clock: Clock = utc_now,
    ) -> None:
        self._jobs = jobs
        self._store = store
        self._expiry = report_url_expiry_seconds
        self._clock = clock

    def get_status(self, claim_id: str, job_id: UUID, principal: str) -> JobStatusResponse:
        job = self._jobs.expire_if_overdue(self._jobs.get_for_claim(claim_id, job_id))
        report_url = None
        expires_at = None
        if (
            job.status in REPORT_STATUSES
            and job.report_key
            and principal == job.submitter_principal
        ):
            report_url = self._store.presign_get(job.report_key, self._expiry)
            expires_at = self._clock() + timedelta(seconds=self._expiry)
        return JobStatusResponse(
            job_id=job.job_id,
            claim_id=job.claim_id,
            correlation_id=job.correlation_id,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            dispatched_at=job.dispatched_at,
            completed_at=job.completed_at,
            failure_category=job.failure_category,
            human_review_required=job.human_review_required,
            report_location=job.report_key if job.status in REPORT_STATUSES else None,
            report_url=report_url,
            report_url_expires_at=expires_at,
        )
