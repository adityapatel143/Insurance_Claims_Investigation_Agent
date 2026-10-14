"""S3 adapter for the single data bucket (bucket default encryption applies)."""

from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from claims_investigator.errors import RequestValidationError
from claims_investigator.gateways.aws import error_code, raise_translated
from claims_investigator.services.ports import ObjectMetadata, PresignedPost

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class S3ObjectStore:
    def __init__(self, client: "S3Client", bucket: str) -> None:
        self._s3 = client
        self._bucket = bucket

    def presign_post(
        self, key: str, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedPost:
        response = self._s3.generate_presigned_post(
            Bucket=self._bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, max_bytes]],
            ExpiresIn=expires_in,
        )
        return PresignedPost(
            url=str(response["url"]),
            fields={k: str(v) for k, v in response["fields"].items()},
        )

    def presign_get(self, key: str, expires_in: int) -> str:
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def head(self, key: str) -> ObjectMetadata | None:
        try:
            response = self._s3.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if error_code(exc) in _NOT_FOUND_CODES:
                return None
            raise_translated(exc, "s3.head_object")
        except BotoCoreError as exc:
            raise_translated(exc, "s3.head_object")
        return ObjectMetadata(
            key=key,
            size_bytes=response["ContentLength"],
            content_type=response.get("ContentType", ""),
        )

    def get_bytes(self, key: str, max_bytes: int) -> bytes:
        try:
            response = self._s3.get_object(
                Bucket=self._bucket, Key=key, Range=f"bytes=0-{max_bytes}"
            )
            data = response["Body"].read()
        except (ClientError, BotoCoreError) as exc:
            raise_translated(exc, "s3.get_object")
        if len(data) > max_bytes:
            raise RequestValidationError("object exceeds the maximum readable size")
        return data

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._s3.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
        except (ClientError, BotoCoreError) as exc:
            raise_translated(exc, "s3.put_object")

    def move(self, source_key: str, destination_key: str) -> None:
        try:
            self._s3.copy_object(
                Bucket=self._bucket,
                Key=destination_key,
                CopySource={"Bucket": self._bucket, "Key": source_key},
            )
            self._s3.delete_object(Bucket=self._bucket, Key=source_key)
        except (ClientError, BotoCoreError) as exc:
            raise_translated(exc, "s3.move")
