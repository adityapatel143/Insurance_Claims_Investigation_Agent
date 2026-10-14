"""Environment-driven configuration; each component loads only the settings it needs."""

from typing import Annotated, Literal

from pydantic import AliasChoices, Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
MAX_UPLOAD_CEILING_BYTES = 50 * 1024 * 1024


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLAIMS_", frozen=True, extra="ignore")

    environment: Literal["dev", "prod"]
    app_name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{2,31}$")]
    aws_region: Annotated[
        str,
        Field(validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION"), min_length=1),
    ]
    log_level: LogLevel = "INFO"


class StorageSettings(BaseAppSettings):
    bucket_name: Annotated[str, Field(min_length=3, max_length=63)]


class JobStoreSettings(BaseAppSettings):
    jobs_table_name: Annotated[str, Field(min_length=3, max_length=255)]


class UploadPolicySettings(BaseAppSettings):
    max_upload_bytes: Annotated[int, Field(gt=0, le=MAX_UPLOAD_CEILING_BYTES)] = 10 * 1024 * 1024
    allowed_content_types: Annotated[tuple[str, ...], NoDecode] = (
        "text/plain",
        "text/csv",
        "application/json",
    )

    @field_validator("allowed_content_types", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip().lower() for item in value.split(",") if item.strip())
        return value

    @field_validator("allowed_content_types")
    @classmethod
    def _not_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("at least one content type must be allowed")
        return value


class UploadSettings(StorageSettings, UploadPolicySettings):
    presign_expiry_seconds: Annotated[int, Field(ge=60, le=900)] = 300


class IntakeSettings(StorageSettings, JobStoreSettings, UploadPolicySettings):
    queue_url: HttpUrl
    job_ttl_days: Annotated[int, Field(ge=0, le=3650)] = 0


class StatusSettings(StorageSettings, JobStoreSettings):
    report_url_expiry_seconds: Annotated[int, Field(ge=60, le=900)] = 300


class OrchestratorSettings(JobStoreSettings):
    agent_runtime_arn: Annotated[str, Field(pattern=r"^arn:aws[a-z-]*:bedrock-agentcore:")]
    agent_runtime_qualifier: str = "DEFAULT"
    max_receive_count: Annotated[int, Field(ge=1, le=10)] = 3
    dispatch_lease_seconds: Annotated[int, Field(ge=30, le=900)] = 120
    investigation_timeout_seconds: Annotated[int, Field(ge=60, le=28_800)] = 1800
    invoke_timeout_seconds: Annotated[int, Field(ge=5, le=60)] = 20


class ToolsSettings(StorageSettings, JobStoreSettings):
    opensearch_endpoint: HttpUrl
    opensearch_index: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,254}$")]
    embedding_model_id: Annotated[str, Field(min_length=1)]
    embedding_dimensions: Annotated[int, Field(gt=0, le=4096)]
    retrieval_top_k: Annotated[int, Field(ge=1, le=20)] = 5
    review_confidence_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.7


class RuntimeSettings(StorageSettings):
    model_id: Annotated[str, Field(min_length=1)]
    guardrail_id: Annotated[str, Field(min_length=1)]
    guardrail_version: Annotated[str, Field(pattern=r"^([0-9]{1,8}|DRAFT)$")]
    memory_id: Annotated[str, Field(min_length=1)]
    gateway_url: HttpUrl
    review_confidence_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.7
    model_timeout_seconds: Annotated[int, Field(ge=5, le=600)] = 120
    max_output_retries: Annotated[int, Field(ge=0, le=3)] = 1
    investigation_timeout_seconds: Annotated[int, Field(ge=60, le=28_800)] = 1800
    max_document_bytes: Annotated[int, Field(gt=0, le=MAX_UPLOAD_CEILING_BYTES)] = 1024 * 1024
    tool_timeout_seconds: Annotated[int, Field(ge=5, le=300)] = 30
