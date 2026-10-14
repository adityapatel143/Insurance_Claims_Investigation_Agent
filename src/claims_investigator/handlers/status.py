"""Lambda: GET /claims/{claim_id}/jobs/{job_id} -> job status."""

from functools import cache
from typing import Any

import boto3

from claims_investigator.config import StatusSettings
from claims_investigator.gateways.aws import client_config
from claims_investigator.gateways.dynamodb import DynamoJobRepository
from claims_investigator.gateways.s3 import S3ObjectStore
from claims_investigator.handlers.http import ApiResult, run_api
from claims_investigator.handlers.upload import s3_presign_config
from claims_investigator.logging import configure_logging
from claims_investigator.models.api import JobStatusPath
from claims_investigator.services.jobs import JobService
from claims_investigator.services.status import StatusService


@cache
def _service() -> StatusService:
    settings = StatusSettings()
    configure_logging(settings.log_level)
    region = settings.aws_region
    table = boto3.resource("dynamodb", region_name=region, config=client_config()).Table(
        settings.jobs_table_name
    )
    s3 = boto3.client("s3", region_name=region, config=s3_presign_config())
    return StatusService(
        JobService(DynamoJobRepository(table)),
        S3ObjectStore(s3, settings.bucket_name),
        settings.report_url_expiry_seconds,
    )


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    def action(principal: str, _correlation_id: str) -> ApiResult:
        path = JobStatusPath.model_validate(event.get("pathParameters") or {})
        return 200, _service().get_status(path.claim_id, path.job_id, principal)

    return run_api(event, "GET /claims/{claim_id}/jobs/{job_id}", action)
