"""Pipeline tests: real agents, services, and tool dispatcher; fakes at AWS and model boundaries."""

import time
from collections.abc import Callable

import pytest
from pydantic import BaseModel

from claims_investigator.agents.fraud_signals import ModelSignals
from claims_investigator.agents.pipeline import InvestigationPipeline, PipelineSettings
from claims_investigator.agents.report import ReportNarrative
from claims_investigator.agents.risk import RiskAssessment
from claims_investigator.errors import GuardrailInterventionError, ModelOutputError
from claims_investigator.models.common import DocumentType
from claims_investigator.models.findings import AnalystAction, AnomalySignal, Level, RiskIndicator
from claims_investigator.models.jobs import FailureCategory, JobStatus
from claims_investigator.models.result import InvestigationResult, ReviewReason
from claims_investigator.services.memory import MemoryService
from claims_investigator.storage_keys import report_json_key, report_markdown_key
from tests.fakes import (
    DispatcherBackedTools,
    DocSpec,
    FakeMemoryStore,
    FakeStructuredModel,
    FakeVectorSearch,
    World,
    standard_docs,
)

SETTINGS = PipelineSettings(
    review_confidence_threshold=0.7,
    max_document_bytes=1024 * 1024,
    investigation_timeout_seconds=1800,
)
NARRATIVE = ReportNarrative(
    executive_summary=(
        "Synthetic review: documents are consistent; analyst confirmation is still required."
    )
)


def _risk(confidence: float = 0.9) -> RiskAssessment:
    return RiskAssessment(
        risk_indicators=[
            RiskIndicator(
                category="DOCUMENTATION",
                level=Level.LOW,
                rationale="All expected documents were readable and consistent.",
                basis="EVIDENCE",
                evidence_refs=["meta:claim_type"],
                confidence=confidence,
            )
        ],
        recommended_analyst_actions=[
            AnalystAction(
                action="Confirm the repair estimate with the listed shop.",
                rationale="Standard verification step from guidance.",
                priority=Level.LOW,
                evidence_refs=["src:guidance-auto-001#c0"],
            )
        ],
        confidence=confidence,
    )


def _model(**overrides: BaseModel | Exception | Callable[[str], BaseModel]) -> FakeStructuredModel:
    responses: dict[str, BaseModel | Exception | Callable[[str], BaseModel]] = {
        "ModelSignals": ModelSignals(signals=[]),
        "RiskAssessment": _risk(),
        "ReportNarrative": NARRATIVE,
    }
    responses.update(overrides)
    return FakeStructuredModel(responses)


def _run(world: World, model: FakeStructuredModel, docs: list[DocSpec] | None = None, **kw: object):  # type: ignore[no-untyped-def]
    submission, job = world.seed_job(docs)
    memory_store = FakeMemoryStore()
    tools = DispatcherBackedTools(world.dispatcher(), kw.pop("before_call", None))  # type: ignore[arg-type]
    pipeline = InvestigationPipeline(
        tools, world.store, model, MemoryService(memory_store), settings=SETTINGS, clock=world.clock
    )
    status = pipeline.run(world.invocation(job, submission, **kw))  # type: ignore[arg-type]
    stored = world.repo.jobs[job.job_id]
    result = None
    if status is not JobStatus.FAILED:
        result = InvestigationResult.model_validate_json(
            world.store.objects[report_json_key(job.claim_id, job.job_id)][0]
        )
    return status, stored, result, tools, memory_store


def test_consistent_claim_completes_with_advisory_report(world: World) -> None:
    status, stored, result, tools, memory = _run(world, _model())

    assert status is JobStatus.COMPLETED
    assert stored.status is JobStatus.COMPLETED
    assert stored.human_review_required is False
    assert stored.report_markdown_key == report_markdown_key(stored.claim_id, stored.job_id)
    assert result is not None
    assert result.review_reasons == []
    assert {s.source_id for s in result.retrieved_sources} == {
        "src:guidance-auto-001#c0",
        "src:historical-auto-007#c0",
    }
    assert tools.calls[0] == "update_job_status"
    assert tools.calls[-1] == "persist_investigation_findings"
    assert len(memory.summaries) == 1
    assert "Synthetic review" not in memory.summaries[0][2]


def test_inconsistent_amounts_require_review_with_evidence_refs(world: World) -> None:
    docs = standard_docs()
    docs[1] = DocSpec(
        DocumentType.REPAIR_ESTIMATE,
        "repair_estimate.csv",
        "text/csv",
        b"field,value\ntotal_amount,1890.00\n",
    )
    status, stored, result, _, _ = _run(world, _model(), docs)

    assert status is JobStatus.REVIEW_REQUIRED
    assert stored.anomaly_signal_count == 1
    assert result is not None
    signal = result.anomaly_signals[0]
    assert signal.code == "AMOUNT_MISMATCH"
    known = {e.evidence_id for e in result.evidence_summary}
    assert set(signal.evidence_refs) <= known
    assert ReviewReason.ANOMALY_SIGNAL in result.review_reasons
    assert ReviewReason.INCONSISTENT_EVIDENCE in result.review_reasons


def test_guardrail_block_degrades_and_forces_review(world: World) -> None:
    model = _model(
        ModelSignals=GuardrailInterventionError("blocked"),
        RiskAssessment=GuardrailInterventionError("blocked"),
    )
    status, _, result, _, _ = _run(world, model)

    assert status is JobStatus.REVIEW_REQUIRED
    assert result is not None
    assert ReviewReason.GUARDRAIL_INTERVENED in result.review_reasons
    assert result.confidence <= 0.3
    assert any("guardrail" in item for item in result.limitations)


def test_malformed_model_output_degrades_and_forces_review(world: World) -> None:
    status, _, result, _, _ = _run(world, _model(ReportNarrative=ModelOutputError("bad json")))

    assert status is JobStatus.REVIEW_REQUIRED
    assert result is not None
    assert ReviewReason.MALFORMED_MODEL_OUTPUT in result.review_reasons
    assert any("template" in item for item in result.limitations)


def test_ungrounded_model_findings_are_dropped(world: World) -> None:
    invented = AnomalySignal(
        code="INVENTED_SOURCE",
        description="Cites a document that does not exist.",
        evidence_refs=["doc:does-not-exist#L1"],
        confidence=0.8,
        origin="MODEL",
    )
    status, _, result, _, _ = _run(world, _model(ModelSignals=ModelSignals(signals=[invented])))

    assert status is JobStatus.REVIEW_REQUIRED
    assert result is not None
    assert all(s.code != "INVENTED_SOURCE" for s in result.anomaly_signals)
    assert ReviewReason.UNGROUNDED_FINDING in result.review_reasons


def test_no_guidance_retrieved_requires_review(world: World) -> None:
    world.search = FakeVectorSearch([])
    actionless = _risk().model_copy(update={"recommended_analyst_actions": []})
    status, _, result, _, _ = _run(world, _model(RiskAssessment=actionless))

    assert status is JobStatus.REVIEW_REQUIRED
    assert result is not None
    assert result.retrieved_sources == []
    assert ReviewReason.NO_GUIDANCE_RETRIEVED in result.review_reasons


def test_embedded_instructions_are_ignored_and_flagged(world: World) -> None:
    from tests.fakes import fixture_bytes

    docs = [
        *standard_docs(),
        DocSpec(
            DocumentType.CORRESPONDENCE,
            "note.txt",
            "text/plain",
            fixture_bytes("injected_note.txt"),
        ),
    ]
    model = _model()
    status, _, result, tools, _ = _run(world, model, docs)

    assert status is JobStatus.REVIEW_REQUIRED
    assert result is not None
    assert ReviewReason.UNTRUSTED_INSTRUCTIONS_DETECTED in result.review_reasons
    prompt = model.prompts[0][1]
    assert '<untrusted_data source="doc:' in prompt
    assert set(tools.calls) <= {
        "update_job_status",
        "get_claim_document_metadata",
        "get_policy_guidance",
        "search_similar_claims",
        "persist_investigation_findings",
    }


def test_deadline_exceeded_marks_failed_timeout(world: World) -> None:
    def slow(tool: str) -> None:
        if tool == "get_claim_document_metadata":
            time.sleep(0.2)

    status, stored, _, _, _ = _run(world, _model(), before_call=slow, deadline_s=0.05)

    assert status is JobStatus.FAILED
    assert stored.status is JobStatus.FAILED
    assert stored.failure_category is FailureCategory.TIMEOUT


def test_tool_failure_marks_failed(world: World) -> None:
    def broken(tool: str) -> None:
        if tool == "get_policy_guidance":
            raise RuntimeError("gateway down")

    status, stored, _, _, _ = _run(world, _model(), before_call=broken)

    assert status is JobStatus.FAILED
    assert stored.failure_category is FailureCategory.TOOL_ERROR


@pytest.mark.parametrize("confidence", [0.2, 0.69])
def test_low_confidence_requires_review(world: World, confidence: float) -> None:
    status, _, result, _, _ = _run(world, _model(RiskAssessment=_risk(confidence)))
    assert status is JobStatus.REVIEW_REQUIRED
    assert result is not None
    assert ReviewReason.LOW_CONFIDENCE in result.review_reasons
