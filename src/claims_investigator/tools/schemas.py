"""Gateway tool contracts: Pydantic models enforce what the Gateway schema subset cannot express."""

import json
from importlib import resources
from typing import Annotated, Any, Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from claims_investigator.models.common import (
    ClaimId,
    ClaimType,
    CorrelationId,
    DocumentId,
    DocumentType,
    JobId,
)
from claims_investigator.models.findings import RetrievedChunk
from claims_investigator.models.jobs import FailureCategory, JobStatus

GET_CLAIM_DOCUMENT_METADATA: Final = "get_claim_document_metadata"
GET_POLICY_GUIDANCE: Final = "get_policy_guidance"
SEARCH_SIMILAR_CLAIMS: Final = "search_similar_claims"
PERSIST_INVESTIGATION_FINDINGS: Final = "persist_investigation_findings"
UPDATE_JOB_STATUS: Final = "update_job_status"
TOOL_NAMES: Final = frozenset(
    {
        GET_CLAIM_DOCUMENT_METADATA,
        GET_POLICY_GUIDANCE,
        SEARCH_SIMILAR_CLAIMS,
        PERSIST_INVESTIGATION_FINDINGS,
        UPDATE_JOB_STATUS,
    }
)
MAX_REPORT_CHARS = 1_000_000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolRequest(_Strict):
    job_id: JobId
    claim_id: ClaimId
    correlation_id: CorrelationId


class DocumentMetadataRequest(ToolRequest):
    pass


class DocumentMetadata(_Strict):
    document_id: DocumentId
    document_type: DocumentType
    content_type: str
    object_key: str
    present: bool
    size_bytes: Annotated[int, Field(ge=0)] = 0


class DocumentMetadataResult(_Strict):
    documents: list[DocumentMetadata]


class RetrievalRequest(ToolRequest):
    claim_type: ClaimType
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class RetrievalResult(_Strict):
    chunks: list[RetrievedChunk]


class PersistFindingsRequest(ToolRequest):
    result_json: Annotated[str, StringConstraints(min_length=2, max_length=MAX_REPORT_CHARS)]
    report_markdown: Annotated[str, StringConstraints(min_length=1, max_length=MAX_REPORT_CHARS)]


class PersistFindingsResult(_Strict):
    status: JobStatus
    report_key: str
    report_markdown_key: str


class UpdateJobStatusRequest(ToolRequest):
    status: Literal[JobStatus.PROCESSING, JobStatus.FAILED]
    failure_category: FailureCategory | None = None
    processing_deadline: AwareDatetime | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.status is JobStatus.FAILED) != (self.failure_category is not None):
            raise ValueError("failure_category is required exactly when status is FAILED")
        return self


class UpdateJobStatusResult(_Strict):
    status: JobStatus
    changed: bool


class ToolError(_Strict):
    code: str
    message: str


class ToolEnvelope(_Strict):
    """Uniform Lambda response so the runtime can distinguish tool errors from transport errors."""

    ok: bool
    result: dict[str, Any] | None = None
    error: ToolError | None = None


def tool_definitions() -> list[dict[str, Any]]:
    """Gateway tool definitions (also consumed by Terraform); must stay in sync with the models."""
    text = resources.files(__package__).joinpath("tool_definitions.json").read_text("utf-8")
    definitions: list[dict[str, Any]] = json.loads(text)
    return definitions
