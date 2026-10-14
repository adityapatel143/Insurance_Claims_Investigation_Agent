import logging
from uuid import uuid4

import pytest

from claims_investigator.errors import DependencyUnavailableError
from claims_investigator.models.common import ClaimType
from claims_investigator.models.findings import SourceType
from claims_investigator.models.result import InvestigationResult
from claims_investigator.services.memory import (
    MemoryService,
    actor_id_for,
    build_session_summary,
    memory_session_id,
)
from claims_investigator.services.retrieval import RetrievalService
from tests.fakes import FakeEmbedder, FakeMemoryStore, FakeVectorSearch, hit


class TestRetrieval:
    def test_returns_sorted_unique_sources_with_scores(self) -> None:
        search = FakeVectorSearch(
            [hit("g-1#c0", score=0.5), hit("g-2#c0", score=2.0), hit("g-1#c0", score=0.4)]
        )
        chunks = RetrievalService(search, FakeEmbedder(), top_k=5).retrieve(
            "amount mismatch", SourceType.GUIDANCE, ClaimType.AUTO
        )
        assert [c.source.source_id for c in chunks] == ["src:g-2#c0", "src:g-1#c0"]
        assert chunks[0].source.score == 2.0
        assert chunks[0].source.retrieval_method == "HYBRID"

    def test_no_results_returns_empty_without_fabrication(self) -> None:
        chunks = RetrievalService(FakeVectorSearch([]), FakeEmbedder(), top_k=5).retrieve(
            "anything", SourceType.GUIDANCE, ClaimType.TRAVEL
        )
        assert chunks == []

    def test_blank_query_skips_embedding_and_search(self) -> None:
        embedder, search = FakeEmbedder(), FakeVectorSearch([hit("g-1#c0")])
        assert (
            RetrievalService(search, embedder, 5).retrieve(
                "   ", SourceType.GUIDANCE, ClaimType.AUTO
            )
            == []
        )
        assert not embedder.calls
        assert not search.calls

    def test_min_score_filters_weak_hits(self) -> None:
        search = FakeVectorSearch([hit("g-1#c0", score=0.1)])
        service = RetrievalService(search, FakeEmbedder(), top_k=5, min_score=0.5)
        assert service.retrieve("q", SourceType.GUIDANCE, ClaimType.AUTO) == []


class TestMemory:
    def test_actor_id_is_a_stable_hash(self) -> None:
        assert actor_id_for("arn:x") == actor_id_for("arn:x")
        assert len(actor_id_for("arn:x")) == 64
        assert "arn" not in actor_id_for("arn:x")

    def test_session_is_job_scoped(self) -> None:
        job_id = uuid4()
        assert memory_session_id(job_id).endswith(str(job_id))

    def test_summary_contains_only_codes_and_counts(
        self, result_fixture: dict[str, object]
    ) -> None:
        result = InvestigationResult.model_validate(result_fixture)
        summary = build_session_summary(result)
        assert "AMOUNT_MISMATCH" in summary
        assert result.executive_summary not in summary
        assert "Amounts stated" not in summary
        assert result.claim_id not in summary

    def test_failures_degrade_to_empty_context(
        self, result_fixture: dict[str, object], caplog: pytest.LogCaptureFixture
    ) -> None:
        service = MemoryService(FakeMemoryStore(DependencyUnavailableError("down")))
        with caplog.at_level(logging.WARNING):
            assert service.load("a" * 64, uuid4()).preferences == []
            service.save_summary("a" * 64, InvestigationResult.model_validate(result_fixture))
