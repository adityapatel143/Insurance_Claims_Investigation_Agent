from datetime import timedelta
from uuid import uuid4

import pytest

from claims_investigator.errors import (
    DocumentRejectedError,
    IdempotencyConflictError,
    JobTransitionError,
    NotFoundError,
    RequestValidationError,
)
from claims_investigator.models.api import UploadRequest
from claims_investigator.models.common import DocumentType
from claims_investigator.models.jobs import FailureCategory, JobStatus
from claims_investigator.services.intake import IntakeService
from claims_investigator.services.jobs import derive_job_id, request_hash
from claims_investigator.services.ports import JobUpdate
from claims_investigator.services.status import StatusService
from claims_investigator.services.uploads import UploadPolicy, UploadService
from claims_investigator.storage_keys import quarantine_key
from tests.fakes import (
    CLAIM_ID,
    CORRELATION_ID,
    PRINCIPAL,
    DocSpec,
    FakeQueue,
    World,
    make_submission,
    standard_docs,
    upload_docs,
    with_status,
)

POLICY = UploadPolicy(1024 * 1024, frozenset({"text/plain", "text/csv", "application/json"}))


class TestJobIdentity:
    def test_job_id_is_deterministic_per_principal_claim_and_request(self) -> None:
        request_id = uuid4()
        assert derive_job_id("p", "C-1", request_id) == derive_job_id("p", "C-1", request_id)
        assert derive_job_id("p", "C-1", request_id) != derive_job_id("q", "C-1", request_id)

    def test_request_hash_changes_with_body(self) -> None:
        assert request_hash(make_submission()) != request_hash(
            make_submission(claimed_amount="999.00")
        )


class TestJobService:
    def test_disallowed_transition_raises(self, world: World) -> None:
        _, job = world.seed_job()
        with pytest.raises(JobTransitionError):
            world.jobs.transition(job.job_id, JobStatus.QUEUED, JobStatus.COMPLETED, JobUpdate())

    def test_lost_race_raises(self, world: World) -> None:
        _, job = world.seed_job(status=JobStatus.PROCESSING)
        with pytest.raises(JobTransitionError):
            world.jobs.transition(job.job_id, JobStatus.QUEUED, JobStatus.PROCESSING, JobUpdate())

    def test_get_for_claim_hides_other_claims(self, world: World) -> None:
        _, job = world.seed_job()
        with pytest.raises(NotFoundError):
            world.jobs.get_for_claim("CLM-SYN-9999", job.job_id)

    def test_expire_if_overdue(self, world: World, no_metrics: list[tuple[str, float]]) -> None:
        _, job = world.seed_job(status=JobStatus.PROCESSING)
        job = with_status(
            job, JobStatus.PROCESSING, processing_deadline=world.clock() - timedelta(seconds=1)
        )
        world.repo.jobs[job.job_id] = job
        expired = world.jobs.expire_if_overdue(job)
        assert expired.status is JobStatus.FAILED
        assert expired.failure_category is FailureCategory.TIMEOUT
        assert ("JobsFailed", 1) in no_metrics

    def test_not_overdue_is_unchanged(self, world: World) -> None:
        _, job = world.seed_job(status=JobStatus.PROCESSING)
        job = with_status(
            job, JobStatus.PROCESSING, processing_deadline=world.clock() + timedelta(hours=1)
        )
        assert world.jobs.expire_if_overdue(job) is job


class TestUploadService:
    def test_creates_presigned_post_for_claim_key(self, world: World) -> None:
        service = UploadService(world.store, POLICY, 300, world.clock)
        response = service.create_upload(
            UploadRequest(claim_id=CLAIM_ID, file_name="claim_form.txt", content_type="text/plain")
        )
        assert response.object_key == f"intake/{CLAIM_ID}/{response.document_id}/claim_form.txt"
        assert world.store.presigned_posts == [
            (response.object_key, "text/plain", POLICY.max_upload_bytes, 300)
        ]
        assert response.expires_at == world.clock() + timedelta(seconds=300)

    def test_rejects_disallowed_content_type(self, world: World) -> None:
        service = UploadService(world.store, POLICY, 300, world.clock)
        with pytest.raises(RequestValidationError):
            service.create_upload(
                UploadRequest(
                    claim_id=CLAIM_ID, file_name="x.exe", content_type="application/x-msdownload"
                )
            )


def _intake(world: World, queue: FakeQueue | None = None) -> tuple[IntakeService, FakeQueue]:
    queue = queue or FakeQueue()
    return IntakeService(
        world.store, world.jobs, queue, POLICY, job_ttl_days=30, clock=world.clock
    ), queue


class TestIntakeService:
    def test_creates_job_and_enqueues_once(self, world: World) -> None:
        docs = standard_docs()
        upload_docs(world.store, docs)
        service, queue = _intake(world)
        accepted = service.submit(make_submission(docs), PRINCIPAL, CORRELATION_ID)

        job = world.repo.jobs[accepted.job_id]
        assert accepted.status is JobStatus.QUEUED
        assert accepted.status_url == f"/claims/{CLAIM_ID}/jobs/{accepted.job_id}"
        assert job.enqueue_count == 1
        assert job.expires_at is not None
        assert [m.attempt for m in queue.messages] == [1]
        assert job.submission_key in world.store.objects
        assert "incident_description" not in job.model_dump_json()

    def test_identical_retry_is_idempotent_and_re_enqueues_while_queued(self, world: World) -> None:
        docs = standard_docs()
        upload_docs(world.store, docs)
        service, queue = _intake(world)
        submission = make_submission(docs)
        first = service.submit(submission, PRINCIPAL, CORRELATION_ID)
        second = service.submit(submission, PRINCIPAL, "corr-retry-0002")

        assert second.job_id == first.job_id
        assert second.correlation_id == CORRELATION_ID
        assert len(world.repo.jobs) == 1
        assert [m.attempt for m in queue.messages] == [1, 2]

    def test_retry_after_processing_does_not_re_enqueue(self, world: World) -> None:
        docs = standard_docs()
        upload_docs(world.store, docs)
        service, queue = _intake(world)
        submission = make_submission(docs)
        accepted = service.submit(submission, PRINCIPAL, CORRELATION_ID)
        world.repo.jobs[accepted.job_id] = with_status(
            world.repo.jobs[accepted.job_id], JobStatus.PROCESSING
        )
        service.submit(submission, PRINCIPAL, CORRELATION_ID)
        assert len(queue.messages) == 1

    def test_reused_request_id_with_different_body_conflicts(self, world: World) -> None:
        docs = standard_docs()
        upload_docs(world.store, docs)
        service, _ = _intake(world)
        service.submit(make_submission(docs), PRINCIPAL, CORRELATION_ID)
        with pytest.raises(IdempotencyConflictError):
            service.submit(
                make_submission(docs, claimed_amount="999.00"), PRINCIPAL, CORRELATION_ID
            )

    def test_mismatched_content_type_is_quarantined(self, world: World) -> None:
        docs = standard_docs()
        upload_docs(world.store, docs)
        bad = docs[0]
        key = f"intake/{CLAIM_ID}/{bad.document_id}/{bad.file_name}"
        world.store.objects[key] = (bad.body, "application/octet-stream")
        service, queue = _intake(world)

        with pytest.raises(DocumentRejectedError) as excinfo:
            service.submit(make_submission(docs), PRINCIPAL, CORRELATION_ID)

        assert str(bad.document_id) in excinfo.value.details[0]
        assert key not in world.store.objects
        assert quarantine_key(key) in world.store.objects
        assert not world.repo.jobs
        assert not queue.messages

    def test_missing_object_is_rejected_without_quarantine(self, world: World) -> None:
        docs = standard_docs()
        upload_docs(world.store, docs[1:])
        service, _ = _intake(world)
        with pytest.raises(DocumentRejectedError, match="rejected"):
            service.submit(make_submission(docs), PRINCIPAL, CORRELATION_ID)
        assert not any(k.startswith("quarantine/") for k in world.store.objects)

    def test_oversized_object_is_quarantined(self, world: World) -> None:
        big = DocSpec(
            DocumentType.CLAIM_FORM, "big.txt", "text/plain", b"x" * (POLICY.max_upload_bytes + 1)
        )
        upload_docs(world.store, [big])
        service, _ = _intake(world)
        with pytest.raises(DocumentRejectedError):
            service.submit(make_submission([big]), PRINCIPAL, CORRELATION_ID)
        assert any(k.startswith("quarantine/") for k in world.store.objects)

    def test_queue_failure_propagates_and_retry_recovers(self, world: World) -> None:
        docs = standard_docs()
        upload_docs(world.store, docs)
        submission = make_submission(docs)
        failing, _ = _intake(world, FakeQueue(fail=True))
        with pytest.raises(RuntimeError):
            failing.submit(submission, PRINCIPAL, CORRELATION_ID)

        service, queue = _intake(world)
        service.submit(submission, PRINCIPAL, CORRELATION_ID)
        assert len(queue.messages) == 1


class TestStatusService:
    def test_owner_gets_report_url(self, world: World) -> None:
        _, job = world.seed_job()
        world.repo.jobs[job.job_id] = with_status(
            job,
            JobStatus.REVIEW_REQUIRED,
            report_key="reports/x/report.json",
            human_review_required=True,
        )
        status = StatusService(world.jobs, world.store, 300, world.clock).get_status(
            CLAIM_ID, job.job_id, PRINCIPAL
        )
        assert status.report_url is not None
        assert status.report_location == "reports/x/report.json"
        assert status.human_review_required is True

    def test_other_principal_gets_no_url(self, world: World) -> None:
        _, job = world.seed_job()
        world.repo.jobs[job.job_id] = with_status(
            job, JobStatus.COMPLETED, report_key="reports/x/report.json"
        )
        status = StatusService(world.jobs, world.store, 300, world.clock).get_status(
            CLAIM_ID, job.job_id, "arn:aws:iam::111122223333:user/someone-else"
        )
        assert status.report_url is None
        assert status.report_location == "reports/x/report.json"

    def test_unknown_or_mismatched_claim_is_not_found(self, world: World) -> None:
        _, job = world.seed_job()
        service = StatusService(world.jobs, world.store, 300, world.clock)
        with pytest.raises(NotFoundError):
            service.get_status("CLM-SYN-0002", job.job_id, PRINCIPAL)
        with pytest.raises(NotFoundError):
            service.get_status(CLAIM_ID, uuid4(), PRINCIPAL)

    def test_overdue_processing_job_reports_timeout(
        self, world: World, no_metrics: list[tuple[str, float]]
    ) -> None:
        _, job = world.seed_job()
        world.repo.jobs[job.job_id] = with_status(
            job, JobStatus.PROCESSING, processing_deadline=world.clock() - timedelta(minutes=1)
        )
        status = StatusService(world.jobs, world.store, 300, world.clock).get_status(
            CLAIM_ID, job.job_id, PRINCIPAL
        )
        assert status.status is JobStatus.FAILED
        assert status.failure_category is FailureCategory.TIMEOUT
        assert status.report_url is None
