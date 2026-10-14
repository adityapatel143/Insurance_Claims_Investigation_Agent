"""Anomaly-signal agent: deterministic rules plus a guardrailed model pass.

Signals are "potential anomaly signals" that require review; they are never fraud determinations.
"""

from threading import Event
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from claims_investigator.agents.context import PromptContext, render_signals
from claims_investigator.agents.evidence import meta_id
from claims_investigator.models.api import ClaimSubmission
from claims_investigator.models.common import ensure_advisory_language
from claims_investigator.models.evidence import EvidenceBundle
from claims_investigator.models.findings import AnomalySignal
from claims_investigator.prompts import system_prompt
from claims_investigator.services.ports import StructuredModel

LATE_REPORTING_DAYS = 30
RULE_CONFIDENCE = 0.9
_RULES: dict[str, tuple[str, str]] = {
    "claimed_amount": (
        "AMOUNT_MISMATCH",
        "Amounts stated in the submission and documents differ and require review.",
    ),
    "incident_date": (
        "INCIDENT_DATE_MISMATCH",
        "Incident dates stated in the submission and documents differ and require review.",
    ),
    "policy_reference": (
        "POLICY_REFERENCE_MISMATCH",
        "Policy references in the submission and documents differ and require review.",
    ),
    "reported_date": (
        "REPORTED_BEFORE_INCIDENT",
        "The reported date precedes the incident date, which requires review.",
    ),
}


class ModelSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: Annotated[list[AnomalySignal], Field(max_length=10)]


def _describe(base: str, observed: list[str]) -> str:
    """Include observed values only when they cannot smuggle prohibited wording into the report."""
    candidate = f"{base} Observed: {'; '.join(observed)}."[:2000]
    try:
        return ensure_advisory_language(candidate)
    except ValueError:
        return base


def rule_signals(bundle: EvidenceBundle, submission: ClaimSubmission) -> list[AnomalySignal]:
    signals = [
        AnomalySignal(
            code=_RULES[item.field][0],
            description=_describe(_RULES[item.field][1], item.observed_values),
            evidence_refs=item.evidence_ids,
            confidence=RULE_CONFIDENCE,
            limitations=["Differences may stem from data-entry or formatting errors."],
            origin="RULE",
        )
        for item in bundle.inconsistencies
        if item.field in _RULES
    ]
    delay = (submission.reported_date - submission.incident_date).days
    if delay > LATE_REPORTING_DAYS:
        signals.append(
            AnomalySignal(
                code="LATE_REPORTING",
                description=(
                    f"The claim was reported {delay} days after the incident, beyond the "
                    f"{LATE_REPORTING_DAYS}-day review threshold."
                ),
                evidence_refs=[meta_id("incident_date"), meta_id("reported_date")],
                confidence=RULE_CONFIDENCE,
                limitations=["Reporting delays often have legitimate explanations."],
                origin="RULE",
            )
        )
    return signals


class AnomalySignalAgent:
    def __init__(self, model: StructuredModel) -> None:
        self._model = model

    def run(
        self, context: PromptContext, rules: list[AnomalySignal], cancel: Event
    ) -> list[AnomalySignal]:
        prompt = context.render(f"RULE-BASED SIGNALS (already detected)\n{render_signals(rules)}")
        output = self._model.generate(
            system_prompt("anomaly_signals"), prompt, ModelSignals, cancel
        )
        return [s.model_copy(update={"origin": "MODEL"}) for s in output.signals]
