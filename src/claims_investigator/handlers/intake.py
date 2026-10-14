"""Lambda: POST /claims -> validate, create job, enqueue, 202 Accepted."""

from functools import cache
from typing import Any

import boto3

from claims_investigator import metrics
from claims_investigator.config import IntakeSettings
from claims_investigator.gateways.aws import client_config
from claims_investigator.gateways.dynamodb import DynamoJobRepository
from claims_investigator.gateways.s3 import S3ObjectStore
from claims_investigator.gateways.sqs import SqsQueuePublisher
from claims_investigator.handlers.http import ApiResult, json_body, run_api
from claims_investigator.logging import configure_logging
from claims_investigator.models.api import ClaimSubmission
from claims_investigator.services.intake import IntakeService
from claims_investigator.services.jobs import JobService
from claims_investigator.services.uploads import UploadPolicy


@cache
def _service() -> IntakeService:
    settings = IntakeSettings()
    configure_logging(settings.log_level)
    config = client_config()
    region = settings.aws_region
    table = boto3.resource("dynamodb", region_name=region, config=config).Table(
        settings.jobs_table_name
    )
    return IntakeService(
        S3ObjectStore(boto3.client("s3", region_name=region, config=config), settings.bucket_name),
        JobService(DynamoJobRepository(table)),
        SqsQueuePublisher(
            boto3.client("sqs", region_name=region, config=config), str(settings.queue_url)
        ),
        UploadPolicy(settings.max_upload_bytes, frozenset(settings.allowed_content_types)),
        job_ttl_days=settings.job_ttl_days,
    )


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    def action(principal: str, correlation_id: str) -> ApiResult:
        submission = ClaimSubmission.model_validate(json_body(event))
        accepted = _service().submit(submission, principal, correlation_id)
        metrics.emit("ClaimsAccepted", 1)
        return 202, accepted

    return run_api(event, "POST /claims", action)
