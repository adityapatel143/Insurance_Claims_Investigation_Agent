from dataclasses import replace

import pytest

from claims_investigator.models.findings import AnomalySignal, Level, RiskIndicator
from claims_investigator.models.result import InvestigationResult, ReviewReason
from claims_investigator.services.human_review import (
    ReviewInputs,
    assess_review,
    minimum_review_reasons,
)

CLEAN = ReviewInputs(
    anomaly_signals=[],
    risk_indicators=[],
    confidence=0.9,
    missing_information_count=0,
    inconsistency_count=0,
    guardrail_intervened=False,
    model_output_invalid=False,
    ungrounded_findings_dropped=0,
    guidance_retrieved=True,
    injection_markers_found=False,
)
SIGNAL = AnomalySignal(
    code="AMOUNT_MISMATCH",
    description="Amounts differ and require review.",
    evidence_refs=["meta:claimed_amount"],
    confidence=0.9,
    origin="RULE",
)


def _indicator(level: Level) -> RiskIndicator:
    return RiskIndicator(
        category="DOCUMENTATION",
        level=level,
        rationale="Synthetic rationale.",
        basis="EVIDENCE",
        evidence_refs=["meta:claim_type"],
        confidence=0.8,
    )


def test_clean_case_does_not_require_review() -> None:
    decision = assess_review(CLEAN, 0.7)
    assert not decision.required
    assert decision.reasons == ()


def test_low_risk_indicator_alone_does_not_require_review() -> None:
    assert not assess_review(replace(CLEAN, risk_indicators=[_indicator(Level.LOW)]), 0.7).required


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"anomaly_signals": [SIGNAL]}, ReviewReason.ANOMALY_SIGNAL),
        ({"risk_indicators": [_indicator(Level.MEDIUM)]}, ReviewReason.ELEVATED_RISK),
        ({"confidence": 0.69}, ReviewReason.LOW_CONFIDENCE),
        ({"missing_information_count": 1}, ReviewReason.MISSING_INFORMATION),
        ({"inconsistency_count": 1}, ReviewReason.INCONSISTENT_EVIDENCE),
        ({"guardrail_intervened": True}, ReviewReason.GUARDRAIL_INTERVENED),
        ({"model_output_invalid": True}, ReviewReason.MALFORMED_MODEL_OUTPUT),
        ({"ungrounded_findings_dropped": 2}, ReviewReason.UNGROUNDED_FINDING),
        ({"guidance_retrieved": False}, ReviewReason.NO_GUIDANCE_RETRIEVED),
        ({"injection_markers_found": True}, ReviewReason.UNTRUSTED_INSTRUCTIONS_DETECTED),
    ],
)
def test_each_condition_routes_to_review(change: dict[str, object], reason: ReviewReason) -> None:
    decision = assess_review(replace(CLEAN, **change), 0.7)  # type: ignore[arg-type]
    assert decision.required
    assert decision.reasons == (reason,)


def test_minimum_reasons_from_persisted_result(result_fixture: dict[str, object]) -> None:
    result = InvestigationResult.model_validate(result_fixture)
    reasons = minimum_review_reasons(result, 0.7)
    assert ReviewReason.ANOMALY_SIGNAL in reasons
    assert ReviewReason.ELEVATED_RISK in reasons
    assert ReviewReason.LOW_CONFIDENCE in reasons
