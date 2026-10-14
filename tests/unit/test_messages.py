from typing import Any

import pytest
from pydantic import ValidationError

from claims_investigator.models.messages import InvestigationMessage, RuntimeInvocation


def test_message_round_trip(message_fixture: dict[str, Any]) -> None:
    message = InvestigationMessage.model_validate(message_fixture)
    again = InvestigationMessage.model_validate_json(message.model_dump_json())
    assert again == message
    assert again.schema_version == "1.0"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("attempt", 0),
        ("document_references", []),
        ("correlation_id", "x"),
        ("submitted_at", "2025-05-05T10:00:00"),
    ],
)
def test_message_rejects_invalid_values(
    message_fixture: dict[str, Any], field: str, value: Any
) -> None:
    message_fixture[field] = value
    with pytest.raises(ValidationError):
        InvestigationMessage.model_validate(message_fixture)


def test_message_rejects_unknown_fields(message_fixture: dict[str, Any]) -> None:
    message_fixture["claim_narrative"] = "should never travel through SQS"
    with pytest.raises(ValidationError):
        InvestigationMessage.model_validate(message_fixture)


def test_runtime_invocation_requires_hashed_actor(message_fixture: dict[str, Any]) -> None:
    payload = {k: v for k, v in message_fixture.items() if k not in {"submitted_at", "attempt"}}
    payload["processing_deadline"] = "2025-05-05T10:30:00Z"
    with pytest.raises(ValidationError):
        RuntimeInvocation.model_validate({**payload, "actor_id": "arn:aws:iam::1:user/x"})
    assert RuntimeInvocation.model_validate({**payload, "actor_id": "b" * 64}).actor_id == "b" * 64
