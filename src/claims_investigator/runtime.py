"""AgentCore Runtime entrypoint: acknowledge immediately, investigate as a tracked async task."""

import logging
import threading
from dataclasses import dataclass
from functools import cache
from typing import Any

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from pydantic import ValidationError

from claims_investigator.agents.pipeline import InvestigationPipeline, PipelineSettings
from claims_investigator.config import RuntimeSettings
from claims_investigator.gateways.agentcore_memory import AgentCoreMemoryStore
from claims_investigator.gateways.aws import client_config
from claims_investigator.gateways.bedrock_model import StrandsStructuredModel
from claims_investigator.gateways.gateway_client import GatewayToolClient, build_mcp_client
from claims_investigator.gateways.s3 import S3ObjectStore
from claims_investigator.logging import configure_logging, get_logger, log_context, log_event
from claims_investigator.models.messages import RuntimeInvocation
from claims_investigator.services.memory import MemoryService

app = BedrockAgentCoreApp()
_LOG = get_logger(__name__)
_ACTIVE_JOBS: set[str] = set()
_ACTIVE_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class _Components:
    settings: RuntimeSettings
    store: S3ObjectStore
    model: StrandsStructuredModel
    memory: MemoryService


@cache
def _components() -> _Components:
    settings = RuntimeSettings()
    configure_logging(settings.log_level)
    region = settings.aws_region
    return _Components(
        settings=settings,
        store=S3ObjectStore(
            boto3.client("s3", region_name=region, config=client_config()), settings.bucket_name
        ),
        model=StrandsStructuredModel(
            model_id=settings.model_id,
            guardrail_id=settings.guardrail_id,
            guardrail_version=settings.guardrail_version,
            region=region,
            timeout_seconds=settings.model_timeout_seconds,
            max_output_retries=settings.max_output_retries,
        ),
        memory=MemoryService(
            AgentCoreMemoryStore(
                boto3.client("bedrock-agentcore", region_name=region, config=client_config()),
                settings.memory_id,
            )
        ),
    )


def _investigate(invocation: RuntimeInvocation, task_id: int) -> None:
    job_key = str(invocation.job_id)
    try:
        with log_context(
            correlation_id=invocation.correlation_id, job_id=job_key, claim_id=invocation.claim_id
        ):
            parts = _components()
            settings = parts.settings
            client = build_mcp_client(str(settings.gateway_url), settings.aws_region)
            with GatewayToolClient(client, settings.tool_timeout_seconds) as tools:
                InvestigationPipeline(
                    tools,
                    parts.store,
                    parts.model,
                    parts.memory,
                    settings=PipelineSettings(
                        review_confidence_threshold=settings.review_confidence_threshold,
                        max_document_bytes=settings.max_document_bytes,
                        investigation_timeout_seconds=settings.investigation_timeout_seconds,
                    ),
                ).run(invocation)
    except Exception as exc:
        # Gateway unreachable: status cannot be written; the job fails at its processing deadline.
        log_event(_LOG, logging.ERROR, "investigation_aborted", exception_type=type(exc).__name__)
    finally:
        app.complete_async_task(task_id)
        with _ACTIVE_LOCK:
            _ACTIVE_JOBS.discard(job_key)


@app.entrypoint
def invoke(payload: dict[str, Any]) -> dict[str, str]:
    try:
        invocation = RuntimeInvocation.model_validate(payload)
    except ValidationError:
        raise ValueError("invalid invocation payload") from None
    job_key = str(invocation.job_id)
    with _ACTIVE_LOCK:
        if job_key in _ACTIVE_JOBS:
            return {"status": "ALREADY_RUNNING", "job_id": job_key}
        _ACTIVE_JOBS.add(job_key)
    task_id = app.add_async_task("claims_investigation", {"job_id": job_key})
    threading.Thread(
        target=_investigate, args=(invocation, task_id), name=f"job-{job_key}", daemon=True
    ).start()
    return {"status": "ACCEPTED", "job_id": job_key}


if __name__ == "__main__":
    app.run()
