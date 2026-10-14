"""Investigation findings: anomaly signals, risk indicators, sources, and analyst actions."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from claims_investigator.models.common import (
    AdvisoryText,
    Confidence,
    EvidenceId,
    ShortAdvisoryText,
)

Code = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")]
EvidenceRefs = Annotated[list[EvidenceId], Field(min_length=1, max_length=50)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Level(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AnomalySignal(_Model):
    """A potential anomaly signal that requires review; never a fraud determination."""

    code: Code
    description: AdvisoryText
    evidence_refs: EvidenceRefs
    confidence: Confidence
    limitations: list[ShortAdvisoryText] = Field(default_factory=list)
    origin: Literal["RULE", "MODEL"]


class RiskIndicator(_Model):
    category: Code
    level: Level
    rationale: AdvisoryText
    basis: Literal["EVIDENCE", "INFERENCE", "MISSING_INFORMATION"]
    evidence_refs: EvidenceRefs
    confidence: Confidence


class SourceType(StrEnum):
    GUIDANCE = "GUIDANCE"
    HISTORICAL_CLAIM = "HISTORICAL_CLAIM"


class RetrievedSource(_Model):
    source_id: EvidenceId
    document_id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    chunk_id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    source_type: SourceType
    source_uri: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    title: Annotated[str, StringConstraints(max_length=300)] = ""
    score: Annotated[float, Field(ge=0.0)]
    retrieval_method: Literal["HYBRID", "VECTOR", "LEXICAL"]


class RetrievedChunk(_Model):
    """A retrieved source plus its text; the text is untrusted and never persisted in results."""

    source: RetrievedSource
    text: Annotated[str, StringConstraints(min_length=1, max_length=8000)]


class AnalystAction(_Model):
    action: ShortAdvisoryText
    rationale: AdvisoryText
    priority: Level
    evidence_refs: EvidenceRefs
