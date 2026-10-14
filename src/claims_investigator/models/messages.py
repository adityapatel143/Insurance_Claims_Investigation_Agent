"""Versioned SQS message and AgentCore Runtime invocation payload."""

from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from claims_investigator.models.api import MAX_DOCUMENTS_PER_CLAIM, DocumentReference
from claims_investigator.models.common import ClaimId, CorrelationId, JobId

MESSAGE_SCHEMA_VERSION: Final = "1.0"
ActorId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = MESSAGE_SCHEMA_VERSION
    job_id: JobId
    claim_id: ClaimId
    correlation_id: CorrelationId
    submission_key: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    document_references: Annotated[
        list[DocumentReference], Field(min_length=1, max_length=MAX_DOCUMENTS_PER_CLAIM)
    ]


class InvestigationMessage(_Envelope):
    """Body of the SQS investigation message; `attempt` counts client-triggered sends."""

    submitted_at: AwareDatetime
    attempt: Annotated[int, Field(ge=1)] = 1


class RuntimeInvocation(_Envelope):
    """Payload sent to AgentCore Runtime by the orchestrator."""

    actor_id: ActorId
    processing_deadline: AwareDatetime
