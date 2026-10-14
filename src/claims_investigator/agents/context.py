"""Prompt context rendering; all claim-derived and retrieved text is fenced as untrusted data."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from claims_investigator.agents.evidence import EvidenceOutput
from claims_investigator.models.api import ClaimSubmission
from claims_investigator.models.evidence import MissingInformation
from claims_investigator.models.findings import AnomalySignal, RetrievedChunk
from claims_investigator.services.guardrails import wrap_untrusted
from claims_investigator.services.ports import MemoryContext


@dataclass(frozen=True, slots=True)
class PromptContext:
    evidence_index: str
    documents: str
    sources: str
    memory: str

    def render(self, *sections: str) -> str:
        return "\n\n".join(
            [
                f"EVIDENCE INDEX\n{self.evidence_index}",
                f"CLAIM DOCUMENTS\n{self.documents}",
                f"RETRIEVED SOURCES\n{self.sources}",
                f"INVESTIGATOR CONTEXT\n{self.memory}",
                *sections,
            ]
        )


def build_context(
    evidence: EvidenceOutput,
    submission: ClaimSubmission,
    chunks: Sequence[RetrievedChunk],
    memory: MemoryContext,
) -> PromptContext:
    values = {f.evidence_id: f"{f.name} = {f.value}" for f in evidence.bundle.fields}
    index_lines = [
        f"- {ref.evidence_id} | {ref.description}"
        + (f" | {values[ref.evidence_id]}" if ref.evidence_id in values else "")
        for ref in evidence.bundle.references
    ]
    documents = [wrap_untrusted("meta:incident_description", submission.incident_description)]
    documents += [
        wrap_untrusted(f"doc:{doc_id}", text) for doc_id, text in evidence.document_texts.items()
    ]
    sources = [
        wrap_untrusted(
            c.source.source_id,
            f"type={c.source.source_type} score={c.source.score:.3f} title={c.source.title}\n"
            f"{c.text}",
        )
        for c in chunks
    ]
    memory_lines = [f"- preference: {p}" for p in memory.preferences] + [
        f"- prior summary for this job: {s}" for s in memory.session_summaries
    ]
    return PromptContext(
        evidence_index=wrap_untrusted("evidence-index", "\n".join(index_lines)),
        documents="\n".join(documents),
        sources="\n".join(sources) or "(no sources retrieved)",
        memory=wrap_untrusted("memory", "\n".join(memory_lines)) if memory_lines else "(none)",
    )


def render_signals(signals: Iterable[AnomalySignal]) -> str:
    lines = [
        f"- {s.code} (origin={s.origin}, confidence={s.confidence:.2f}) "
        f"refs={','.join(s.evidence_refs)}: {s.description}"
        for s in signals
    ]
    return "\n".join(lines) or "(none)"


def render_missing(missing: Iterable[MissingInformation]) -> str:
    lines = [
        f"- {m.item}: {m.reason} refs={','.join(m.related_evidence_ids) or 'none'}" for m in missing
    ]
    return "\n".join(lines) or "(none)"
