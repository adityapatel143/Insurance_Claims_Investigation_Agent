"""Runtime-side adapters (need the `agent` extra): Gateway MCP client and AgentCore entrypoint."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("strands")
pytest.importorskip("bedrock_agentcore")

import boto3
import httpx

from claims_investigator import runtime
from claims_investigator.errors import ToolCallError
from claims_investigator.gateways.gateway_client import (
    GatewayToolClient,
    SigV4HttpxAuth,
    _envelope,
)
from claims_investigator.tools import schemas as s
from tests.fakes import CORRELATION_ID, FixedClock, make_job, make_submission


class FakeMCP:
    def __init__(self, names: list[str], results: list[dict[str, Any]]) -> None:
        self.names = names
        self.results = results
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def list_tools_sync(self, pagination_token: str | None = None) -> Any:
        page = [SimpleNamespace(tool_name=n) for n in self.names]

        class Page(list[Any]):
            pagination_token = None

        return Page(page)

    def call_tool_sync(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((kwargs["name"], kwargs["arguments"]))
        return self.results.pop(0)

    def __enter__(self) -> "FakeMCP":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _text(envelope: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "toolUseId": "t", "content": [{"text": json.dumps(envelope)}]}


ALL_TOOLS = [f"claims-tools___{name}" for name in sorted(s.TOOL_NAMES)]
REQUEST = s.ToolRequest(
    job_id=make_job(make_submission(), FixedClock()).job_id,
    claim_id="CLM-SYN-0001",
    correlation_id=CORRELATION_ID,
)


class TestEnvelope:
    def test_prefers_structured_content(self) -> None:
        result = {
            "status": "success",
            "toolUseId": "t",
            "content": [],
            "structuredContent": {"ok": True, "result": {"x": 1}},
        }
        assert _envelope(result).result == {"x": 1}  # type: ignore[arg-type]

    def test_parses_text_content(self) -> None:
        assert _envelope(_text({"ok": False, "error": {"code": "C", "message": "m"}})).ok is False  # type: ignore[arg-type]

    def test_unreadable_response_raises(self) -> None:
        with pytest.raises(ToolCallError):
            _envelope({"status": "error", "toolUseId": "t", "content": [{"text": "boom"}]})  # type: ignore[arg-type]


class TestGatewayToolClient:
    def test_resolves_prefixed_names_and_calls_with_ids(self) -> None:
        mcp = FakeMCP(
            ALL_TOOLS, [_text({"ok": True, "result": {"status": "PROCESSING", "changed": True}})]
        )
        with GatewayToolClient(mcp, timeout_seconds=5) as tools:  # type: ignore[arg-type]
            tools.mark_processing(REQUEST, datetime(2025, 5, 5, tzinfo=UTC))
        name, args = mcp.calls[0]
        assert name == "claims-tools___update_job_status"
        assert args["status"] == "PROCESSING"
        assert args["correlation_id"] == CORRELATION_ID

    def test_missing_tool_fails_fast(self) -> None:
        with pytest.raises(ToolCallError, match="not uniquely available"):
            GatewayToolClient(FakeMCP(ALL_TOOLS[:-1], []), timeout_seconds=5).__enter__()  # type: ignore[arg-type]

    def test_retries_only_dependency_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "claims_investigator.gateways.gateway_client.time.sleep", lambda _: None
        )
        unavailable = _text(
            {"ok": False, "error": {"code": "DEPENDENCY_UNAVAILABLE", "message": "m"}}
        )
        ok = _text({"ok": True, "result": {"documents": []}})
        mcp = FakeMCP(ALL_TOOLS, [unavailable, ok])
        with GatewayToolClient(mcp, timeout_seconds=5) as tools:  # type: ignore[arg-type]
            assert tools.get_claim_document_metadata(REQUEST) == []
        assert len(mcp.calls) == 2

        invalid = _text({"ok": False, "error": {"code": "INVALID_TOOL_ARGUMENTS", "message": "m"}})
        mcp = FakeMCP(ALL_TOOLS, [invalid])
        with GatewayToolClient(mcp, timeout_seconds=5) as tools, pytest.raises(ToolCallError):  # type: ignore[arg-type]
            tools.get_claim_document_metadata(REQUEST)
        assert len(mcp.calls) == 1


def test_sigv4_auth_signs_with_agentcore_service() -> None:
    session = boto3.Session(
        aws_access_key_id="testing", aws_secret_access_key="testing", region_name="us-east-1"
    )
    request = httpx.Request(
        "POST",
        "https://example.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
        content=b"{}",
    )
    signed = next(SigV4HttpxAuth(session, "us-east-1").auth_flow(request))
    assert "/us-east-1/bedrock-agentcore/aws4_request" in signed.headers["authorization"]
    assert "x-amz-date" in signed.headers


class TestRuntimeEntrypoint:
    def _payload(self) -> dict[str, Any]:
        submission = make_submission()
        job = make_job(submission, FixedClock())
        return {
            "job_id": str(job.job_id),
            "claim_id": job.claim_id,
            "correlation_id": job.correlation_id,
            "submission_key": job.submission_key,
            "document_references": [d.model_dump(mode="json") for d in submission.documents],
            "actor_id": "a" * 64,
            "processing_deadline": "2025-05-05T10:30:00Z",
        }

    def test_invalid_payload_is_rejected_without_echo(self) -> None:
        with pytest.raises(ValueError, match="invalid invocation payload") as excinfo:
            runtime.invoke({"job_id": "secret-ish"})
        assert "secret-ish" not in str(excinfo.value)

    def test_accepts_once_per_job_and_tracks_async_task(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        started: list[str] = []

        def fake_investigate(invocation: Any, task_id: int) -> None:
            started.append(str(invocation.job_id))
            runtime.app.complete_async_task(task_id)

        monkeypatch.setattr(runtime, "_investigate", fake_investigate)
        monkeypatch.setattr(
            runtime.threading,
            "Thread",
            lambda target, args, name, daemon: SimpleNamespace(start=lambda: target(*args)),
        )
        payload = self._payload()
        runtime._ACTIVE_JOBS.add(payload["job_id"])
        try:
            assert runtime.invoke(payload)["status"] == "ALREADY_RUNNING"
        finally:
            runtime._ACTIVE_JOBS.discard(payload["job_id"])

        response = runtime.invoke(payload)
        assert response == {"status": "ACCEPTED", "job_id": payload["job_id"]}
        assert started == [payload["job_id"]]
        runtime._ACTIVE_JOBS.discard(payload["job_id"])
