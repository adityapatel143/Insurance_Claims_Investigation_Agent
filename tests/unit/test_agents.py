from uuid import uuid4

from claims_investigator.agents.evidence import EvidenceAgent
from claims_investigator.agents.fraud_signals import rule_signals
from claims_investigator.agents.report import (
    dedupe_actions,
    dedupe_signals,
    filter_grounded,
    render_markdown,
)
from claims_investigator.models.common import DocumentType
from claims_investigator.models.findings import AnalystAction, AnomalySignal, Level
from claims_investigator.models.result import ADVISORY_NOTICE, InvestigationResult
from claims_investigator.tools.schemas import DocumentMetadata
from tests.fakes import (
    DocSpec,
    InMemoryObjectStore,
    fixture_bytes,
    make_submission,
    standard_docs,
    upload_docs,
)


def _run(docs: list[DocSpec], present: bool = True, **overrides: object):  # type: ignore[no-untyped-def]
    store = InMemoryObjectStore()
    upload_docs(store, docs)
    submission = make_submission(docs, **overrides)
    metadata = [
        DocumentMetadata(
            document_id=d.document_id,
            document_type=d.document_type,
            content_type=d.content_type,
            object_key=ref.object_key,
            present=present,
            size_bytes=len(d.body),
        )
        for d, ref in zip(docs, submission.documents, strict=True)
    ]
    return EvidenceAgent(store, 1024 * 1024).run(uuid4(), submission, metadata), store, submission


class TestEvidenceAgent:
    def test_extracts_fields_from_text_csv_and_json(self) -> None:
        output, store, _ = _run(standard_docs())
        names = {f.name for f in output.bundle.fields}
        assert {"claimed_amount", "policy_number", "date_of_loss"} <= names
        assert {"total_amount", "incident_date", "officer_badge"} <= names
        assert not output.bundle.missing_information
        assert not output.bundle.inconsistencies
        assert output.injection_markers == ()
        assert all(d.extraction_status == "EXTRACTED" for d in output.bundle.documents)
        assert sum(k.startswith("normalized/") for k in store.objects) == 3

    def test_evidence_ids_point_to_lines_and_keys(self) -> None:
        output, _, _ = _run(standard_docs())
        ids = output.bundle.evidence_ids
        assert any(i.endswith("#L4") for i in ids)
        assert any("#key:incident_date" in i for i in ids)
        assert {"meta:claimed_amount", "meta:incident_description"} <= ids
        assert all(f.evidence_id in ids for f in output.bundle.fields)

    def test_amount_mismatch_is_detected(self) -> None:
        docs = standard_docs()
        docs[1] = DocSpec(
            DocumentType.REPAIR_ESTIMATE,
            "repair_estimate.csv",
            "text/csv",
            b"field,value\ntotal_amount,1890.00\n",
        )
        output, _, submission = _run(docs)
        mismatch = next(i for i in output.bundle.inconsistencies if i.field == "claimed_amount")
        assert mismatch.observed_values == ["1250.00", "1890.00"]
        codes = [s.code for s in rule_signals(output.bundle, submission)]
        assert codes == ["AMOUNT_MISMATCH"]

    def test_date_inconsistencies_and_late_reporting(self) -> None:
        output, _, submission = _run(standard_docs(), reported_date="2025-04-20")
        codes = {s.code for s in rule_signals(output.bundle, submission)}
        assert "REPORTED_BEFORE_INCIDENT" in codes

        output, _, submission = _run(standard_docs(), reported_date="2025-07-30")
        assert "LATE_REPORTING" in {s.code for s in rule_signals(output.bundle, submission)}

    def test_missing_required_document_is_reported(self) -> None:
        output, _, _ = _run(standard_docs()[:1])
        items = {m.item for m in output.bundle.missing_information}
        assert "Repair estimate document" in items
        assert "Incident report document" in items

    def test_absent_and_unsupported_documents(self) -> None:
        docs = [
            DocSpec(DocumentType.CLAIM_FORM, "scan.pdf", "application/pdf", b"%PDF-1.7 synthetic"),
        ]
        output, _, _ = _run(docs)
        assert output.bundle.documents[0].extraction_status == "UNSUPPORTED"

        output, _, _ = _run(standard_docs(), present=False)
        assert all(d.extraction_status == "FAILED" for d in output.bundle.documents)
        assert len(output.bundle.missing_information) >= 3

    def test_malformed_json_is_failed_not_fatal(self) -> None:
        docs = standard_docs()
        docs[2] = DocSpec(
            DocumentType.INCIDENT_REPORT, "incident_report.json", "application/json", b"[1, 2"
        )
        output, _, _ = _run(docs)
        assert output.bundle.documents[2].extraction_status == "FAILED"

    def test_injection_markers_detected(self) -> None:
        docs = [
            *standard_docs(),
            DocSpec(
                DocumentType.CORRESPONDENCE,
                "note.txt",
                "text/plain",
                fixture_bytes("injected_note.txt"),
            ),
        ]
        output, _, _ = _run(docs)
        assert "override_instructions" in output.injection_markers


class TestRuleSignals:
    def test_prohibited_wording_in_document_values_is_not_echoed(self) -> None:
        docs = standard_docs()
        docs[0] = DocSpec(
            DocumentType.CLAIM_FORM,
            "claim_form.txt",
            "text/plain",
            b"Policy Number: POL-SYN-1001\nPolicy Reference: this person is fraudulent\n",
        )
        output, _, submission = _run(docs)
        signals = rule_signals(output.bundle, submission)
        policy = next(s for s in signals if s.code == "POLICY_REFERENCE_MISMATCH")
        assert "fraudulent" not in policy.description.lower()
        assert policy.origin == "RULE"


def _signal(code: str, origin: str, refs: list[str]) -> AnomalySignal:
    return AnomalySignal(
        code=code,
        description="Requires review.",
        evidence_refs=refs,
        confidence=0.5,
        origin=origin,  # type: ignore[arg-type]
    )


class TestReportHelpers:
    def test_filter_grounded_drops_unknown_references(self) -> None:
        kept, dropped = filter_grounded(
            [
                _signal("A_CODE", "MODEL", ["meta:x"]),
                _signal("B_CODE", "MODEL", ["doc:made-up#L1"]),
            ],
            frozenset({"meta:x"}),
        )
        assert [s.code for s in kept] == ["A_CODE"]
        assert dropped == 1

    def test_rule_signals_win_over_model_duplicates(self) -> None:
        merged = dedupe_signals(
            [
                _signal("AMOUNT_MISMATCH", "MODEL", ["meta:x"]),
                _signal("AMOUNT_MISMATCH", "RULE", ["meta:y"]),
            ]
        )
        assert len(merged) == 1
        assert merged[0].origin == "RULE"

    def test_dedupe_actions_is_case_and_space_insensitive(self) -> None:
        action = AnalystAction(
            action="Request invoice.", rationale="r", priority=Level.LOW, evidence_refs=["meta:x"]
        )
        twin = action.model_copy(update={"action": "request   INVOICE."})
        assert len(dedupe_actions([action, twin])) == 1

    def test_markdown_includes_notice_and_evidence(self, result_fixture: dict[str, object]) -> None:
        markdown = render_markdown(InvestigationResult.model_validate(result_fixture))
        assert ADVISORY_NOTICE in markdown
        assert "`meta:claimed_amount`" in markdown
        assert "## Potential anomaly signals" in markdown
        assert "Human review required: **yes**" in markdown
