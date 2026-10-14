"""OpenSearch Serverless adapter (SigV4 service `aoss`): index management and hybrid search."""

from collections.abc import Sequence
from typing import Any

import boto3
from opensearchpy import (
    OpenSearch,
    OpenSearchException,
    Urllib3AWSV4SignerAuth,
    Urllib3HttpConnection,
)

from claims_investigator.errors import DependencyUnavailableError
from claims_investigator.models.common import ClaimType
from claims_investigator.models.findings import SourceType
from claims_investigator.services.ports import SearchHit

GENERAL_CLAIM_TYPE = "GENERAL"
VECTOR_FIELD = "embedding"


def build_client(endpoint_host: str, region: str, timeout: int = 10) -> OpenSearch:
    credentials = boto3.Session().get_credentials()
    return OpenSearch(
        hosts=[{"host": endpoint_host, "port": 443}],
        http_auth=Urllib3AWSV4SignerAuth(credentials, region, "aoss"),
        use_ssl=True,
        verify_certs=True,
        connection_class=Urllib3HttpConnection,
        timeout=timeout,
        max_retries=2,
        retry_on_timeout=True,
    )


def index_body(dimensions: int) -> dict[str, Any]:
    return {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "document_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "source_type": {"type": "keyword"},
                "source_uri": {"type": "keyword"},
                "claim_type": {"type": "keyword"},
                "title": {"type": "text"},
                "text": {"type": "text"},
                "metadata": {"type": "object", "dynamic": True},
                VECTOR_FIELD: {
                    "type": "knn_vector",
                    "dimension": dimensions,
                    "method": {"name": "hnsw", "engine": "faiss", "space_type": "l2"},
                },
            },
        },
    }


class OpenSearchVectorSearch:
    def __init__(self, client: OpenSearch, index: str) -> None:
        self._client = client
        self._index = index

    def create_index(self, dimensions: int) -> bool:
        """Create the index if absent; return True when it was created."""
        try:
            if self._client.indices.exists(index=self._index):
                return False
            self._client.indices.create(index=self._index, body=index_body(dimensions))
        except OpenSearchException as exc:
            raise DependencyUnavailableError("opensearch index creation failed") from exc
        return True

    def delete_index(self) -> bool:
        """Delete the index if present; return True when it was deleted."""
        try:
            if not self._client.indices.exists(index=self._index):
                return False
            self._client.indices.delete(index=self._index)
        except OpenSearchException as exc:
            raise DependencyUnavailableError("opensearch index deletion failed") from exc
        return True

    def index_chunk(self, chunk_id: str, document: dict[str, Any]) -> None:
        """AOSS vector collections assign document IDs; `chunk_id` is stored as a field."""
        try:
            self._client.index(index=self._index, body={**document, "chunk_id": chunk_id})
        except OpenSearchException as exc:
            raise DependencyUnavailableError("opensearch indexing failed") from exc

    def hybrid_search(
        self,
        query_text: str,
        query_vector: Sequence[float],
        source_type: SourceType,
        claim_type: ClaimType,
        top_k: int,
    ) -> list[SearchHit]:
        filters = [
            {"term": {"source_type": str(source_type)}},
            {"terms": {"claim_type": [str(claim_type), GENERAL_CLAIM_TYPE]}},
        ]
        body = {
            "size": top_k,
            "_source": {"excludes": [VECTOR_FIELD]},
            "query": {
                "bool": {
                    "should": [
                        {
                            "knn": {
                                VECTOR_FIELD: {
                                    "vector": list(query_vector),
                                    "k": top_k,
                                    "filter": {"bool": {"filter": filters}},
                                }
                            }
                        },
                        {"bool": {"filter": filters, "must": [{"match": {"text": query_text}}]}},
                    ],
                    "minimum_should_match": 1,
                }
            },
        }
        try:
            response = self._client.search(index=self._index, body=body)
        except OpenSearchException as exc:
            raise DependencyUnavailableError("opensearch search failed") from exc
        return [_to_hit(hit) for hit in response.get("hits", {}).get("hits", [])]


def _to_hit(hit: dict[str, Any]) -> SearchHit:
    source = hit.get("_source", {})
    return SearchHit(
        document_id=str(source.get("document_id", "")),
        chunk_id=str(source.get("chunk_id", "")),
        source_type=SourceType(source.get("source_type", SourceType.GUIDANCE)),
        source_uri=str(source.get("source_uri", "")),
        title=str(source.get("title", "")),
        text=str(source.get("text", "")),
        score=float(hit.get("_score") or 0.0),
    )
