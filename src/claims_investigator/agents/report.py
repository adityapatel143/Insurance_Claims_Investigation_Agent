"""Report agent: grounding filter, de-duplication, result assembly, and Markdown rendering."""

from collections.abc import Iterable, Sequence
from threading import Event
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field

from claims_investigator.models.common import AdvisoryText
from claims_investigator.models.findings import AnalystAction, AnomalySignal
from claims_investigator.models.result import InvestigationResult
from claims_investigator.prompts import system_prompt
from claims_investigator.services.ports import StructuredModel


class ReportNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executive_summary: AdvisoryText
    limitations: Annotated[list[AdvisoryText], Field(max_length=10)] = []


class _Cited(Protocol):
    @property
    def evidence_refs(self) -> list[str]: ...


class ReportAgent:
    def __init__(self, model: StructuredModel) -> None:
        self._model = model

    def run(self, findings: str, cancel: Event) -> ReportNarrative:
        return self._model.generate(
            system_prompt("report"), f"FINDINGS\n{findings}", ReportNarrative, cancel
        )


def fallback_narrative(
    documents: int, missing: int, signals: int, indicators: int
) -> ReportNarrative:
    return ReportNarrative(
        executive_summary=(
            f"{documents} submitted document(s) were reviewed. "
            f"{missing} missing-information item(s), "
            f"{signals} potential anomaly signal(s), and {indicators} risk indicator(s) were "
            "recorded. All findings require analyst review."
        ),
        limitations=["The executive summary was generated from a deterministic template."],
    )


def filter_grounded[T: _Cited](items: Sequence[T], known: frozenset[str]) -> tuple[list[T], int]:
    """Drop findings that cite any evidence ID not present in the evidence index or sources."""
    kept = [item for item in items if set(item.evidence_refs) <= known]
    return kept, len(items) - len(kept)


def dedupe_signals(signals: Iterable[AnomalySignal]) -> list[AnomalySignal]:
    """Keep one signal per code; rule-based signals take precedence over model duplicates."""
    best: dict[str, AnomalySignal] = {}
    for signal in signals:
        current = best.get(signal.code)
        if current is None or (current.origin == "MODEL" and signal.origin == "RULE"):
            best[signal.code] = signal
    return list(best.values())


def dedupe_actions(actions: Iterable[AnalystAction]) -> list[AnalystAction]:
    seen: dict[str, AnalystAction] = {}
    for action in actions:
        seen.setdefault(" ".join(action.action.lower().split()), action)
    return list(seen.values())


def render_markdown(result: InvestigationResult) -> str:
    lines = [
        f"# Claim investigation report — {result.claim_id}",
        "",
        f"> {result.advisory_notice}",
        "",
        f"- Job: `{result.job_id}`",
        f"- Correlation ID: `{result.correlation_id}`",
        f"- Status: **{result.status}**",
        f"- Human review required: **{'yes' if result.human_review_required else 'no'}**",
        f"- Review reasons: {', '.join(result.review_reasons) or 'none'}",
        f"- Confidence: {result.confidence:.2f}",
        f"- Completed: {result.completed_at.isoformat()}",
        "",
        "## Executive summary",
        "",
        result.executive_summary,
        "",
        "## Missing information",
        "",
        *_bullets(
            f"{m.item} — {m.reason} {_refs(m.related_evidence_ids)}"
            for m in result.missing_information
        ),
        "",
        "## Potential anomaly signals",
        "",
        *_bullets(
            f"**{s.code}** ({s.origin.lower()}, confidence {s.confidence:.2f}): {s.description} "
            f"{_refs(s.evidence_refs)}"
            for s in result.anomaly_signals
        ),
        "",
        "## Risk indicators",
        "",
        *_bullets(
            f"**{r.category}** — {r.level} ({r.basis.lower().replace('_', ' ')}, "
            f"confidence {r.confidence:.2f}): {r.rationale} {_refs(r.evidence_refs)}"
            for r in result.risk_indicators
        ),
        "",
        "## Recommended analyst actions",
        "",
        *_bullets(
            f"[{a.priority}] {a.action} — {a.rationale} {_refs(a.evidence_refs)}"
            for a in result.recommended_analyst_actions
        ),
        "",
        "## Evidence index",
        "",
        *_bullets(f"`{e.evidence_id}` — {e.description}" for e in result.evidence_summary),
        "",
        "## Retrieved sources",
        "",
        *_bullets(
            f"`{s.source_id}` {s.title or s.document_id} ({s.source_type}, score {s.score:.3f})"
            for s in result.retrieved_sources
        ),
        "",
        "## Limitations",
        "",
        *_bullets(result.limitations),
        "",
    ]
    return "\n".join(lines)


def _refs(refs: Sequence[str]) -> str:
    return f"[{', '.join(f'`{r}`' for r in refs)}]" if refs else ""


def _bullets(items: Iterable[str]) -> list[str]:
    rendered = [f"- {item}" for item in items]
    return rendered or ["- None recorded."]
