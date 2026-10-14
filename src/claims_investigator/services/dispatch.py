"""Orchestrator dispatch: lease the job, invoke AgentCore Runtime, record PROCESSING."""

import logging
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from uuid import UUID

from claims_investigator import metrics
from claims_investigator.errors import JobTransitionError
from claims_investigator.logging import get_logger, log_event
from claims_investigator.models.jobs import FailureCategory, JobStatus
from claims_investigator.models.messages import InvestigationMessage, RuntimeInvocation
from claims_investigator.services.jobs import JobService, runtime_session_id
from claims_investigator.services.memory import actor_id_for
from claims_investigator.services.ports import (
    AgentRuntimeInvoker,
    Clock,
    JobRepository,
    JobUpdate,
    utc_now,
)

_LOG = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DispatchPolicy:
    lease_seconds: int
    investigation_timeout_seconds: int
    max_receive_count: int


class DispatchOutcome(StrEnum):
    DISPATCHED = "DISPATCHED"
    SKIPPED = "SKIPPED"


class DispatchService:
    def __init__(
        self,
        jobs: JobService,
        repository: JobRepository,
        invoker: AgentRuntimeInvoker,
        policy: DispatchPolicy,
        clock: Clock = utc_now,
    ) -> None:
        self._jobs = jobs
        self._repo = repository
        self._invoker = invoker
        self._policy = policy
        self._clock = clock

    def dispatch(self, message: InvestigationMessage, receive_count: int) -> DispatchOutcome:
        """Return SKIPPED for duplicates; raise to have SQS redeliver (then DLQ)."""
        job = self._jobs.get(message.job_id)
        if job is None or job.claim_id != message.claim_id:
            log_event(_LOG, logging.WARNING, "dispatch_skipped_unknown_job")
            return DispatchOutcome.SKIPPED
        if job.status is not JobStatus.QUEUED:
            log_event(_LOG, logging.INFO, "dispatch_skipped_status", status=str(job.status))
            return DispatchOutcome.SKIPPED

        now = self._clock()
        if not self._repo.acquire_dispatch_lease(
            job.job_id, now, now + timedelta(seconds=self._policy.lease_seconds)
        ):
            log_event(_LOG, logging.INFO, "dispatch_skipped_lease_held")
            return DispatchOutcome.SKIPPED

        deadline = now + timedelta(seconds=self._policy.investigation_timeout_seconds)
        payload = RuntimeInvocation(
            job_id=job.job_id,
            claim_id=job.claim_id,
            correlation_id=job.correlation_id,
            submission_key=job.submission_key,
            document_references=message.document_references,
            actor_id=actor_id_for(job.submitter_principal),
            processing_deadline=deadline,
        )
        try:
            self._invoker.invoke(runtime_session_id(job.job_id), payload)
        except Exception:
            self._repo.release_dispatch_lease(job.job_id)
            if receive_count >= self._policy.max_receive_count:
                self._fail_exhausted(job.job_id)
            raise

        try:
            self._jobs.transition(
                job.job_id,
                JobStatus.QUEUED,
                JobStatus.PROCESSING,
                JobUpdate(dispatched_at=now, processing_deadline=deadline),
            )
        except JobTransitionError:
            # The runtime may already have recorded PROCESSING through the Gateway tool.
            log_event(_LOG, logging.INFO, "dispatch_status_already_advanced")
        return DispatchOutcome.DISPATCHED

    def _fail_exhausted(self, job_id: UUID) -> None:
        try:
            self._jobs.transition(
                job_id,
                JobStatus.QUEUED,
                JobStatus.FAILED,
                JobUpdate(
                    completed_at=self._clock(),
                    failure_category=FailureCategory.DISPATCH_EXHAUSTED,
                ),
            )
            metrics.emit("JobsFailed", 1)
        except JobTransitionError:
            log_event(_LOG, logging.WARNING, "dispatch_fail_transition_skipped")
