"""Presigned upload creation with content-type allowlist and size limits."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from claims_investigator.errors import RequestValidationError
from claims_investigator.models.api import UploadRequest, UploadResponse
from claims_investigator.services.ports import Clock, ObjectStore, utc_now
from claims_investigator.storage_keys import intake_document_key


@dataclass(frozen=True, slots=True)
class UploadPolicy:
    max_upload_bytes: int
    allowed_content_types: frozenset[str]

    def check_content_type(self, content_type: str) -> None:
        if content_type.lower() not in self.allowed_content_types:
            raise RequestValidationError(f"content type {content_type!r} is not allowed")


class UploadService:
    def __init__(
        self,
        store: ObjectStore,
        policy: UploadPolicy,
        expiry_seconds: int,
        clock: Clock = utc_now,
        new_document_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._store = store
        self._policy = policy
        self._expiry_seconds = expiry_seconds
        self._clock = clock
        self._new_document_id = new_document_id

    def create_upload(self, request: UploadRequest) -> UploadResponse:
        self._policy.check_content_type(request.content_type)
        document_id = self._new_document_id()
        key = intake_document_key(request.claim_id, document_id, request.file_name)
        presigned = self._store.presign_post(
            key, request.content_type, self._policy.max_upload_bytes, self._expiry_seconds
        )
        return UploadResponse(
            claim_id=request.claim_id,
            document_id=document_id,
            object_key=key,
            upload_url=presigned.url,
            upload_fields=presigned.fields,
            content_type=request.content_type,
            max_size_bytes=self._policy.max_upload_bytes,
            expires_at=self._clock() + timedelta(seconds=self._expiry_seconds),
        )
