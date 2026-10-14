"""DynamoDB job repository using single-item conditional writes (ADR 0003)."""

from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError

from claims_investigator.gateways.aws import error_code, raise_translated
from claims_investigator.models.jobs import JobRecord, JobStatus
from claims_investigator.services.ports import JobUpdate

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import Table

_CONDITION_FAILED = "ConditionalCheckFailedException"
_INT_FIELDS = ("document_count", "enqueue_count", "anomaly_signal_count", "expires_at")


def _ts(value: datetime) -> str:
    """Fixed-width UTC timestamp so string comparison in conditions is chronological."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _to_attr(value: object) -> Any:
    if isinstance(value, datetime):
        return _ts(value)
    if isinstance(value, (UUID, Enum)):
        return str(value)
    return value


def job_to_item(job: JobRecord) -> dict[str, Any]:
    return {k: _to_attr(v) for k, v in job.model_dump(mode="python", exclude_none=True).items()}


def item_to_job(item: dict[str, Any]) -> JobRecord:
    data = dict(item)
    for name in _INT_FIELDS:
        if isinstance(data.get(name), Decimal):
            data[name] = int(data[name])
    return JobRecord.model_validate(data)


class DynamoJobRepository:
    def __init__(self, table: "Table") -> None:
        self._table = table

    def create(self, job: JobRecord) -> bool:
        try:
            self._table.put_item(
                Item=job_to_item(job), ConditionExpression="attribute_not_exists(job_id)"
            )
        except ClientError as exc:
            if error_code(exc) == _CONDITION_FAILED:
                return False
            raise_translated(exc, "dynamodb.put_item")
        except BotoCoreError as exc:
            raise_translated(exc, "dynamodb.put_item")
        return True

    def get(self, job_id: UUID) -> JobRecord | None:
        try:
            response = self._table.get_item(Key={"job_id": str(job_id)}, ConsistentRead=True)
        except (ClientError, BotoCoreError) as exc:
            raise_translated(exc, "dynamodb.get_item")
        item = response.get("Item")
        return item_to_job(dict(item)) if item else None

    def transition(
        self,
        job_id: UUID,
        expected: JobStatus,
        target: JobStatus,
        now: datetime,
        update: JobUpdate,
    ) -> bool:
        values: dict[str, Any] = {
            ":expected": str(expected),
            ":target": str(target),
            ":now": _ts(now),
        }
        sets = ["#status = :target", "updated_at = :now"]
        for field in fields(update):
            value = getattr(update, field.name)
            if value is not None:
                sets.append(f"{field.name} = :{field.name}")
                values[f":{field.name}"] = _to_attr(value)
        return self._conditional_update(
            job_id,
            f"SET {', '.join(sets)} REMOVE dispatch_lease_until",
            "#status = :expected",
            values,
        )

    def acquire_dispatch_lease(self, job_id: UUID, now: datetime, lease_until: datetime) -> bool:
        return self._conditional_update(
            job_id,
            "SET dispatch_lease_until = :until, updated_at = :now",
            "#status = :queued AND "
            "(attribute_not_exists(dispatch_lease_until) OR dispatch_lease_until < :now)",
            {":until": _ts(lease_until), ":now": _ts(now), ":queued": str(JobStatus.QUEUED)},
        )

    def release_dispatch_lease(self, job_id: UUID) -> None:
        try:
            self._table.update_item(
                Key={"job_id": str(job_id)},
                UpdateExpression="REMOVE dispatch_lease_until",
                ConditionExpression="attribute_exists(job_id)",
            )
        except ClientError as exc:
            if error_code(exc) != _CONDITION_FAILED:
                raise_translated(exc, "dynamodb.update_item")
        except BotoCoreError as exc:
            raise_translated(exc, "dynamodb.update_item")

    def record_enqueue(self, job_id: UUID) -> int:
        try:
            response = self._table.update_item(
                Key={"job_id": str(job_id)},
                UpdateExpression="ADD enqueue_count :one",
                ConditionExpression="attribute_exists(job_id)",
                ExpressionAttributeValues={":one": 1},
                ReturnValues="UPDATED_NEW",
            )
        except (ClientError, BotoCoreError) as exc:
            raise_translated(exc, "dynamodb.update_item")
        return int(str(response["Attributes"]["enqueue_count"]))

    def _conditional_update(
        self, job_id: UUID, expression: str, condition: str, values: dict[str, Any]
    ) -> bool:
        try:
            self._table.update_item(
                Key={"job_id": str(job_id)},
                UpdateExpression=expression,
                ConditionExpression=condition,
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues=values,
            )
        except ClientError as exc:
            if error_code(exc) == _CONDITION_FAILED:
                return False
            raise_translated(exc, "dynamodb.update_item")
        except BotoCoreError as exc:
            raise_translated(exc, "dynamodb.update_item")
        return True
