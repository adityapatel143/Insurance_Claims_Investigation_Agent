"""AWS adapter tests (no network): botocore Stubber for clients, a recording fake Table."""

import base64
import io
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from claims_investigator.errors import DependencyUnavailableError, RequestValidationError
from claims_investigator.gateways.agentcore_memory import AgentCoreMemoryStore
from claims_investigator.gateways.agentcore_runtime import AgentCoreRuntimeInvoker
from claims_investigator.gateways.dynamodb import DynamoJobRepository, item_to_job, job_to_item
from claims_investigator.gateways.embeddings import BedrockEmbedder
from claims_investigator.gateways.s3 import S3ObjectStore
from claims_investigator.models.jobs import JobStatus
from claims_investigator.models.messages import RuntimeInvocation
from claims_investigator.services.ports import JobUpdate
from tests.fakes import FixedClock, make_job, make_submission

REGION = "us-east-1"
RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:111122223333:runtime/example"
MEMORY_ID = "memory-synthetic-0001"
ACTOR = "a" * 64
SESSION = "claims-job-" + "1" * 36


def _body(data: bytes) -> StreamingBody:
    return StreamingBody(io.BytesIO(data), len(data))


def _client_error(code: str, operation: str = "Op", status: int = 400) -> ClientError:
    return ClientError(
        {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}}, operation
    )


class RecordingTable:
    def __init__(self, *results: Any) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _next(self, name: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((name, kwargs))
        result = self.results.pop(0) if self.results else {}
        if isinstance(result, Exception):
            raise result
        return result

    def put_item(self, **kwargs: Any) -> Any:
        return self._next("put_item", kwargs)

    def update_item(self, **kwargs: Any) -> Any:
        return self._next("update_item", kwargs)

    def get_item(self, **kwargs: Any) -> Any:
        return self._next("get_item", kwargs)


class TestDynamo:
    def test_item_round_trip(self) -> None:
        job = make_job(make_submission(), FixedClock(), expires_at=1_900_000_000)
        item = job_to_item(job)
        assert item["created_at"] == "2025-05-05T10:00:00.000000Z"
        assert item["status"] == "QUEUED"
        assert "dispatch_lease_until" not in item
        item["document_count"] = Decimal(item["document_count"])
        item["expires_at"] = Decimal(item["expires_at"])
        assert item_to_job(item) == job

    def test_create_is_conditional(self) -> None:
        job = make_job(make_submission(), FixedClock())
        table = RecordingTable({}, _client_error("ConditionalCheckFailedException"))
        repo = DynamoJobRepository(table)  # type: ignore[arg-type]
        assert repo.create(job) is True
        assert repo.create(job) is False
        assert table.calls[0][1]["ConditionExpression"] == "attribute_not_exists(job_id)"

    def test_throttling_is_retryable_dependency_error(self) -> None:
        table = RecordingTable(_client_error("ThrottlingException"))
        with pytest.raises(DependencyUnavailableError):
            DynamoJobRepository(table).create(make_job(make_submission(), FixedClock()))  # type: ignore[arg-type]

    def test_validation_errors_are_not_masked(self) -> None:
        table = RecordingTable(_client_error("ValidationException"))
        with pytest.raises(ClientError):
            DynamoJobRepository(table).create(make_job(make_submission(), FixedClock()))  # type: ignore[arg-type]

    def test_transition_sets_fields_and_clears_lease(self) -> None:
        job = make_job(make_submission(), FixedClock())
        now = datetime(2025, 5, 5, 10, 1, tzinfo=UTC)
        table = RecordingTable({}, _client_error("ConditionalCheckFailedException"))
        repo = DynamoJobRepository(table)  # type: ignore[arg-type]
        update = JobUpdate(dispatched_at=now)

        assert repo.transition(job.job_id, JobStatus.QUEUED, JobStatus.PROCESSING, now, update)
        assert not repo.transition(job.job_id, JobStatus.QUEUED, JobStatus.PROCESSING, now, update)
        call = table.calls[0][1]
        assert call["ConditionExpression"] == "#status = :expected"
        assert call["UpdateExpression"].endswith("REMOVE dispatch_lease_until")
        assert "dispatched_at = :dispatched_at" in call["UpdateExpression"]
        assert call["ExpressionAttributeValues"][":target"] == "PROCESSING"

    def test_lease_condition_requires_queued_and_expired_lease(self) -> None:
        table = RecordingTable({})
        clock = FixedClock()
        job = make_job(make_submission(), clock)
        DynamoJobRepository(table).acquire_dispatch_lease(job.job_id, clock(), clock())  # type: ignore[arg-type]
        condition = table.calls[0][1]["ConditionExpression"]
        assert "#status = :queued" in condition
        assert "dispatch_lease_until < :now" in condition

    def test_record_enqueue_returns_counter(self) -> None:
        table = RecordingTable({"Attributes": {"enqueue_count": Decimal(2)}})
        job = make_job(make_submission(), FixedClock())
        assert DynamoJobRepository(table).record_enqueue(job.job_id) == 2  # type: ignore[arg-type]

    def test_get_uses_consistent_read(self) -> None:
        job = make_job(make_submission(), FixedClock())
        table = RecordingTable({"Item": job_to_item(job)}, {})
        repo = DynamoJobRepository(table)  # type: ignore[arg-type]
        assert repo.get(job.job_id) == job
        assert repo.get(job.job_id) is None
        assert table.calls[0][1]["ConsistentRead"] is True


class TestS3:
    def test_head_missing_object_returns_none(self) -> None:
        client = boto3.client("s3", region_name=REGION)
        with Stubber(client) as stub:
            stub.add_client_error("head_object", "404", http_status_code=404)
            assert S3ObjectStore(client, "bucket").head("intake/x") is None

    def test_get_bytes_enforces_limit(self) -> None:
        client = boto3.client("s3", region_name=REGION)
        with Stubber(client) as stub:
            stub.add_response(
                "get_object",
                {"Body": _body(b"12345")},
                {"Bucket": "bucket", "Key": "k", "Range": "bytes=0-4"},
            )
            with pytest.raises(RequestValidationError):
                S3ObjectStore(client, "bucket").get_bytes("k", 4)

    def test_presigned_post_enforces_type_and_size(self) -> None:
        client = boto3.client("s3", region_name=REGION)
        post = S3ObjectStore(client, "bucket").presign_post(
            "intake/C/D/f.txt", "text/plain", 100, 300
        )
        policy = json.loads(base64.b64decode(post.fields["policy"]))
        assert post.fields["Content-Type"] == "text/plain"
        assert ["content-length-range", 1, 100] in policy["conditions"]
        assert {"Content-Type": "text/plain"} in policy["conditions"]


def _invocation() -> RuntimeInvocation:
    submission = make_submission()
    job = make_job(submission, FixedClock())
    return RuntimeInvocation(
        job_id=job.job_id,
        claim_id=job.claim_id,
        correlation_id=job.correlation_id,
        submission_key=job.submission_key,
        document_references=submission.documents,
        actor_id=ACTOR,
        processing_deadline=datetime(2025, 5, 5, 10, 30, tzinfo=UTC),
    )


class TestAgentCore:
    def test_invoke_runtime_passes_session_and_qualifier(self) -> None:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        with Stubber(client) as stub:
            stub.add_response(
                "invoke_agent_runtime",
                {
                    "statusCode": 200,
                    "response": _body(b'{"status":"ACCEPTED"}'),
                    "contentType": "application/json",
                },
                {
                    "agentRuntimeArn": RUNTIME_ARN,
                    "qualifier": "DEFAULT",
                    "runtimeSessionId": SESSION,
                    "contentType": "application/json",
                    "accept": "application/json",
                    "payload": ANY,
                },
            )
            AgentCoreRuntimeInvoker(client, RUNTIME_ARN, "DEFAULT").invoke(SESSION, _invocation())

    def test_invoke_runtime_error_status_is_retryable(self) -> None:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        with Stubber(client) as stub:
            stub.add_response(
                "invoke_agent_runtime",
                {"statusCode": 500, "response": _body(b"{}"), "contentType": "application/json"},
            )
            with pytest.raises(DependencyUnavailableError):
                AgentCoreRuntimeInvoker(client, RUNTIME_ARN, "DEFAULT").invoke(
                    SESSION, _invocation()
                )

    def test_memory_load_and_save(self) -> None:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        created = datetime(2025, 1, 1, tzinfo=UTC)
        record = {
            "memoryRecordId": "mr-" + "0" * 40,
            "content": {"text": "prefers concise reports"},
            "memoryStrategyId": "strategy-1",
            "namespaces": [f"/claims/preferences/{ACTOR}"],
            "createdAt": created,
        }
        with Stubber(client) as stub:
            stub.add_response(
                "list_memory_records",
                {"memoryRecordSummaries": [record]},
                {
                    "memoryId": MEMORY_ID,
                    "namespace": f"/claims/preferences/{ACTOR}",
                    "maxResults": 20,
                },
            )
            stub.add_response(
                "list_memory_records",
                {"memoryRecordSummaries": []},
                {
                    "memoryId": MEMORY_ID,
                    "namespace": f"/claims/summaries/{ACTOR}/{SESSION}",
                    "maxResults": 20,
                },
            )
            stub.add_response(
                "create_event",
                {
                    "event": {
                        "memoryId": MEMORY_ID,
                        "actorId": ACTOR,
                        "sessionId": SESSION,
                        "eventId": "event-1",
                        "eventTimestamp": created,
                        "payload": [],
                    }
                },
                {
                    "memoryId": MEMORY_ID,
                    "actorId": ACTOR,
                    "sessionId": SESSION,
                    "eventTimestamp": ANY,
                    "payload": [
                        {
                            "conversational": {
                                "content": {"text": "status=COMPLETED"},
                                "role": "ASSISTANT",
                            }
                        }
                    ],
                },
            )
            store = AgentCoreMemoryStore(client, MEMORY_ID, FixedClock())
            context = store.load(ACTOR, SESSION)
            store.save_session_summary(ACTOR, SESSION, "status=COMPLETED")
        assert context.preferences == ["prefers concise reports"]
        assert context.session_summaries == []


class TestEmbeddings:
    def test_titan_v2_request_and_dimension_check(self) -> None:
        client = boto3.client("bedrock-runtime", region_name=REGION)
        expected_body = json.dumps(
            {"inputText": "hello", "dimensions": 3, "normalize": True}
        ).encode()
        with Stubber(client) as stub:
            stub.add_response(
                "invoke_model",
                {
                    "body": _body(json.dumps({"embedding": [0.1, 0.2, 0.3]}).encode()),
                    "contentType": "application/json",
                },
                {
                    "modelId": "amazon.titan-embed-text-v2:0",
                    "body": expected_body,
                    "contentType": "application/json",
                    "accept": "application/json",
                },
            )
            stub.add_response(
                "invoke_model",
                {"body": _body(b'{"embedding": [0.1]}'), "contentType": "application/json"},
            )
            embedder = BedrockEmbedder(client, "amazon.titan-embed-text-v2:0", 3)
            assert embedder.embed("hello") == [0.1, 0.2, 0.3]
            with pytest.raises(DependencyUnavailableError):
                embedder.embed("hello")
