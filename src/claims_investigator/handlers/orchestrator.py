"""Lambda: SQS investigation queue consumer with partial batch failure reporting."""

import logging
from functools import cache
from typing import Any

import boto3
from pydantic import ValidationError

from claims_investigator import metrics
from claims_investigator.config import OrchestratorSettings
from claims_investigator.gateways.agentcore_runtime import AgentCoreRuntimeInvoker
from claims_investigator.gateways.aws import client_config
from claims_investigator.gateways.dynamodb import DynamoJobRepository
from claims_investigator.logging import configure_logging, get_logger, log_context, log_event
from claims_investigator.models.messages import InvestigationMessage
from claims_investigator.services.dispatch import DispatchPolicy, DispatchService
from claims_investigator.services.jobs import JobService

_LOG = get_logger(__name__)


@cache
def _service() -> DispatchService:
    settings = OrchestratorSettings()
    configure_logging(settings.log_level)
    region = settings.aws_region
    repository = DynamoJobRepository(
        boto3.resource("dynamodb", region_name=region, config=client_config()).Table(
            settings.jobs_table_name
        )
    )
    agentcore = boto3.client(
        "bedrock-agentcore",
        region_name=region,
        config=client_config(read_timeout=settings.invoke_timeout_seconds, max_attempts=2),
    )
    return DispatchService(
        JobService(repository),
        repository,
        AgentCoreRuntimeInvoker(
            agentcore, settings.agent_runtime_arn, settings.agent_runtime_qualifier
        ),
        DispatchPolicy(
            lease_seconds=settings.dispatch_lease_seconds,
            investigation_timeout_seconds=settings.investigation_timeout_seconds,
            max_receive_count=settings.max_receive_count,
        ),
    )


def handler(event: dict[str, Any], _context: Any) -> dict[str, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        message_id = str(record.get("messageId", ""))
        if not _process(record):
            failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}


def _process(record: dict[str, Any]) -> bool:
    """Return True when the record can be deleted from the queue."""
    with log_context(message_id=str(record.get("messageId", ""))):
        try:
            message = InvestigationMessage.model_validate_json(record.get("body", ""))
        except ValidationError:
            log_event(_LOG, logging.ERROR, "dispatch_message_invalid")
            metrics.emit("DispatchInvalidMessage", 1)
            return False
        receive_count = int(record.get("attributes", {}).get("ApproximateReceiveCount", "1"))
        with log_context(
            correlation_id=message.correlation_id,
            job_id=str(message.job_id),
            claim_id=message.claim_id,
        ):
            try:
                outcome = _service().dispatch(message, receive_count)
            except Exception as exc:
                log_event(
                    _LOG,
                    logging.ERROR,
                    "dispatch_failed",
                    exception_type=type(exc).__name__,
                    receive_count=receive_count,
                )
                metrics.emit("DispatchFailed", 1)
                return False
            log_event(_LOG, logging.INFO, "dispatch_completed", outcome=str(outcome))
            metrics.emit(f"Dispatch{outcome.title()}", 1)
            return True
