"""Lambda: POST /uploads -> presigned S3 POST for one claim document."""

from functools import cache
from typing import Any

import boto3
from botocore.config import Config

from claims_investigator.config import UploadSettings
from claims_investigator.gateways.aws import client_config
from claims_investigator.gateways.s3 import S3ObjectStore
from claims_investigator.handlers.http import ApiResult, json_body, run_api
from claims_investigator.logging import configure_logging
from claims_investigator.models.api import UploadRequest
from claims_investigator.services.uploads import UploadPolicy, UploadService


def s3_presign_config() -> Config:
    return client_config().merge(
        Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
    )


@cache
def _service() -> UploadService:
    settings = UploadSettings()
    configure_logging(settings.log_level)
    s3 = boto3.client("s3", region_name=settings.aws_region, config=s3_presign_config())
    return UploadService(
        S3ObjectStore(s3, settings.bucket_name),
        UploadPolicy(settings.max_upload_bytes, frozenset(settings.allowed_content_types)),
        settings.presign_expiry_seconds,
    )


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    def action(_principal: str, _correlation_id: str) -> ApiResult:
        request = UploadRequest.model_validate(json_body(event))
        return 201, _service().create_upload(request)

    return run_api(event, "POST /uploads", action)
