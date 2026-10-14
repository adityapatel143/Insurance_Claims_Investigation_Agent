"""Deterministic human-review routing (ADR 0004); the model never decides this."""

from collections.abc import Sequence
from dataclasses import dataclass

from claims_investigator.models.findings import AnomalySignal, Level, RiskIndicator
from claims_investigator.models.result import InvestigationResult, ReviewReason


@dataclass(frozen=True, slots=True)
class ReviewInputs:
    anomaly_signals: Sequence[AnomalySignal]
    risk_indicators: Sequence[RiskIndicator]
    confidence: float
    missing_information_count: int
    inconsistency_count: int
    guardrail_intervened: bool
    model_output_invalid: bool
    ungrounded_findings_dropped: int
    guidance_retrieved: bool
    injection_markers_found: bool


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    required: bool
    reasons: tuple[ReviewReason, ...]


def assess_review(inputs: ReviewInputs, confidence_threshold: float) -> ReviewDecision:
    checks: tuple[tuple[bool, ReviewReason], ...] = (
        (bool(inputs.anomaly_signals), ReviewReason.ANOMALY_SIGNAL),
        (
            any(r.level is not Level.LOW for r in inputs.risk_indicators),
            ReviewReason.ELEVATED_RISK,
        ),
        (inputs.confidence < confidence_threshold, ReviewReason.LOW_CONFIDENCE),
        (inputs.missing_information_count > 0, ReviewReason.MISSING_INFORMATION),
        (inputs.inconsistency_count > 0, ReviewReason.INCONSISTENT_EVIDENCE),
        (inputs.guardrail_intervened, ReviewReason.GUARDRAIL_INTERVENED),
        (inputs.model_output_invalid, ReviewReason.MALFORMED_MODEL_OUTPUT),
        (inputs.ungrounded_findings_dropped > 0, ReviewReason.UNGROUNDED_FINDING),
        (not inputs.guidance_retrieved, ReviewReason.NO_GUIDANCE_RETRIEVED),
        (inputs.injection_markers_found, ReviewReason.UNTRUSTED_INSTRUCTIONS_DETECTED),
    )
    reasons = tuple(reason for triggered, reason in checks if triggered)
    return ReviewDecision(required=bool(reasons), reasons=reasons)


def minimum_review_reasons(
    result: InvestigationResult, confidence_threshold: float
) -> tuple[ReviewReason, ...]:
    """Review reasons derivable from a persisted result alone (defence in depth at the tool)."""
    inputs = ReviewInputs(
        anomaly_signals=result.anomaly_signals,
        risk_indicators=result.risk_indicators,
        confidence=result.confidence,
        missing_information_count=len(result.missing_information),
        inconsistency_count=0,
        guardrail_intervened=False,
        model_output_invalid=False,
        ungrounded_findings_dropped=0,
        guidance_retrieved=bool(result.retrieved_sources),
        injection_markers_found=False,
    )
    return assess_review(inputs, confidence_threshold).reasons
