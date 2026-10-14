"""AgentCore Runtime invoker used by the orchestrator."""

from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from claims_investigator.errors import DependencyUnavailableError
from claims_investigator.gateways.aws import raise_translated
from claims_investigator.models.messages import RuntimeInvocation

if TYPE_CHECKING:
    from mypy_boto3_bedrock_agentcore import BedrockAgentCoreClient

_MAX_ACK_BYTES = 4096


class AgentCoreRuntimeInvoker:
    def __init__(self, client: "BedrockAgentCoreClient", runtime_arn: str, qualifier: str) -> None:
        self._client = client
        self._runtime_arn = runtime_arn
        self._qualifier = qualifier

    def invoke(self, session_id: str, payload: RuntimeInvocation) -> None:
        try:
            response = self._client.invoke_agent_runtime(
                agentRuntimeArn=self._runtime_arn,
                qualifier=self._qualifier,
                runtimeSessionId=session_id,
                contentType="application/json",
                accept="application/json",
                payload=payload.model_dump_json().encode(),
            )
            # The entrypoint only acknowledges; the investigation continues as an async task.
            response["response"].read(_MAX_ACK_BYTES)
        except (ClientError, BotoCoreError) as exc:
            raise_translated(exc, "bedrock-agentcore.invoke_agent_runtime")
        if not 200 <= response["statusCode"] < 300:  # noqa: PLR2004
            raise DependencyUnavailableError(f"runtime returned status {response['statusCode']}")
