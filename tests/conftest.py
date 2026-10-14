"""Test configuration: isolate from real AWS credentials, config, and metadata endpoints."""

import json
from typing import Any

import pytest

from tests.fakes import FIXTURES, World

FAKE_AWS_ENV = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",  # pragma: allowlist secret
    "AWS_SESSION_TOKEN": "testing",
    "AWS_REGION": "us-east-1",
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_EC2_METADATA_DISABLED": "true",
    "AWS_CONFIG_FILE": "/dev/null",
    "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
}


@pytest.fixture(autouse=True)
def _isolated_aws_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("integration"):
        return
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    for key, value in FAKE_AWS_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CLAIMS_ENVIRONMENT", "dev")
    monkeypatch.setenv("CLAIMS_APP_NAME", "claims-investigator")


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def result_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "investigation_result.json").read_text())
    return data


@pytest.fixture
def message_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "investigation_message.json").read_text())
    return data


@pytest.fixture
def no_metrics(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, float]]:
    emitted: list[tuple[str, float]] = []
    monkeypatch.setattr(
        "claims_investigator.metrics.emit",
        lambda name, value, unit="Count", **dims: emitted.append((name, value)),
    )
    return emitted
