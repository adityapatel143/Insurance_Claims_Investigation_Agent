"""HTTP API request and response models."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from claims_investigator.models.common import (
    ClaimId,
    ClaimType,
    CorrelationId,
    DocumentId,
    DocumentType,
    FileName,
    JobId,
)
from claims_investigator.models.jobs import FailureCategory, JobStatus
from claims_investigator.storage_keys import intake_document_prefix

# Lower-case before the pattern check; StringConstraints applies `pattern` to the raw input.
ContentType = Annotated[
    str,
    BeforeValidator(lambda v: v.strip().lower() if isinstance(v, str) else v),
    StringConstraints(pattern=r"^[a-z]+/[a-z0-9.+-]+$", max_length=100),
]
MAX_DOCUMENTS_PER_CLAIM = 20


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class UploadRequest(_Request):
    claim_id: ClaimId
    file_name: FileName
    content_type: ContentType


class UploadResponse(BaseModel):
    claim_id: ClaimId
    document_id: DocumentId
    object_key: str
    upload_url: str
    upload_fields: dict[str, str]
    content_type: str
    max_size_bytes: int
    expires_at: AwareDatetime


class DocumentReference(_Request):
    document_id: DocumentId
    object_key: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    document_type: DocumentType
    content_type: ContentType


class ClaimSubmission(_Request):
    client_request_id: UUID
    claim_id: ClaimId
    policy_reference: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9-]{3,31}$")]
    claim_type: ClaimType
    incident_date: date
    reported_date: date
    claimed_amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    incident_description: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    documents: Annotated[
        list[DocumentReference], Field(min_length=1, max_length=MAX_DOCUMENTS_PER_CLAIM)
    ]

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        today = datetime.now(UTC).date()
        if self.incident_date > today or self.reported_date > today:
            raise ValueError("dates must not be in the future")
        ids = [doc.document_id for doc in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("document_id values must be unique")
        for doc in self.documents:
            prefix = intake_document_prefix(self.claim_id, doc.document_id)
            name = doc.object_key.removeprefix(prefix)
            if not doc.object_key.startswith(prefix) or not name or "/" in name:
                raise ValueError(f"object_key must be {prefix}<file_name>")
        return self


class JobStatusPath(_Request):
    claim_id: ClaimId
    job_id: JobId


class ClaimAccepted(BaseModel):
    job_id: JobId
    claim_id: ClaimId
    correlation_id: CorrelationId
    status: JobStatus
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: JobId
    claim_id: ClaimId
    correlation_id: CorrelationId
    status: JobStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
    dispatched_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    failure_category: FailureCategory | None = None
    human_review_required: bool | None = None
    report_location: str | None = None
    report_url: str | None = None
    report_url_expires_at: AwareDatetime | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    correlation_id: CorrelationId | None = None
    details: list[str] = Field(default_factory=list)
