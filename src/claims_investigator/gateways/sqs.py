"""SQS publisher for investigation messages."""

from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from claims_investigator.gateways.aws import raise_translated
from claims_investigator.models.messages import InvestigationMessage

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient


class SqsQueuePublisher:
    def __init__(self, client: "SQSClient", queue_url: str) -> None:
        self._sqs = client
        self._queue_url = queue_url

    def send(self, message: InvestigationMessage) -> str:
        try:
            response = self._sqs.send_message(
                QueueUrl=self._queue_url,
                MessageBody=message.model_dump_json(),
                MessageAttributes={
                    "schema_version": {"DataType": "String", "StringValue": message.schema_version},
                    "correlation_id": {"DataType": "String", "StringValue": message.correlation_id},
                },
            )
        except (ClientError, BotoCoreError) as exc:
            raise_translated(exc, "sqs.send_message")
        return response["MessageId"]
