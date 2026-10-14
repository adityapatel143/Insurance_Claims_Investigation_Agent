import pytest

from claims_investigator.errors import DependencyUnavailableError
from claims_investigator.models.jobs import FailureCategory, JobStatus
from claims_investigator.services.dispatch import DispatchOutcome, DispatchPolicy, DispatchService
from claims_investigator.services.memory import actor_id_for
from tests.fakes import PRINCIPAL, FakeInvoker, World, make_message, with_status

POLICY = DispatchPolicy(lease_seconds=120, investigation_timeout_seconds=1800, max_receive_count=3)


def _service(world: World, invoker: FakeInvoker) -> DispatchService:
    return DispatchService(world.jobs, world.repo, invoker, POLICY, world.clock)


def test_dispatch_invokes_runtime_and_marks_processing(world: World) -> None:
    submission, job = world.seed_job()
    invoker = FakeInvoker()
    outcome = _service(world, invoker).dispatch(make_message(job, submission), receive_count=1)

    assert outcome is DispatchOutcome.DISPATCHED
    session_id, payload = invoker.calls[0]
    assert session_id == f"claims-job-{job.job_id}"
    assert len(session_id) >= 33
    assert payload.actor_id == actor_id_for(PRINCIPAL)
    assert payload.correlation_id == job.correlation_id
    stored = world.repo.jobs[job.job_id]
    assert stored.status is JobStatus.PROCESSING
    assert stored.dispatch_lease_until is None
    assert stored.processing_deadline is not None


@pytest.mark.parametrize("status", [JobStatus.PROCESSING, JobStatus.COMPLETED, JobStatus.FAILED])
def test_duplicate_message_is_skipped(world: World, status: JobStatus) -> None:
    submission, job = world.seed_job()
    world.repo.jobs[job.job_id] = with_status(job, status)
    invoker = FakeInvoker()
    outcome = _service(world, invoker).dispatch(make_message(job, submission), receive_count=1)
    assert outcome is DispatchOutcome.SKIPPED
    assert not invoker.calls


def test_held_lease_skips_concurrent_delivery(world: World) -> None:
    submission, job = world.seed_job()
    world.repo.acquire_dispatch_lease(job.job_id, world.clock(), world.clock().replace(year=2030))
    invoker = FakeInvoker()
    assert (
        _service(world, invoker).dispatch(make_message(job, submission), 1)
        is DispatchOutcome.SKIPPED
    )
    assert not invoker.calls


def test_unknown_job_or_claim_mismatch_is_skipped(world: World) -> None:
    submission, job = world.seed_job()
    message = make_message(job, submission).model_copy(update={"claim_id": "CLM-SYN-9999"})
    assert _service(world, FakeInvoker()).dispatch(message, 1) is DispatchOutcome.SKIPPED


def test_invoke_failure_releases_lease_and_reraises(world: World) -> None:
    submission, job = world.seed_job()
    invoker = FakeInvoker(DependencyUnavailableError("throttled"))
    with pytest.raises(DependencyUnavailableError):
        _service(world, invoker).dispatch(make_message(job, submission), receive_count=1)
    stored = world.repo.jobs[job.job_id]
    assert stored.status is JobStatus.QUEUED
    assert stored.dispatch_lease_until is None


def test_final_attempt_marks_failed_before_dlq(
    world: World, no_metrics: list[tuple[str, float]]
) -> None:
    submission, job = world.seed_job()
    invoker = FakeInvoker(DependencyUnavailableError("throttled"))
    with pytest.raises(DependencyUnavailableError):
        _service(world, invoker).dispatch(make_message(job, submission), receive_count=3)
    stored = world.repo.jobs[job.job_id]
    assert stored.status is JobStatus.FAILED
    assert stored.failure_category is FailureCategory.DISPATCH_EXHAUSTED
    assert ("JobsFailed", 1) in no_metrics


def test_runtime_already_marked_processing_is_tolerated(world: World) -> None:
    submission, job = world.seed_job()

    class AdvancingInvoker(FakeInvoker):
        def invoke(self, session_id: str, payload: object) -> None:  # type: ignore[override]
            world.repo.jobs[job.job_id] = with_status(
                world.repo.jobs[job.job_id], JobStatus.PROCESSING
            )

    outcome = _service(world, AdvancingInvoker()).dispatch(make_message(job, submission), 1)
    assert outcome is DispatchOutcome.DISPATCHED
