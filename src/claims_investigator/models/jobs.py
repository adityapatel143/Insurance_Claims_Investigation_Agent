"""Job lifecycle types shared by the API, orchestrator, tools, and runtime."""

from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from claims_investigator.models.common import ClaimId, CorrelationId, JobId


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_STATUSES


TERMINAL_STATUSES = frozenset({JobStatus.COMPLETED, JobStatus.REVIEW_REQUIRED, JobStatus.FAILED})

ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.PROCESSING, JobStatus.FAILED}),
    JobStatus.PROCESSING: frozenset(
        {JobStatus.COMPLETED, JobStatus.REVIEW_REQUIRED, JobStatus.FAILED}
    ),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.REVIEW_REQUIRED: frozenset(),
    JobStatus.FAILED: frozenset(),
}


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


class FailureCategory(StrEnum):
    DISPATCH_EXHAUSTED = "DISPATCH_EXHAUSTED"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIMEOUT = "TIMEOUT"
    TOOL_ERROR = "TOOL_ERROR"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL = "INTERNAL"


class JobRecord(BaseModel):
    """DynamoDB job item; holds identifiers and pointers only, never claim content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: JobId
    claim_id: ClaimId
    correlation_id: CorrelationId
    status: JobStatus
    request_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    submitter_principal: Annotated[str, Field(min_length=1, max_length=2048)]
    submission_key: Annotated[str, Field(min_length=1, max_length=1024)]
    document_count: Annotated[int, Field(ge=1)]
    enqueue_count: Annotated[int, Field(ge=0)] = 0
    created_at: AwareDatetime
    updated_at: AwareDatetime
    dispatch_lease_until: AwareDatetime | None = None
    dispatched_at: AwareDatetime | None = None
    processing_deadline: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    failure_category: FailureCategory | None = None
    report_key: str | None = None
    report_markdown_key: str | None = None
    human_review_required: bool | None = None
    anomaly_signal_count: Annotated[int, Field(ge=0)] | None = None
    expires_at: Annotated[int, Field(ge=0)] | None = None
