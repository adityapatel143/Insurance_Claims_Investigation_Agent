"""AgentCore Memory adapter; namespaces must match the Terraform memory strategies."""

from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from claims_investigator.gateways.aws import raise_translated
from claims_investigator.services.ports import Clock, MemoryContext, utc_now

if TYPE_CHECKING:
    from mypy_boto3_bedrock_agentcore import BedrockAgentCoreClient

PREFERENCES_NAMESPACE = "/claims/preferences/{actor_id}"
SUMMARIES_NAMESPACE = "/claims/summaries/{actor_id}/{session_id}"
MAX_RECORDS = 20


class AgentCoreMemoryStore:
    def __init__(
        self, client: "BedrockAgentCoreClient", memory_id: str, clock: Clock = utc_now
    ) -> None:
        self._client = client
        self._memory_id = memory_id
        self._clock = clock

    def load(self, actor_id: str, session_id: str) -> MemoryContext:
        return MemoryContext(
            preferences=self._list(PREFERENCES_NAMESPACE.format(actor_id=actor_id)),
            session_summaries=self._list(
                SUMMARIES_NAMESPACE.format(actor_id=actor_id, session_id=session_id)
            ),
        )

    def save_session_summary(self, actor_id: str, session_id: str, summary: str) -> None:
        try:
            self._client.create_event(
                memoryId=self._memory_id,
                actorId=actor_id,
                sessionId=session_id,
                eventTimestamp=self._clock(),
                payload=[{"conversational": {"content": {"text": summary}, "role": "ASSISTANT"}}],
            )
        except (ClientError, BotoCoreError) as exc:
            raise_translated(exc, "bedrock-agentcore.create_event")

    def _list(self, namespace: str) -> list[str]:
        try:
            response = self._client.list_memory_records(
                memoryId=self._memory_id, namespace=namespace, maxResults=MAX_RECORDS
            )
        except (ClientError, BotoCoreError) as exc:
            raise_translated(exc, "bedrock-agentcore.list_memory_records")
        return [
            text
            for record in response["memoryRecordSummaries"]
            if (text := record["content"].get("text"))
        ]
