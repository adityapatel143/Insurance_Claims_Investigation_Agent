"""Lambda handler tests: service construction is replaced; request/response mapping is real."""

import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from claims_investigator.errors import DependencyUnavailableError, ToolArgumentError
from claims_investigator.handlers import gateway_tools, intake, orchestrator, status, upload
from claims_investigator.models.api import ClaimAccepted, JobStatusResponse, UploadResponse
from claims_investigator.models.jobs import JobStatus
from claims_investigator.services.dispatch import DispatchOutcome
from claims_investigator.tools.schemas import UpdateJobStatusResult
from tests.fakes import CLAIM_ID, PRINCIPAL, FixedClock, make_submission

CLOCK = FixedClock()


def api_event(
    body: Any = None,
    *,
    principal: str | None = PRINCIPAL,
    headers: dict[str, str] | None = None,
    path: dict[str, str] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {"requestId": "req-1"}
    if principal:
        context["authorizer"] = {"iam": {"userArn": principal}}
    return {
        "version": "2.0",
        "headers": headers or {},
        "requestContext": context,
        "pathParameters": path,
        "body": None if body is None else json.dumps(body),
        "isBase64Encoded": False,
    }


class StubIntake:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def submit(self, submission: Any, principal: str, correlation_id: str) -> ClaimAccepted:
        self.calls.append((principal, correlation_id))
        if self.error:
            raise self.error
        job_id = uuid4()
        return ClaimAccepted(
            job_id=job_id,
            claim_id=submission.claim_id,
            correlation_id=correlation_id,
            status=JobStatus.QUEUED,
            status_url=f"/claims/{submission.claim_id}/jobs/{job_id}",
        )


class TestIntakeHandler:
    def test_accepts_valid_submission(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub = StubIntake()
        monkeypatch.setattr(intake, "_service", lambda: stub)
        body = make_submission().model_dump(mode="json")
        response = intake.handler(
            api_event(body, headers={"x-correlation-id": "corr-client-0001"}), None
        )

        assert response["statusCode"] == 202
        assert response["headers"]["x-correlation-id"] == "corr-client-0001"
        assert response["headers"]["cache-control"] == "no-store"
        assert json.loads(response["body"])["status"] == "QUEUED"
        assert stub.calls == [(PRINCIPAL, "corr-client-0001")]

    def test_invalid_body_returns_400_without_echoing_input(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(intake, "_service", StubIntake)
        body = {
            **make_submission().model_dump(mode="json"),
            "incident_description": "",
            "secret_note": "SENSITIVE",  # pragma: allowlist secret
        }
        response = intake.handler(api_event(body), None)
        payload = json.loads(response["body"])
        assert response["statusCode"] == 400
        assert payload["code"] == "VALIDATION_ERROR"
        assert "SENSITIVE" not in response["body"]

    def test_malformed_json_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(intake, "_service", StubIntake)
        event = api_event()
        event["body"] = "{not json"
        assert intake.handler(event, None)["statusCode"] == 400

    def test_missing_iam_identity_returns_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(intake, "_service", StubIntake)
        response = intake.handler(api_event({}, principal=None), None)
        assert response["statusCode"] == 403

    def test_invalid_correlation_header_is_replaced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub = StubIntake()
        monkeypatch.setattr(intake, "_service", lambda: stub)
        body = make_submission().model_dump(mode="json")
        response = intake.handler(api_event(body, headers={"x-correlation-id": "<script>"}), None)
        assert response["headers"]["x-correlation-id"] != "<script>"

    def test_dependency_error_maps_to_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            intake, "_service", lambda: StubIntake(DependencyUnavailableError("sqs down"))
        )
        response = intake.handler(api_event(make_submission().model_dump(mode="json")), None)
        assert response["statusCode"] == 503

    def test_unexpected_error_is_generic_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            intake, "_service", lambda: StubIntake(RuntimeError("table arn:aws:dynamodb:..."))
        )
        response = intake.handler(api_event(make_submission().model_dump(mode="json")), None)
        assert response["statusCode"] == 500
        assert "arn:aws" not in response["body"]


def test_upload_handler_returns_201(monkeypatch: pytest.MonkeyPatch) -> None:
    doc_id = uuid4()
    stub = SimpleNamespace(
        create_upload=lambda request: UploadResponse(
            claim_id=request.claim_id,
            document_id=doc_id,
            object_key=f"intake/{request.claim_id}/{doc_id}/{request.file_name}",
            upload_url="https://example.invalid/upload",
            upload_fields={"key": "k"},
            content_type=request.content_type,
            max_size_bytes=10,
            expires_at=CLOCK(),
        )
    )
    monkeypatch.setattr(upload, "_service", lambda: stub)
    body = {"claim_id": CLAIM_ID, "file_name": "claim_form.txt", "content_type": "text/plain"}
    response = upload.handler(api_event(body), None)
    assert response["statusCode"] == 201
    assert json.loads(response["body"])["document_id"] == str(doc_id)


def test_status_handler_validates_path_and_passes_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, Any, str]] = []

    def get_status(claim_id: str, job_id: Any, principal: str) -> JobStatusResponse:
        seen.append((claim_id, job_id, principal))
        return JobStatusResponse(
            job_id=job_id,
            claim_id=claim_id,
            correlation_id="corr-synthetic-0001",
            status=JobStatus.PROCESSING,
            created_at=CLOCK(),
            updated_at=CLOCK(),
        )

    monkeypatch.setattr(status, "_service", lambda: SimpleNamespace(get_status=get_status))
    job_id = uuid4()
    ok = status.handler(api_event(path={"claim_id": CLAIM_ID, "job_id": str(job_id)}), None)
    bad = status.handler(api_event(path={"claim_id": CLAIM_ID, "job_id": "nope"}), None)
    assert ok["statusCode"] == 200
    assert "report_url" not in json.loads(ok["body"])
    assert seen == [(CLAIM_ID, job_id, PRINCIPAL)]
    assert bad["statusCode"] == 400


class TestOrchestratorHandler:
    def _record(self, message_id: str, body: str, receive_count: int = 1) -> dict[str, Any]:
        return {
            "messageId": message_id,
            "body": body,
            "attributes": {"ApproximateReceiveCount": str(receive_count)},
        }

    def test_partial_batch_failures(
        self, monkeypatch: pytest.MonkeyPatch, message_fixture: dict[str, Any]
    ) -> None:
        outcomes = iter(
            [
                DispatchOutcome.DISPATCHED,
                DependencyUnavailableError("throttled"),
                DispatchOutcome.SKIPPED,
            ]
        )

        def dispatch(message: Any, receive_count: int) -> DispatchOutcome:
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(orchestrator, "_service", lambda: SimpleNamespace(dispatch=dispatch))
        good = json.dumps(message_fixture)
        event = {
            "Records": [
                self._record("m-1", good),
                self._record("m-2", good, receive_count=2),
                self._record("m-3", good),
                self._record("m-4", '{"schema_version": "9.9"}'),
            ]
        }
        response = orchestrator.handler(event, None)
        assert response == {
            "batchItemFailures": [{"itemIdentifier": "m-2"}, {"itemIdentifier": "m-4"}]
        }

    def test_empty_batch(self) -> None:
        assert orchestrator.handler({"Records": []}, None) == {"batchItemFailures": []}


class TestGatewayToolsHandler:
    @staticmethod
    def _context(tool: str) -> Any:
        custom = {
            "bedrockAgentCoreToolName": f"claims-tools___{tool}",
            "bedrockAgentCoreAwsRequestId": "r-1",
        }
        return SimpleNamespace(client_context=SimpleNamespace(custom=custom))

    def test_strips_target_prefix(self) -> None:
        assert (
            gateway_tools.tool_name_from(self._context("update_job_status")) == "update_job_status"
        )
        assert gateway_tools.tool_name_from(SimpleNamespace(client_context=None)) == ""

    def test_success_envelope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        def dispatch(tool: str, args: dict[str, Any]) -> UpdateJobStatusResult:
            calls.append(tool)
            return UpdateJobStatusResult(status=JobStatus.PROCESSING, changed=True)

        monkeypatch.setattr(
            gateway_tools, "_dispatcher", lambda: SimpleNamespace(dispatch=dispatch)
        )
        response = gateway_tools.handler(
            {"correlation_id": "corr-synthetic-0001"}, self._context("update_job_status")
        )
        assert response == {"ok": True, "result": {"status": "PROCESSING", "changed": True}}
        assert calls == ["update_job_status"]

    @pytest.mark.parametrize(
        ("error", "code"),
        [
            (ToolArgumentError("bad"), "INVALID_TOOL_ARGUMENTS"),
            (DependencyUnavailableError("down"), "DEPENDENCY_UNAVAILABLE"),
            (RuntimeError("secret detail"), "INTERNAL_ERROR"),
        ],
    )
    def test_error_envelopes(
        self, monkeypatch: pytest.MonkeyPatch, error: Exception, code: str
    ) -> None:
        def dispatch(tool: str, args: dict[str, Any]) -> Any:
            raise error

        monkeypatch.setattr(
            gateway_tools, "_dispatcher", lambda: SimpleNamespace(dispatch=dispatch)
        )
        response = gateway_tools.handler({}, self._context("get_policy_guidance"))
        assert response["ok"] is False
        assert response["error"]["code"] == code
        assert "secret detail" not in json.dumps(response)
