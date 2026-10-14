"""Grounded retrieval over OpenSearch; returns only what the index returned."""

from claims_investigator.models.common import ClaimType
from claims_investigator.models.findings import RetrievedChunk, RetrievedSource, SourceType
from claims_investigator.services.ports import Embedder, VectorSearch

MAX_QUERY_CHARS = 2000
MAX_CHUNK_CHARS = 8000


class RetrievalService:
    def __init__(
        self, search: VectorSearch, embedder: Embedder, top_k: int, min_score: float = 0.0
    ) -> None:
        self._search = search
        self._embedder = embedder
        self._top_k = top_k
        self._min_score = min_score

    def retrieve(
        self, query: str, source_type: SourceType, claim_type: ClaimType
    ) -> list[RetrievedChunk]:
        query = query.strip()[:MAX_QUERY_CHARS]
        if not query:
            return []
        hits = self._search.hybrid_search(
            query, self._embedder.embed(query), source_type, claim_type, self._top_k
        )
        chunks: dict[str, RetrievedChunk] = {}
        for hit in sorted(hits, key=lambda h: h.score, reverse=True):
            if hit.score < self._min_score or not hit.text.strip() or hit.chunk_id in chunks:
                continue
            chunks[hit.chunk_id] = RetrievedChunk(
                source=RetrievedSource(
                    source_id=f"src:{hit.chunk_id}",
                    document_id=hit.document_id,
                    chunk_id=hit.chunk_id,
                    source_type=hit.source_type,
                    source_uri=hit.source_uri,
                    title=hit.title,
                    score=hit.score,
                    retrieval_method="HYBRID",
                ),
                text=hit.text[:MAX_CHUNK_CHARS],
            )
        return list(chunks.values())
