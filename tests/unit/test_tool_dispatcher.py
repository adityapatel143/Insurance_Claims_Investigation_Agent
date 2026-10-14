from typing import Any

import pytest
from pydantic import ValidationError

from claims_investigator.errors import (
    ForbiddenError,
    JobTransitionError,
    NotFoundError,
    ToolArgumentError,
)
from claims_investigator.models.jobs import JobStatus
from claims_investigator.models.result import InvestigationResult
from claims_investigator.storage_keys import report_json_key
from claims_investigator.tools import schemas as s
from tests.fakes import World, with_status


def _ids(job: Any) -> dict[str, str]:
    return {
        "job_id": str(job.job_id),
        "claim_id": job.claim_id,
        "correlation_id": job.correlation_id,
    }


def _result_for(job: Any, fixture: dict[str, Any], **changes: Any) -> str:
    data = {**fixture, **_ids(job), **changes}
    return InvestigationResult.model_validate(data).model_dump_json()


@pytest.fixture
def processing(world: World) -> Any:
    _, job = world.seed_job()
    world.repo.jobs[job.job_id] = with_status(job, JobStatus.PROCESSING)
    return world.repo.jobs[job.job_id]


def test_unknown_tool_rejected(world: World) -> None:
    with pytest.raises(ToolArgumentError):
        world.dispatcher().dispatch("delete_everything", {})


def test_extra_arguments_rejected(world: World, processing: Any) -> None:
    with pytest.raises(ValidationError):
        world.dispatcher().dispatch(
            s.GET_CLAIM_DOCUMENT_METADATA, {**_ids(processing), "bucket": "x"}
        )


def test_correlation_mismatch_forbidden(world: World, processing: Any) -> None:
    args = {**_ids(processing), "correlation_id": "corr-other-0001"}
    with pytest.raises(ForbiddenError):
        world.dispatcher().dispatch(s.GET_CLAIM_DOCUMENT_METADATA, args)


def test_claim_mismatch_not_found(world: World, processing: Any) -> None:
    args = {**_ids(processing), "claim_id": "CLM-SYN-0002"}
    with pytest.raises(NotFoundError):
        world.dispatcher().dispatch(s.GET_CLAIM_DOCUMENT_METADATA, args)


def test_reads_require_processing_job(world: World) -> None:
    _, job = world.seed_job()
    with pytest.raises(JobTransitionError):
        world.dispatcher().dispatch(s.GET_CLAIM_DOCUMENT_METADATA, _ids(job))


def test_document_metadata_is_scoped_to_job_documents(world: World, processing: Any) -> None:
    result = world.dispatcher().dispatch(s.GET_CLAIM_DOCUMENT_METADATA, _ids(processing))
    assert isinstance(result, s.DocumentMetadataResult)
    assert len(result.documents) == 3
    assert all(d.present and d.size_bytes > 0 for d in result.documents)


def test_retrieval_tools_use_their_source_type(world: World, processing: Any) -> None:
    args = {**_ids(processing), "claim_type": "AUTO", "query": "repair estimate verification"}
    guidance = world.dispatcher().dispatch(s.GET_POLICY_GUIDANCE, args)
    similar = world.dispatcher().dispatch(s.SEARCH_SIMILAR_CLAIMS, args)
    assert isinstance(guidance, s.RetrievalResult)
    assert isinstance(similar, s.RetrievalResult)
    assert [c.source.source_type for c in guidance.chunks] == ["GUIDANCE"]
    assert [c.source.source_type for c in similar.chunks] == ["HISTORICAL_CLAIM"]


class TestUpdateJobStatus:
    def test_processing_then_failed(self, world: World) -> None:
        _, job = world.seed_job()
        dispatcher = world.dispatcher()
        first = dispatcher.dispatch(s.UPDATE_JOB_STATUS, {**_ids(job), "status": "PROCESSING"})
        again = dispatcher.dispatch(s.UPDATE_JOB_STATUS, {**_ids(job), "status": "PROCESSING"})
        failed = dispatcher.dispatch(
            s.UPDATE_JOB_STATUS, {**_ids(job), "status": "FAILED", "failure_category": "TIMEOUT"}
        )
        assert first == s.UpdateJobStatusResult(status=JobStatus.PROCESSING, changed=True)
        assert again == s.UpdateJobStatusResult(status=JobStatus.PROCESSING, changed=False)
        assert failed == s.UpdateJobStatusResult(status=JobStatus.FAILED, changed=True)

    @pytest.mark.parametrize(
        "args",
        [
            {"status": "COMPLETED"},
            {"status": "REVIEW_REQUIRED"},
            {"status": "FAILED"},
            {"status": "PROCESSING", "failure_category": "TIMEOUT"},
        ],
    )
    def test_cannot_set_terminal_success_or_inconsistent_values(
        self, world: World, args: dict[str, str]
    ) -> None:
        _, job = world.seed_job()
        with pytest.raises(ValidationError):
            world.dispatcher().dispatch(s.UPDATE_JOB_STATUS, {**_ids(job), **args})

    def test_terminal_job_cannot_be_failed_again_differently(self, world: World) -> None:
        _, job = world.seed_job()
        world.repo.jobs[job.job_id] = with_status(job, JobStatus.COMPLETED)
        with pytest.raises(JobTransitionError):
            world.dispatcher().dispatch(
                s.UPDATE_JOB_STATUS,
                {**_ids(job), "status": "FAILED", "failure_category": "INTERNAL"},
            )


class TestPersistFindings:
    def test_persists_reports_and_derives_status(
        self, world: World, processing: Any, result_fixture: dict[str, Any]
    ) -> None:
        args = {
            **_ids(processing),
            "result_json": _result_for(processing, result_fixture),
            "report_markdown": "# r",
        }
        result = world.dispatcher().dispatch(s.PERSIST_INVESTIGATION_FINDINGS, args)

        assert isinstance(result, s.PersistFindingsResult)
        assert result.status is JobStatus.REVIEW_REQUIRED
        stored = world.repo.jobs[processing.job_id]
        assert stored.status is JobStatus.REVIEW_REQUIRED
        assert stored.report_key == report_json_key(processing.claim_id, processing.job_id)
        assert stored.report_key in world.store.objects
        assert stored.anomaly_signal_count == 1

    def test_replay_after_success_is_idempotent(
        self, world: World, processing: Any, result_fixture: dict[str, Any]
    ) -> None:
        args = {
            **_ids(processing),
            "result_json": _result_for(processing, result_fixture),
            "report_markdown": "# r",
        }
        dispatcher = world.dispatcher()
        first = dispatcher.dispatch(s.PERSIST_INVESTIGATION_FINDINGS, args)
        second = dispatcher.dispatch(s.PERSIST_INVESTIGATION_FINDINGS, args)
        assert first == second

    def test_completed_with_anomalies_is_rejected(
        self, world: World, processing: Any, result_fixture: dict[str, Any]
    ) -> None:
        tampered = {
            **result_fixture,
            **_ids(processing),
            "status": "COMPLETED",
            "human_review_required": False,
            "review_reasons": [],
        }
        args = {
            **_ids(processing),
            "result_json": InvestigationResult.model_validate(tampered).model_dump_json(),
            "report_markdown": "# r",
        }
        with pytest.raises(ToolArgumentError, match="human review"):
            world.dispatcher().dispatch(s.PERSIST_INVESTIGATION_FINDINGS, args)
        assert world.repo.jobs[processing.job_id].status is JobStatus.PROCESSING

    def test_malformed_result_is_rejected(self, world: World, processing: Any) -> None:
        args = {
            **_ids(processing),
            "result_json": '{"status": "COMPLETED"}',
            "report_markdown": "# r",
        }
        with pytest.raises(ToolArgumentError, match="validation"):
            world.dispatcher().dispatch(s.PERSIST_INVESTIGATION_FINDINGS, args)

    def test_result_for_another_job_is_rejected(
        self, world: World, processing: Any, result_fixture: dict[str, Any]
    ) -> None:
        args = {
            **_ids(processing),
            "result_json": InvestigationResult.model_validate(result_fixture).model_dump_json(),
            "report_markdown": "# r",
        }
        with pytest.raises(ToolArgumentError, match="identifiers"):
            world.dispatcher().dispatch(s.PERSIST_INVESTIGATION_FINDINGS, args)
