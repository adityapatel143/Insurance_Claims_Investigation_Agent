"""Shared helpers for API Gateway HTTP API (payload format 2.0) handlers."""

import base64
import json
import logging
import re
from collections.abc import Callable, Mapping
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from claims_investigator.errors import (
    ClaimsInvestigatorError,
    ForbiddenError,
    RequestValidationError,
)
from claims_investigator.logging import get_logger, log_context, log_event
from claims_investigator.models.api import ErrorResponse
from claims_investigator.services.memory import actor_id_for

_LOG = get_logger(__name__)
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
MAX_BODY_BYTES = 64 * 1024
ApiResult = tuple[int, BaseModel]


def principal_of(event: Mapping[str, Any]) -> str:
    iam = ((event.get("requestContext") or {}).get("authorizer") or {}).get("iam") or {}
    principal = iam.get("userArn")
    if not isinstance(principal, str) or not principal:
        raise ForbiddenError("IAM caller identity is required")
    return principal


def correlation_id_of(event: Mapping[str, Any]) -> str:
    header = (event.get("headers") or {}).get("x-correlation-id", "")
    return header if _CORRELATION_ID.match(header) else str(uuid4())


def json_body(event: Mapping[str, Any]) -> Any:
    raw = event.get("body") or ""
    data = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode()
    if len(data) > MAX_BODY_BYTES:
        raise RequestValidationError("request body is too large")
    try:
        return json.loads(data or b"null")
    except json.JSONDecodeError as exc:
        raise RequestValidationError("request body must be valid JSON") from exc


def response(status: int, body: BaseModel, correlation_id: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "cache-control": "no-store",
            "x-correlation-id": correlation_id,
        },
        "body": body.model_dump_json(exclude_none=True),
    }


def run_api(
    event: Mapping[str, Any], route: str, action: Callable[[str, str], ApiResult]
) -> dict[str, Any]:
    """Run `action(principal, correlation_id)` and map errors to safe JSON responses."""
    correlation_id = correlation_id_of(event)
    request_id = str((event.get("requestContext") or {}).get("requestId", ""))
    with log_context(correlation_id=correlation_id, request_id=request_id, route=route):
        try:
            principal = principal_of(event)
            with log_context(actor_id=actor_id_for(principal)):
                status, body = action(principal, correlation_id)
            log_event(_LOG, logging.INFO, "api_request_completed", status=status)
            return response(status, body, correlation_id)
        except ValidationError as exc:
            details = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
            return _error(
                400, "VALIDATION_ERROR", "request validation failed", details, correlation_id
            )
        except ClaimsInvestigatorError as exc:
            return _error(exc.http_status, exc.code, exc.message, list(exc.details), correlation_id)
        except Exception as exc:
            log_event(_LOG, logging.ERROR, "api_request_failed", exception_type=type(exc).__name__)
            return _error(500, "INTERNAL_ERROR", "internal error", [], correlation_id)


def _error(
    status: int, code: str, message: str, details: list[str], correlation_id: str
) -> dict[str, Any]:
    log_event(_LOG, logging.WARNING, "api_request_rejected", status=status, code=code)
    body = ErrorResponse(code=code, message=message, correlation_id=correlation_id, details=details)
    return response(status, body, correlation_id)
