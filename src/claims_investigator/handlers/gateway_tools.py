"""Lambda: AgentCore Gateway target implementing the approved investigation tools."""

import logging
import re
import time
from functools import cache
from typing import Any

import boto3
from pydantic import ValidationError

from claims_investigator import metrics
from claims_investigator.config import ToolsSettings
from claims_investigator.errors import ClaimsInvestigatorError
from claims_investigator.gateways.aws import client_config
from claims_investigator.gateways.dynamodb import DynamoJobRepository
from claims_investigator.gateways.embeddings import BedrockEmbedder
from claims_investigator.gateways.opensearch import OpenSearchVectorSearch, build_client
from claims_investigator.gateways.s3 import S3ObjectStore
from claims_investigator.logging import configure_logging, get_logger, log_context, log_event
from claims_investigator.services.jobs import JobService
from claims_investigator.services.retrieval import RetrievalService
from claims_investigator.tools.dispatcher import ToolDispatcher
from claims_investigator.tools.schemas import ToolEnvelope, ToolError

_LOG = get_logger(__name__)
TOOL_NAME_DELIMITER = "___"
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


@cache
def _dispatcher() -> ToolDispatcher:
    settings = ToolsSettings()
    configure_logging(settings.log_level)
    region = settings.aws_region
    config = client_config()
    table = boto3.resource("dynamodb", region_name=region, config=config).Table(
        settings.jobs_table_name
    )
    search = OpenSearchVectorSearch(
        build_client(str(settings.opensearch_endpoint.host), region), settings.opensearch_index
    )
    embedder = BedrockEmbedder(
        boto3.client("bedrock-runtime", region_name=region, config=config),
        settings.embedding_model_id,
        settings.embedding_dimensions,
    )
    return ToolDispatcher(
        JobService(DynamoJobRepository(table)),
        S3ObjectStore(boto3.client("s3", region_name=region, config=config), settings.bucket_name),
        RetrievalService(search, embedder, settings.retrieval_top_k),
        settings.review_confidence_threshold,
    )


def tool_name_from(context: Any) -> str:
    """Gateway sends `${target}___${tool}` in the Lambda client context."""
    custom = getattr(getattr(context, "client_context", None), "custom", None) or {}
    full_name = str(custom.get("bedrockAgentCoreToolName", ""))
    return full_name.split(TOOL_NAME_DELIMITER, 1)[-1]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    tool = tool_name_from(context)
    custom = getattr(getattr(context, "client_context", None), "custom", None) or {}
    correlation_id = str(event.get("correlation_id", ""))
    started = time.perf_counter()
    error_code = None
    with log_context(
        tool=tool,
        gateway_request_id=str(custom.get("bedrockAgentCoreAwsRequestId", "")),
        correlation_id=correlation_id if _CORRELATION_ID.match(correlation_id) else "invalid",
    ):
        try:
            result = _dispatcher().dispatch(tool, event)
            envelope = ToolEnvelope(ok=True, result=result.model_dump(mode="json"))
        except ValidationError as exc:
            error_code = "INVALID_TOOL_ARGUMENTS"
            fields = ", ".join(".".join(map(str, e["loc"])) for e in exc.errors())
            envelope = _failure(error_code, f"invalid arguments: {fields}")
        except ClaimsInvestigatorError as exc:
            error_code = exc.code
            envelope = _failure(exc.code, exc.message)
        except Exception as exc:
            error_code = "INTERNAL_ERROR"
            log_event(_LOG, logging.ERROR, "tool_failed", exception_type=type(exc).__name__)
            envelope = _failure(error_code, "internal error")
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        log_event(
            _LOG,
            logging.INFO if envelope.ok else logging.WARNING,
            "tool_call",
            result_status="OK" if envelope.ok else "ERROR",
            error_category=error_code,
            latency_ms=latency_ms,
        )
        metrics.emit("ToolLatency", latency_ms, "Milliseconds", Tool=tool or "unknown")
        if not envelope.ok:
            metrics.emit("ToolErrors", 1, Tool=tool or "unknown")
    return envelope.model_dump(mode="json", exclude_none=True)


def _failure(code: str, message: str) -> ToolEnvelope:
    return ToolEnvelope(ok=False, error=ToolError(code=code, message=message))
