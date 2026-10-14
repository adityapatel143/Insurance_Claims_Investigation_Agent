"""Risk-assessment agent with a deterministic fallback when the model is unavailable or blocked."""

from collections.abc import Sequence
from threading import Event
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from claims_investigator.agents.context import PromptContext, render_missing, render_signals
from claims_investigator.agents.evidence import meta_id
from claims_investigator.models.common import AdvisoryText, Confidence
from claims_investigator.models.evidence import MissingInformation
from claims_investigator.models.findings import AnalystAction, AnomalySignal, Level, RiskIndicator
from claims_investigator.prompts import system_prompt
from claims_investigator.services.ports import StructuredModel

FALLBACK_CONFIDENCE = 0.3


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_indicators: Annotated[list[RiskIndicator], Field(max_length=15)]
    recommended_analyst_actions: Annotated[list[AnalystAction], Field(max_length=10)]
    confidence: Confidence
    limitations: Annotated[list[AdvisoryText], Field(max_length=10)] = []


class RiskAssessmentAgent:
    def __init__(self, model: StructuredModel) -> None:
        self._model = model

    def run(
        self,
        context: PromptContext,
        signals: Sequence[AnomalySignal],
        missing: Sequence[MissingInformation],
        cancel: Event,
    ) -> RiskAssessment:
        prompt = context.render(
            f"ANOMALY SIGNALS\n{render_signals(signals)}",
            f"MISSING INFORMATION\n{render_missing(missing)}",
        )
        return self._model.generate(
            system_prompt("risk_assessment"), prompt, RiskAssessment, cancel
        )


def fallback_assessment(
    signals: Sequence[AnomalySignal], missing: Sequence[MissingInformation]
) -> RiskAssessment:
    indicators = [
        RiskIndicator(
            category=s.code,
            level=Level.MEDIUM,
            rationale=f"Potential anomaly signal {s.code} requires review.",
            basis="EVIDENCE" if s.origin == "RULE" else "INFERENCE",
            evidence_refs=s.evidence_refs,
            confidence=s.confidence,
        )
        for s in signals
    ]
    actions = [
        AnalystAction(
            action=f"Review the evidence behind {s.code}.",
            rationale="Deterministic rule output; confirm against source documents.",
            priority=Level.MEDIUM,
            evidence_refs=s.evidence_refs,
        )
        for s in signals
    ]
    for item in missing:
        refs = item.related_evidence_ids or [meta_id("claim_type")]
        indicators.append(
            RiskIndicator(
                category="MISSING_INFORMATION",
                level=Level.MEDIUM,
                rationale=f"{item.item}: {item.reason}"[:2000],
                basis="MISSING_INFORMATION",
                evidence_refs=refs,
                confidence=1.0,
            )
        )
        actions.append(
            AnalystAction(
                action=f"Request or locate: {item.item}"[:300],
                rationale=item.reason,
                priority=Level.MEDIUM,
                evidence_refs=refs,
            )
        )
    return RiskAssessment(
        risk_indicators=indicators[:15],
        recommended_analyst_actions=actions[:10],
        confidence=FALLBACK_CONFIDENCE,
        limitations=["Risk narrative was produced by deterministic rules only."],
    )
