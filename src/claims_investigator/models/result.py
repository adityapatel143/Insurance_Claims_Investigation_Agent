"""Versioned investigation result persisted to `reports/` and summarized in DynamoDB."""

from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from claims_investigator.models.common import (
    AdvisoryText,
    ClaimId,
    Confidence,
    CorrelationId,
    JobId,
)
from claims_investigator.models.evidence import EvidenceReference, MissingInformation
from claims_investigator.models.findings import (
    AnalystAction,
    AnomalySignal,
    RetrievedSource,
    RiskIndicator,
)
from claims_investigator.models.jobs import JobStatus

RESULT_SCHEMA_VERSION: Final = "1.0"
ADVISORY_NOTICE: Final = (
    "Advisory investigation support only. This report does not approve, reject, price, or pay "
    "a claim and does not determine eligibility. "
    "A licensed claims analyst must review all findings."
)


class ReviewReason(StrEnum):
    ANOMALY_SIGNAL = "ANOMALY_SIGNAL"
    ELEVATED_RISK = "ELEVATED_RISK"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    INCONSISTENT_EVIDENCE = "INCONSISTENT_EVIDENCE"
    GUARDRAIL_INTERVENED = "GUARDRAIL_INTERVENED"
    MALFORMED_MODEL_OUTPUT = "MALFORMED_MODEL_OUTPUT"
    UNGROUNDED_FINDING = "UNGROUNDED_FINDING"
    NO_GUIDANCE_RETRIEVED = "NO_GUIDANCE_RETRIEVED"
    UNTRUSTED_INSTRUCTIONS_DETECTED = "UNTRUSTED_INSTRUCTIONS_DETECTED"


class InvestigationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = RESULT_SCHEMA_VERSION
    job_id: JobId
    claim_id: ClaimId
    correlation_id: CorrelationId
    status: Literal[JobStatus.COMPLETED, JobStatus.REVIEW_REQUIRED]
    advisory_notice: str = ADVISORY_NOTICE
    executive_summary: AdvisoryText
    evidence_summary: list[EvidenceReference]
    missing_information: list[MissingInformation] = Field(default_factory=list)
    anomaly_signals: list[AnomalySignal] = Field(default_factory=list)
    risk_indicators: list[RiskIndicator] = Field(default_factory=list)
    retrieved_sources: list[RetrievedSource] = Field(default_factory=list)
    recommended_analyst_actions: list[AnalystAction] = Field(default_factory=list)
    confidence: Confidence
    limitations: list[AdvisoryText] = Field(default_factory=list)
    human_review_required: bool
    review_reasons: list[ReviewReason] = Field(default_factory=list)
    created_at: AwareDatetime
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def _check_integrity(self) -> Self:
        if self.advisory_notice != ADVISORY_NOTICE:
            raise ValueError("advisory_notice must not be altered")
        if self.human_review_required != (self.status is JobStatus.REVIEW_REQUIRED):
            raise ValueError("status must be REVIEW_REQUIRED exactly when human review is required")
        if self.human_review_required and not self.review_reasons:
            raise ValueError("review_reasons are required when human review is required")
        if self.completed_at < self.created_at:
            raise ValueError("completed_at must not precede created_at")
        known = {e.evidence_id for e in self.evidence_summary} | {
            s.source_id for s in self.retrieved_sources
        }
        cited = [ref for s in self.anomaly_signals for ref in s.evidence_refs]
        cited += [ref for r in self.risk_indicators for ref in r.evidence_refs]
        cited += [ref for a in self.recommended_analyst_actions for ref in a.evidence_refs]
        cited += [ref for m in self.missing_information for ref in m.related_evidence_ids]
        unknown = sorted(set(cited) - known)
        if unknown:
            raise ValueError(f"findings cite unknown evidence ids: {unknown}")
        return self
