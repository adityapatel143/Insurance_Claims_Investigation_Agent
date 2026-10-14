from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from claims_investigator.models.api import ClaimSubmission, JobStatusPath, UploadRequest
from claims_investigator.models.common import ensure_advisory_language
from claims_investigator.models.jobs import JobStatus, can_transition
from claims_investigator.models.result import ADVISORY_NOTICE, InvestigationResult
from tests.fakes import make_submission


class TestClaimSubmission:
    def test_valid_submission(self) -> None:
        submission = make_submission()
        assert submission.claim_id == "CLM-SYN-0001"
        assert len(submission.documents) == 3

    def test_rejects_future_dates(self) -> None:
        future = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
        with pytest.raises(ValidationError, match="future"):
            make_submission(incident_date=future)

    def test_rejects_object_key_for_another_claim(self) -> None:
        data = make_submission().model_dump(mode="json")
        data["documents"][0]["object_key"] = data["documents"][0]["object_key"].replace(
            "CLM-SYN-0001", "CLM-SYN-9999"
        )
        with pytest.raises(ValidationError, match="object_key"):
            ClaimSubmission.model_validate(data)

    def test_rejects_nested_path_in_object_key(self) -> None:
        data = make_submission().model_dump(mode="json")
        data["documents"][0]["object_key"] += "/../escape.txt"
        with pytest.raises(ValidationError):
            ClaimSubmission.model_validate(data)

    def test_rejects_duplicate_documents(self) -> None:
        data = make_submission().model_dump(mode="json")
        data["documents"].append(data["documents"][0])
        with pytest.raises(ValidationError, match="unique"):
            ClaimSubmission.model_validate(data)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("claimed_amount", "-1"),
            ("claimed_amount", "1.001"),
            ("currency", "usd"),
            ("claim_id", "bad id"),
            ("claim_type", "HEALTH"),
            ("incident_description", ""),
        ],
    )
    def test_rejects_invalid_fields(self, field: str, value: Any) -> None:
        with pytest.raises(ValidationError):
            make_submission(**{field: value})

    def test_rejects_unknown_fields(self) -> None:
        data = make_submission().model_dump(mode="json")
        data["approved"] = True
        with pytest.raises(ValidationError, match="Extra inputs"):
            ClaimSubmission.model_validate(data)

    def test_allows_reported_before_incident_for_downstream_review(self) -> None:
        submission = make_submission(incident_date="2025-05-04", reported_date="2025-05-02")
        assert submission.reported_date < submission.incident_date


class TestUploadRequest:
    def test_normalizes_content_type(self) -> None:
        request = UploadRequest(
            claim_id="CLM-SYN-0001", file_name="a.txt", content_type="TEXT/PLAIN"
        )
        assert request.content_type == "text/plain"

    @pytest.mark.parametrize("name", ["../etc/passwd", "a/b.txt", ".hidden", "x" * 200])
    def test_rejects_unsafe_file_names(self, name: str) -> None:
        with pytest.raises(ValidationError):
            UploadRequest(claim_id="CLM-SYN-0001", file_name=name, content_type="text/plain")


def test_status_path_requires_uuid() -> None:
    with pytest.raises(ValidationError):
        JobStatusPath.model_validate({"claim_id": "CLM-SYN-0001", "job_id": "not-a-uuid"})
    path = JobStatusPath.model_validate({"claim_id": "CLM-SYN-0001", "job_id": str(uuid4())})
    assert path.claim_id == "CLM-SYN-0001"


class TestStatusTransitions:
    @pytest.mark.parametrize(
        ("current", "target", "allowed"),
        [
            (JobStatus.QUEUED, JobStatus.PROCESSING, True),
            (JobStatus.QUEUED, JobStatus.FAILED, True),
            (JobStatus.QUEUED, JobStatus.COMPLETED, False),
            (JobStatus.PROCESSING, JobStatus.COMPLETED, True),
            (JobStatus.PROCESSING, JobStatus.REVIEW_REQUIRED, True),
            (JobStatus.PROCESSING, JobStatus.QUEUED, False),
            (JobStatus.COMPLETED, JobStatus.FAILED, False),
            (JobStatus.FAILED, JobStatus.PROCESSING, False),
        ],
    )
    def test_transition_map(self, current: JobStatus, target: JobStatus, allowed: bool) -> None:
        assert can_transition(current, target) is allowed

    def test_terminal_states(self) -> None:
        assert JobStatus.FAILED.is_terminal
        assert not JobStatus.PROCESSING.is_terminal


class TestAdvisoryLanguage:
    @pytest.mark.parametrize(
        "text",
        [
            "The claimant is fraudulent.",
            "We approve the claim.",
            "Deny this claim.",
            "The claimant is not eligible for payment.",
            "The diagnosis is whiplash.",
            "The customer committed fraud.",
        ],
    )
    def test_rejects_prohibited_wording(self, text: str) -> None:
        with pytest.raises(ValueError, match="prohibited"):
            ensure_advisory_language(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Potential anomaly signal: amounts differ and require review.",
            "Request the itemised repair invoice.",
        ],
    )
    def test_accepts_advisory_wording(self, text: str) -> None:
        assert ensure_advisory_language(text) == text


class TestInvestigationResult:
    def test_fixture_is_valid(self, result_fixture: dict[str, Any]) -> None:
        result = InvestigationResult.model_validate(result_fixture)
        assert result.advisory_notice == ADVISORY_NOTICE
        assert result.schema_version == "1.0"

    def test_rejects_unknown_evidence_reference(self, result_fixture: dict[str, Any]) -> None:
        result_fixture["anomaly_signals"][0]["evidence_refs"] = ["doc:invented#L99"]
        with pytest.raises(ValidationError, match="unknown evidence ids"):
            InvestigationResult.model_validate(result_fixture)

    def test_status_must_match_review_flag(self, result_fixture: dict[str, Any]) -> None:
        result_fixture["status"] = "COMPLETED"
        with pytest.raises(ValidationError, match="REVIEW_REQUIRED"):
            InvestigationResult.model_validate(result_fixture)

    def test_review_requires_reasons(self, result_fixture: dict[str, Any]) -> None:
        result_fixture["review_reasons"] = []
        with pytest.raises(ValidationError, match="review_reasons"):
            InvestigationResult.model_validate(result_fixture)

    def test_failed_is_not_a_result_status(self, result_fixture: dict[str, Any]) -> None:
        result_fixture["status"] = "FAILED"
        with pytest.raises(ValidationError):
            InvestigationResult.model_validate(result_fixture)

    def test_advisory_notice_cannot_be_altered(self, result_fixture: dict[str, Any]) -> None:
        result_fixture["advisory_notice"] = "Approved."
        with pytest.raises(ValidationError, match="advisory_notice"):
            InvestigationResult.model_validate(result_fixture)

    def test_rejects_fraud_label_in_summary(self, result_fixture: dict[str, Any]) -> None:
        result_fixture["executive_summary"] = "The claimant is fraudulent."
        with pytest.raises(ValidationError):
            InvestigationResult.model_validate(result_fixture)
