"""Shared boto3 client configuration and error translation."""

from typing import NoReturn

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from claims_investigator.errors import DependencyUnavailableError

_SERVER_ERROR = 500
_RETRYABLE_CODES = frozenset(
    {
        "InternalServerException",
        "ServiceUnavailableException",
        "ThrottlingException",
        "ProvisionedThroughputExceededException",
        "RequestLimitExceeded",
        "SlowDown",
        "TooManyRequestsException",
    }
)


def client_config(read_timeout: int = 10, max_attempts: int = 3) -> Config:
    """Bounded retries with exponential backoff and jitter (botocore `standard` mode)."""
    return Config(
        connect_timeout=3,
        read_timeout=read_timeout,
        retries={"mode": "standard", "total_max_attempts": max_attempts},
    )


def error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def is_retryable(exc: ClientError) -> bool:
    status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
    return error_code(exc) in _RETRYABLE_CODES or status >= _SERVER_ERROR


def raise_translated(exc: ClientError | BotoCoreError, action: str) -> NoReturn:
    if isinstance(exc, BotoCoreError) or is_retryable(exc):
        raise DependencyUnavailableError(f"{action} failed") from exc
    raise exc
