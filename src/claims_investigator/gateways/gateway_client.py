"""AgentCore Gateway MCP client with SigV4 (AWS_IAM inbound auth) for the approved tools."""

import json
import time
from collections.abc import Generator
from datetime import datetime, timedelta
from types import TracebackType
from typing import Any, Self
from uuid import uuid4

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from strands.tools.mcp import MCPClient
from strands.tools.mcp.mcp_types import MCPToolResult

from claims_investigator.errors import DependencyUnavailableError, ToolCallError
from claims_investigator.models.common import ClaimType
from claims_investigator.models.findings import RetrievedChunk
from claims_investigator.models.jobs import FailureCategory, JobStatus
from claims_investigator.tools import schemas as s

GATEWAY_SIGNING_NAME = "bedrock-agentcore"
TOOL_NAME_DELIMITER = "___"
_UNSIGNED_HEADERS = frozenset({"connection"})


class SigV4HttpxAuth(httpx.Auth):
    requires_request_body = True

    def __init__(self, session: boto3.Session, region: str) -> None:
        self._session = session
        self._region = region

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        credentials = self._session.get_credentials()
        if credentials is None:
            raise DependencyUnavailableError("no AWS credentials available for Gateway calls")
        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content,
            headers={
                k: v for k, v in request.headers.items() if k.lower() not in _UNSIGNED_HEADERS
            },
        )
        SigV4Auth(
            credentials.get_frozen_credentials(), GATEWAY_SIGNING_NAME, self._region
        ).add_auth(aws_request)
        request.headers.update(dict(aws_request.headers.items()))
        yield request


def build_mcp_client(gateway_url: str, region: str, startup_timeout: int = 30) -> MCPClient:
    return MCPClient(
        url=gateway_url,
        auth_provider=SigV4HttpxAuth(boto3.Session(), region),
        startup_timeout=startup_timeout,
    )


class GatewayToolClient:
    """Implements `InvestigationTools`; use as a context manager for the MCP session lifetime."""

    def __init__(self, client: MCPClient, timeout_seconds: int, max_attempts: int = 3) -> None:
        self._client = client
        self._timeout = timedelta(seconds=timeout_seconds)
        self._max_attempts = max_attempts
        self._names: dict[str, str] = {}

    def __enter__(self) -> Self:
        self._client.__enter__()
        self._names = self._resolve_names()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._client.__exit__(exc_type, exc, tb)

    def mark_processing(self, request: s.ToolRequest, deadline: datetime) -> None:
        self._call(
            s.UPDATE_JOB_STATUS,
            {
                **_ids(request),
                "status": str(JobStatus.PROCESSING),
                "processing_deadline": deadline.isoformat(),
            },
        )

    def mark_failed(self, request: s.ToolRequest, category: FailureCategory) -> None:
        self._call(
            s.UPDATE_JOB_STATUS,
            {**_ids(request), "status": str(JobStatus.FAILED), "failure_category": str(category)},
        )

    def get_claim_document_metadata(self, request: s.ToolRequest) -> list[s.DocumentMetadata]:
        data = self._call(s.GET_CLAIM_DOCUMENT_METADATA, _ids(request))
        return s.DocumentMetadataResult.model_validate(data).documents

    def get_policy_guidance(
        self, request: s.ToolRequest, claim_type: ClaimType, query: str
    ) -> list[RetrievedChunk]:
        return self._retrieve(s.GET_POLICY_GUIDANCE, request, claim_type, query)

    def search_similar_claims(
        self, request: s.ToolRequest, claim_type: ClaimType, query: str
    ) -> list[RetrievedChunk]:
        return self._retrieve(s.SEARCH_SIMILAR_CLAIMS, request, claim_type, query)

    def persist_investigation_findings(
        self, request: s.ToolRequest, result_json: str, report_markdown: str
    ) -> s.PersistFindingsResult:
        data = self._call(
            s.PERSIST_INVESTIGATION_FINDINGS,
            {**_ids(request), "result_json": result_json, "report_markdown": report_markdown},
        )
        return s.PersistFindingsResult.model_validate(data)

    def _retrieve(
        self, tool: str, request: s.ToolRequest, claim_type: ClaimType, query: str
    ) -> list[RetrievedChunk]:
        data = self._call(tool, {**_ids(request), "claim_type": str(claim_type), "query": query})
        return s.RetrievalResult.model_validate(data).chunks

    def _resolve_names(self) -> dict[str, str]:
        available: list[str] = []
        token: str | None = None
        while True:
            page = self._client.list_tools_sync(pagination_token=token)
            available += [tool.tool_name for tool in page]
            token = page.pagination_token
            if not token:
                break
        names = {}
        for tool in s.TOOL_NAMES:
            matches = [n for n in available if n == tool or n.endswith(TOOL_NAME_DELIMITER + tool)]
            if len(matches) != 1:
                raise ToolCallError(f"gateway tool {tool} not uniquely available")
            names[tool] = matches[0]
        return names

    def _call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(1, self._max_attempts + 1):
            result = self._client.call_tool_sync(
                tool_use_id=str(uuid4()),
                name=self._names[tool],
                arguments=arguments,
                read_timeout_seconds=self._timeout,
            )
            envelope = _envelope(result)
            if envelope.ok:
                return envelope.result or {}
            code = envelope.error.code if envelope.error else "UNKNOWN"
            if code != DependencyUnavailableError.code or attempt == self._max_attempts:
                raise ToolCallError(f"{tool} failed with {code}")
            time.sleep(2 ** (attempt - 1))
        raise ToolCallError(f"{tool} failed")


def _ids(request: s.ToolRequest) -> dict[str, Any]:
    return request.model_dump(mode="json")


def _envelope(result: MCPToolResult) -> s.ToolEnvelope:
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and "ok" in structured:
        return s.ToolEnvelope.model_validate(structured)
    for item in result.get("content", []):
        text = item.get("text")
        if text:
            try:
                return s.ToolEnvelope.model_validate(json.loads(text))
            except (ValueError, TypeError):
                break
    raise ToolCallError("tool returned an unreadable response")
