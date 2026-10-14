"""Bedrock embeddings adapter (Titan Text Embeddings V2 request/response format)."""

import json
from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from claims_investigator.errors import DependencyUnavailableError
from claims_investigator.gateways.aws import raise_translated

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient

MAX_EMBED_CHARS = 8000


class BedrockEmbedder:
    def __init__(self, client: "BedrockRuntimeClient", model_id: str, dimensions: int) -> None:
        self._client = client
        self._model_id = model_id
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        body = {
            "inputText": text[:MAX_EMBED_CHARS],
            "dimensions": self._dimensions,
            "normalize": True,
        }
        try:
            response = self._client.invoke_model(
                modelId=self._model_id,
                body=json.dumps(body).encode(),
                contentType="application/json",
                accept="application/json",
            )
            vector = json.loads(response["body"].read())["embedding"]
        except (ClientError, BotoCoreError) as exc:
            raise_translated(exc, "bedrock-runtime.invoke_model")
        if not isinstance(vector, list) or len(vector) != self._dimensions:
            raise DependencyUnavailableError("embedding has unexpected dimensions")
        return [float(v) for v in vector]
