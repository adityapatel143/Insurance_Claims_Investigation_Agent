"""JSON structured logging with correlation context and sensitive-key redaction."""

import json
import logging
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_CONTEXT: ContextVar[Mapping[str, str]] = ContextVar("log_context", default={})  # noqa: B039
_FIELDS_ATTR = "structured_fields"
REDACTED = "[REDACTED]"
SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "body",
        "content",
        "description",
        "document",
        "excerpt",
        "incident_description",
        "narrative",
        "password",
        "payload",
        "prompt",
        "secret",
        "text",
        "token",
        "upload_fields",
        "upload_url",
        "report_url",
    }
)


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(k): REDACTED if str(k).lower() in SENSITIVE_KEYS else _sanitize(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **_CONTEXT.get(),
        }
        entry.update(_sanitize(getattr(record, _FIELDS_ATTR, {})))
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception_type"] = record.exc_info[0].__name__
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    logger.log(level, event, extra={_FIELDS_ATTR: fields})


@contextmanager
def log_context(**fields: str) -> Iterator[None]:
    token = _CONTEXT.set({**_CONTEXT.get(), **fields})
    try:
        yield
    finally:
        _CONTEXT.reset(token)
