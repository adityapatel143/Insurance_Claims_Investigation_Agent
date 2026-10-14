"""Contract tests: Gateway tool definitions, payload schemas, and Terraform <-> Python wiring."""

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from claims_investigator import config
from claims_investigator.gateways import agentcore_memory
from claims_investigator.models.messages import InvestigationMessage
from claims_investigator.models.result import InvestigationResult
from claims_investigator.tools import schemas as s

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"
GATEWAY_SCHEMA_KEYS = {"type", "properties", "required", "items", "description"}
REQUEST_MODELS: dict[str, type[BaseModel]] = {
    s.GET_CLAIM_DOCUMENT_METADATA: s.DocumentMetadataRequest,
    s.GET_POLICY_GUIDANCE: s.RetrievalRequest,
    s.SEARCH_SIMILAR_CLAIMS: s.RetrievalRequest,
    s.PERSIST_INVESTIGATION_FINDINGS: s.PersistFindingsRequest,
    s.UPDATE_JOB_STATUS: s.UpdateJobStatusRequest,
}


def _schema_keys(schema: dict[str, Any]) -> set[str]:
    keys = set(schema)
    for prop in schema.get("properties", {}).values():
        keys |= _schema_keys(prop)
    if "items" in schema:
        keys |= _schema_keys(schema["items"])
    return keys


class TestToolDefinitions:
    def test_exactly_the_approved_tools(self) -> None:
        names = [d["name"] for d in s.tool_definitions()]
        assert sorted(names) == sorted(s.TOOL_NAMES)
        assert len(names) == len(set(names))

    @pytest.mark.parametrize("definition", s.tool_definitions(), ids=lambda d: d["name"])
    def test_uses_only_gateway_supported_schema_keywords(self, definition: dict[str, Any]) -> None:
        assert set(definition) <= {"name", "description", "inputSchema", "outputSchema"}
        assert definition["description"]
        assert _schema_keys(definition["inputSchema"]) <= GATEWAY_SCHEMA_KEYS
        assert definition["inputSchema"]["type"] == "object"

    @pytest.mark.parametrize("definition", s.tool_definitions(), ids=lambda d: d["name"])
    def test_matches_pydantic_request_model(self, definition: dict[str, Any]) -> None:
        model = REQUEST_MODELS[definition["name"]]
        schema = definition["inputSchema"]
        assert set(schema["properties"]) == set(model.model_fields)
        required = {n for n, f in model.model_fields.items() if f.is_required()}
        assert set(schema["required"]) == required

    def test_every_tool_requires_job_scope(self) -> None:
        for definition in s.tool_definitions():
            assert {"job_id", "claim_id", "correlation_id"} <= set(
                definition["inputSchema"]["required"]
            )


class TestPayloadSchemas:
    def test_message_contract_fields(self) -> None:
        required = {
            "schema_version",
            "job_id",
            "claim_id",
            "correlation_id",
            "submitted_at",
            "document_references",
            "attempt",
        }
        assert required <= set(InvestigationMessage.model_fields)

    def test_result_contract_fields(self) -> None:
        required = {
            "schema_version",
            "job_id",
            "claim_id",
            "correlation_id",
            "status",
            "executive_summary",
            "evidence_summary",
            "missing_information",
            "anomaly_signals",
            "risk_indicators",
            "retrieved_sources",
            "recommended_analyst_actions",
            "confidence",
            "limitations",
            "human_review_required",
            "created_at",
            "completed_at",
        }
        assert required <= set(InvestigationResult.model_fields)

    def test_fixtures_validate(
        self, message_fixture: dict[str, Any], result_fixture: dict[str, Any]
    ) -> None:
        InvestigationMessage.model_validate(message_fixture)
        InvestigationResult.model_validate(result_fixture)


def _platform_env_vars() -> set[str]:
    text = (INFRA / "modules" / "platform" / "main.tf").read_text()
    return set(re.findall(r"\b(CLAIMS_[A-Z_]+)\s*=", text))


def _settings_env_vars(cls: type[config.BaseAppSettings]) -> set[str]:
    return {f"CLAIMS_{name.upper()}" for name in cls.model_fields if name != "aws_region"}


class TestTerraformWiring:
    @pytest.mark.parametrize(
        "settings",
        [
            config.UploadSettings,
            config.IntakeSettings,
            config.StatusSettings,
            config.OrchestratorSettings,
            config.ToolsSettings,
            config.RuntimeSettings,
        ],
    )
    def test_required_settings_are_provided_by_terraform(
        self, settings: type[config.BaseAppSettings]
    ) -> None:
        required = {
            f"CLAIMS_{name.upper()}"
            for name, field in settings.model_fields.items()
            if field.is_required() and name != "aws_region"
        }
        assert required <= _platform_env_vars()

    def test_terraform_sets_no_unknown_settings(self) -> None:
        known: set[str] = set()
        for cls in (
            config.UploadSettings,
            config.IntakeSettings,
            config.StatusSettings,
            config.OrchestratorSettings,
            config.ToolsSettings,
            config.RuntimeSettings,
        ):
            known |= _settings_env_vars(cls)
        assert _platform_env_vars() <= known

    def test_env_example_lists_every_setting(self) -> None:
        text = (ROOT / ".env.example").read_text()
        listed = set(re.findall(r"^(CLAIMS_[A-Z_]+)=", text, re.MULTILINE))
        for cls in (
            config.UploadSettings,
            config.IntakeSettings,
            config.StatusSettings,
            config.OrchestratorSettings,
            config.ToolsSettings,
            config.RuntimeSettings,
        ):
            assert _settings_env_vars(cls) <= listed, cls.__name__

    def test_memory_namespaces_match_strategies(self) -> None:
        text = (INFRA / "modules" / "agentcore-memory" / "main.tf").read_text()
        templates = set(re.findall(r'namespace_templates\s*=\s*\["([^"]+)"\]', text))
        python = {
            agentcore_memory.PREFERENCES_NAMESPACE.replace("{actor_id}", "{actorId}"),
            agentcore_memory.SUMMARIES_NAMESPACE.replace("{actor_id}", "{actorId}").replace(
                "{session_id}", "{sessionId}"
            ),
        }
        assert templates == python

    def test_gateway_reads_the_shared_tool_definitions(self) -> None:
        text = (INFRA / "modules" / "platform" / "main.tf").read_text()
        assert "src/claims_investigator/tools/tool_definitions.json" in text

    def test_lambda_handlers_exist(self) -> None:
        text = (INFRA / "modules" / "platform" / "main.tf").read_text()
        for handler in re.findall(r'"claims_investigator\.handlers\.([a-z_]+)\.handler"', text):
            assert (ROOT / "src" / "claims_investigator" / "handlers" / f"{handler}.py").exists()

    @pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform not installed")
    def test_terraform_is_formatted(self) -> None:
        result = subprocess.run(  # noqa: S603
            ["terraform", "fmt", "-check", "-recursive", str(INFRA)],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout
