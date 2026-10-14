from typing import Any

import pytest
from pydantic import ValidationError

from claims_investigator.config import IntakeSettings, OrchestratorSettings, UploadSettings


@pytest.fixture
def storage_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAIMS_BUCKET_NAME", "example-bucket")


def test_upload_settings_parse_comma_separated_allowlist(
    monkeypatch: pytest.MonkeyPatch, storage_env: None
) -> None:
    monkeypatch.setenv("CLAIMS_ALLOWED_CONTENT_TYPES", "text/plain, Application/JSON ,")
    settings = UploadSettings()
    assert settings.allowed_content_types == ("text/plain", "application/json")
    assert settings.aws_region == "us-east-1"


def test_region_falls_back_to_default_region(
    monkeypatch: pytest.MonkeyPatch, storage_env: None
) -> None:
    monkeypatch.delenv("AWS_REGION")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    assert UploadSettings().aws_region == "eu-west-1"


def test_empty_allowlist_rejected(monkeypatch: pytest.MonkeyPatch, storage_env: None) -> None:
    monkeypatch.setenv("CLAIMS_ALLOWED_CONTENT_TYPES", " , ")
    with pytest.raises(ValidationError):
        UploadSettings()


def test_upload_size_ceiling(monkeypatch: pytest.MonkeyPatch, storage_env: None) -> None:
    monkeypatch.setenv("CLAIMS_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))
    with pytest.raises(ValidationError):
        UploadSettings()


def test_missing_required_settings_fail_fast() -> None:
    with pytest.raises(ValidationError):
        IntakeSettings()


@pytest.mark.parametrize(
    ("arn", "ok"),
    [
        ("arn:aws:bedrock-agentcore:us-east-1:111122223333:runtime/example", True),
        ("arn:aws:lambda:us-east-1:111122223333:function:x", False),
    ],
)
def test_orchestrator_runtime_arn_validation(
    monkeypatch: pytest.MonkeyPatch, arn: str, ok: bool
) -> None:
    env: dict[str, Any] = {"CLAIMS_JOBS_TABLE_NAME": "jobs", "CLAIMS_AGENT_RUNTIME_ARN": arn}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    if ok:
        assert OrchestratorSettings().agent_runtime_qualifier == "DEFAULT"
    else:
        with pytest.raises(ValidationError):
            OrchestratorSettings()
