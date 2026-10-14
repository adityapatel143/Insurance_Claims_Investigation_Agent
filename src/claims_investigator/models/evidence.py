"""Evidence extracted from claim artifacts; every item is addressable by an evidence ID."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from claims_investigator.models.common import (
    ClaimId,
    DocumentId,
    DocumentType,
    EvidenceId,
    JobId,
)

FieldName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=300)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceSource(StrEnum):
    CLAIM_DOCUMENT = "CLAIM_DOCUMENT"
    CLAIM_METADATA = "CLAIM_METADATA"


class EvidenceReference(_Model):
    evidence_id: EvidenceId
    source: EvidenceSource
    document_id: DocumentId | None = None
    locator: ShortText
    description: ShortText


class ExtractedField(_Model):
    name: FieldName
    value: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    evidence_id: EvidenceId


class NormalizedDocument(_Model):
    document_id: DocumentId
    document_type: DocumentType
    content_type: str
    source_key: str
    normalized_key: str | None = None
    extraction_status: Literal["EXTRACTED", "EMPTY", "UNSUPPORTED", "FAILED"]
    line_count: Annotated[int, Field(ge=0)] = 0
    fields: list[ExtractedField] = Field(default_factory=list)


class MissingInformation(_Model):
    item: ShortText
    reason: ShortText
    related_evidence_ids: list[EvidenceId] = Field(default_factory=list)


class FieldInconsistency(_Model):
    field: FieldName
    observed_values: Annotated[list[str], Field(min_length=2)]
    evidence_ids: Annotated[list[EvidenceId], Field(min_length=2)]


class EvidenceBundle(_Model):
    claim_id: ClaimId
    job_id: JobId
    documents: list[NormalizedDocument]
    references: list[EvidenceReference]
    fields: list[ExtractedField] = Field(default_factory=list)
    missing_information: list[MissingInformation] = Field(default_factory=list)
    inconsistencies: list[FieldInconsistency] = Field(default_factory=list)

    @property
    def evidence_ids(self) -> frozenset[str]:
        return frozenset(ref.evidence_id for ref in self.references)
