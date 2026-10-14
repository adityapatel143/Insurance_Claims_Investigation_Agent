"""Investigation pipeline: evidence -> retrieval -> anomaly signals -> risk -> report -> persist."""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from threading import Event
from typing import TypeVar

from claims_investigator import metrics
from claims_investigator.agents.context import build_context, render_missing, render_signals
from claims_investigator.agents.evidence import EvidenceAgent
from claims_investigator.agents.fraud_signals import AnomalySignalAgent, rule_signals
from claims_investigator.agents.report import (
    ReportAgent,
    ReportNarrative,
    dedupe_actions,
    dedupe_signals,
    fallback_narrative,
    filter_grounded,
    render_markdown,
)
from claims_investigator.agents.risk import (
    RiskAssessment,
    RiskAssessmentAgent,
    fallback_assessment,
)
from claims_investigator.errors import (
    ClaimsInvestigatorError,
    GuardrailInterventionError,
    InvestigationTimeoutError,
    ModelOutputError,
)
from claims_investigator.logging import get_logger, log_event
from claims_investigator.models.api import ClaimSubmission
from claims_investigator.models.evidence import EvidenceBundle
from claims_investigator.models.findings import AnomalySignal, RetrievedChunk
from claims_investigator.models.jobs import FailureCategory, JobStatus
from claims_investigator.models.messages import RuntimeInvocation
from claims_investigator.models.result import InvestigationResult
from claims_investigator.services.human_review import ReviewInputs, assess_review
from claims_investigator.services.memory import MemoryService
from claims_investigator.services.ports import (
    Clock,
    InvestigationTools,
    ObjectStore,
    StructuredModel,
    utc_now,
)
from claims_investigator.tools.schemas import ToolRequest

_LOG = get_logger(__name__)
MAX_SUBMISSION_BYTES = 64 * 1024
DEGRADED_CONFIDENCE_CAP = 0.3
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PipelineSettings:
    review_confidence_threshold: float
    max_document_bytes: int
    investigation_timeout_seconds: int


@dataclass(slots=True)
class _Flags:
    guardrail_intervened: bool = False
    model_output_invalid: bool = False
    steps_degraded: list[str] = field(default_factory=list)


class InvestigationPipeline:
    def __init__(
        self,
        tools: InvestigationTools,
        store: ObjectStore,
        model: StructuredModel,
        memory: MemoryService,
        *,
        settings: PipelineSettings,
        clock: Clock = utc_now,
    ) -> None:
        self._tools = tools
        self._store = store
        self._memory = memory
        self._settings = settings
        self._clock = clock
        self._evidence = EvidenceAgent(store, settings.max_document_bytes)
        self._signals = AnomalySignalAgent(model)
        self._risk = RiskAssessmentAgent(model)
        self._report = ReportAgent(model)

    def run(self, invocation: RuntimeInvocation) -> JobStatus:
        request = ToolRequest(
            job_id=invocation.job_id,
            claim_id=invocation.claim_id,
            correlation_id=invocation.correlation_id,
        )
        now = self._clock()
        deadline = min(
            invocation.processing_deadline,
            now + timedelta(seconds=self._settings.investigation_timeout_seconds),
        )
        cancel = Event()
        timer = threading.Timer(max(0.0, (deadline - now).total_seconds()), cancel.set)
        timer.daemon = True
        timer.start()
        try:
            self._tools.mark_processing(request, invocation.processing_deadline)
            result = self._investigate(invocation, request, cancel)
            _check(cancel)
            persisted = self._tools.persist_investigation_findings(
                request, result.model_dump_json(), render_markdown(result)
            )
            self._memory.save_summary(invocation.actor_id, result)
            log_event(_LOG, logging.INFO, "investigation_completed", status=str(persisted.status))
            return persisted.status
        except Exception as exc:
            category = _failure_category(exc, cancel)
            log_event(
                _LOG,
                logging.ERROR,
                "investigation_failed",
                failure_category=str(category),
                exception_type=type(exc).__name__,
            )
            try:
                self._tools.mark_failed(request, category)
            except Exception as mark_exc:
                log_event(
                    _LOG,
                    logging.ERROR,
                    "mark_failed_failed",
                    exception_type=type(mark_exc).__name__,
                )
            return JobStatus.FAILED
        finally:
            timer.cancel()

    def _investigate(
        self, invocation: RuntimeInvocation, request: ToolRequest, cancel: Event
    ) -> InvestigationResult:
        started = self._clock()
        submission = ClaimSubmission.model_validate_json(
            self._store.get_bytes(invocation.submission_key, MAX_SUBMISSION_BYTES)
        )
        metadata = self._tools.get_claim_document_metadata(request)
        evidence = self._evidence.run(invocation.job_id, submission, metadata)
        bundle = evidence.bundle
        _check(cancel)

        rules = rule_signals(bundle, submission)
        guidance_query = _guidance_query(submission, [s.code for s in rules], bundle)
        guidance = self._tools.get_policy_guidance(request, submission.claim_type, guidance_query)
        similar = self._tools.search_similar_claims(
            request, submission.claim_type, submission.incident_description[:500]
        )
        chunks = _unique_chunks([*guidance, *similar])
        memory = self._memory.load(invocation.actor_id, invocation.job_id)
        context = build_context(evidence, submission, chunks, memory)
        _check(cancel)

        flags = _Flags()
        model_signals: list[AnomalySignal] = self._guarded(
            "anomaly_signals", flags, lambda: self._signals.run(context, rules, cancel), lambda: []
        )
        signals = dedupe_signals([*rules, *model_signals])
        _check(cancel)
        risk = self._guarded(
            "risk_assessment",
            flags,
            lambda: self._risk.run(context, signals, bundle.missing_information, cancel),
            lambda: fallback_assessment(signals, bundle.missing_information),
        )
        _check(cancel)

        known = bundle.evidence_ids | {c.source.source_id for c in chunks}
        signals, dropped_signals = filter_grounded(signals, known)
        indicators, dropped_indicators = filter_grounded(risk.risk_indicators, known)
        actions, dropped_actions = filter_grounded(
            dedupe_actions(risk.recommended_analyst_actions), known
        )
        dropped = dropped_signals + dropped_indicators + dropped_actions

        findings = "\n\n".join(
            [
                f"DOCUMENTS REVIEWED: {len(bundle.documents)}",
                f"MISSING INFORMATION\n{render_missing(bundle.missing_information)}",
                f"ANOMALY SIGNALS\n{render_signals(signals)}",
                "RISK INDICATORS\n"
                + (
                    "\n".join(f"- {r.category} {r.level}: {r.rationale}" for r in indicators)
                    or "(none)"
                ),
                "ANALYST ACTIONS\n" + ("\n".join(f"- {a.action}" for a in actions) or "(none)"),
            ]
        )
        narrative = self._guarded(
            "report",
            flags,
            lambda: self._report.run(findings, cancel),
            lambda: fallback_narrative(
                len(bundle.documents),
                len(bundle.missing_information),
                len(signals),
                len(indicators),
            ),
        )

        confidence = risk.confidence
        if flags.guardrail_intervened or flags.model_output_invalid:
            confidence = min(confidence, DEGRADED_CONFIDENCE_CAP)
        decision = assess_review(
            ReviewInputs(
                anomaly_signals=signals,
                risk_indicators=indicators,
                confidence=confidence,
                missing_information_count=len(bundle.missing_information),
                inconsistency_count=len(bundle.inconsistencies),
                guardrail_intervened=flags.guardrail_intervened,
                model_output_invalid=flags.model_output_invalid,
                ungrounded_findings_dropped=dropped,
                guidance_retrieved=bool(guidance),
                injection_markers_found=bool(evidence.injection_markers),
            ),
            self._settings.review_confidence_threshold,
        )
        limitations = _limitations(
            risk,
            narrative,
            flags,
            dropped=dropped,
            guidance=guidance,
            markers=evidence.injection_markers,
        )
        metrics.emit("UngroundedFindingsDropped", dropped)
        return InvestigationResult(
            job_id=invocation.job_id,
            claim_id=invocation.claim_id,
            correlation_id=invocation.correlation_id,
            status=JobStatus.REVIEW_REQUIRED if decision.required else JobStatus.COMPLETED,
            executive_summary=narrative.executive_summary,
            evidence_summary=bundle.references,
            missing_information=bundle.missing_information,
            anomaly_signals=signals,
            risk_indicators=indicators,
            retrieved_sources=[c.source for c in chunks],
            recommended_analyst_actions=actions,
            confidence=confidence,
            limitations=limitations,
            human_review_required=decision.required,
            review_reasons=list(decision.reasons),
            created_at=started,
            completed_at=self._clock(),
        )

    def _guarded(
        self, step: str, flags: _Flags, call: Callable[[], T], fallback: Callable[[], T]
    ) -> T:
        """Model failures degrade to deterministic output and force human review."""
        try:
            return call()
        except GuardrailInterventionError:
            flags.guardrail_intervened = True
        except ModelOutputError:
            flags.model_output_invalid = True
        flags.steps_degraded.append(step)
        log_event(_LOG, logging.WARNING, "model_step_degraded", step=step)
        metrics.emit("ModelStepDegraded", 1, Step=step)
        return fallback()


def _check(cancel: Event) -> None:
    if cancel.is_set():
        raise InvestigationTimeoutError("investigation deadline exceeded")


def _failure_category(exc: Exception, cancel: Event) -> FailureCategory:
    if cancel.is_set():
        return FailureCategory.TIMEOUT
    if (
        isinstance(exc, ClaimsInvestigatorError)
        and exc.failure_category != FailureCategory.INTERNAL
    ):
        return exc.failure_category
    return FailureCategory.RUNTIME_ERROR


def _guidance_query(submission: ClaimSubmission, codes: list[str], bundle: EvidenceBundle) -> str:
    missing = "; ".join(m.item for m in bundle.missing_information)
    return (
        f"{submission.claim_type} claim investigation procedure. "
        f"Signals: {', '.join(codes) or 'none'}. Missing: {missing or 'none'}."
    )


def _unique_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: dict[str, RetrievedChunk] = {}
    for chunk in chunks:
        seen.setdefault(chunk.source.source_id, chunk)
    return list(seen.values())


def _limitations(
    risk: RiskAssessment,
    narrative: ReportNarrative,
    flags: _Flags,
    *,
    dropped: int,
    guidance: list[RetrievedChunk],
    markers: tuple[str, ...],
) -> list[str]:
    items = [*risk.limitations, *narrative.limitations]
    if flags.guardrail_intervened:
        items.append("A content guardrail intervened; affected steps used deterministic output.")
    if flags.model_output_invalid:
        items.append("Model output failed validation; affected steps used deterministic output.")
    if dropped:
        items.append(f"{dropped} finding(s) without valid evidence references were removed.")
    if not guidance:
        items.append("No investigation guidance was retrieved for this claim type.")
    if markers:
        items.append("Embedded instructions were detected in submitted content and were ignored.")
    return list(dict.fromkeys(items))
