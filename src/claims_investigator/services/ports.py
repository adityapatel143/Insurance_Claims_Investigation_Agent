"""Protocol interfaces for every external boundary; AWS adapters in `gateways/` implement these."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Event
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from claims_investigator.models.common import ClaimType
from claims_investigator.models.findings import RetrievedChunk, SourceType
from claims_investigator.models.jobs import FailureCategory, JobRecord, JobStatus
from claims_investigator.models.messages import InvestigationMessage, RuntimeInvocation
from claims_investigator.tools.schemas import (
    DocumentMetadata,
    PersistFindingsResult,
    ToolRequest,
)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    key: str
    size_bytes: int
    content_type: str


@dataclass(frozen=True, slots=True)
class PresignedPost:
    url: str
    fields: dict[str, str]


class ObjectStore(Protocol):
    def presign_post(
        self, key: str, content_type: str, max_bytes: int, expires_in: int
    ) -> PresignedPost: ...

    def presign_get(self, key: str, expires_in: int) -> str: ...

    def head(self, key: str) -> ObjectMetadata | None: ...

    def get_bytes(self, key: str, max_bytes: int) -> bytes: ...

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...

    def move(self, source_key: str, destination_key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class JobUpdate:
    """Attributes set alongside a status transition; `None` fields are left untouched."""

    dispatched_at: datetime | None = None
    processing_deadline: datetime | None = None
    completed_at: datetime | None = None
    failure_category: FailureCategory | None = None
    report_key: str | None = None
    report_markdown_key: str | None = None
    human_review_required: bool | None = None
    anomaly_signal_count: int | None = None


class JobRepository(Protocol):
    def create(self, job: JobRecord) -> bool:
        """Conditionally create; return False if the job_id already exists."""
        ...

    def get(self, job_id: UUID) -> JobRecord | None: ...

    def transition(
        self,
        job_id: UUID,
        expected: JobStatus,
        target: JobStatus,
        now: datetime,
        update: JobUpdate,
    ) -> bool:
        """Conditionally move `expected -> target`; return False if the condition failed."""
        ...

    def acquire_dispatch_lease(
        self, job_id: UUID, now: datetime, lease_until: datetime
    ) -> bool: ...

    def release_dispatch_lease(self, job_id: UUID) -> None: ...

    def record_enqueue(self, job_id: UUID) -> int:
        """Atomically increment and return the number of queue sends for the job."""
        ...


class QueuePublisher(Protocol):
    def send(self, message: InvestigationMessage) -> str: ...


class AgentRuntimeInvoker(Protocol):
    def invoke(self, session_id: str, payload: RuntimeInvocation) -> None: ...


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class SearchHit:
    document_id: str
    chunk_id: str
    source_type: SourceType
    source_uri: str
    title: str
    text: str
    score: float


class VectorSearch(Protocol):
    def hybrid_search(
        self,
        query_text: str,
        query_vector: Sequence[float],
        source_type: SourceType,
        claim_type: ClaimType,
        top_k: int,
    ) -> list[SearchHit]: ...


@dataclass(frozen=True, slots=True)
class MemoryContext:
    preferences: list[str] = field(default_factory=list)
    session_summaries: list[str] = field(default_factory=list)


class MemoryStore(Protocol):
    def load(self, actor_id: str, session_id: str) -> MemoryContext: ...

    def save_session_summary(self, actor_id: str, session_id: str, summary: str) -> None: ...


class InvestigationTools(Protocol):
    """Approved AgentCore Gateway tools, as seen by the runtime."""

    def mark_processing(self, request: ToolRequest, deadline: datetime) -> None: ...

    def mark_failed(self, request: ToolRequest, category: FailureCategory) -> None: ...

    def get_claim_document_metadata(self, request: ToolRequest) -> list[DocumentMetadata]: ...

    def get_policy_guidance(
        self, request: ToolRequest, claim_type: ClaimType, query: str
    ) -> list[RetrievedChunk]: ...

    def search_similar_claims(
        self, request: ToolRequest, claim_type: ClaimType, query: str
    ) -> list[RetrievedChunk]: ...

    def persist_investigation_findings(
        self, request: ToolRequest, result_json: str, report_markdown: str
    ) -> PersistFindingsResult: ...


class StructuredModel(Protocol):
    """Guardrailed model call returning a validated Pydantic object.

    Raises GuardrailInterventionError when blocked and ModelOutputError when output stays invalid.
    """

    def generate[T: BaseModel](
        self, system_prompt: str, prompt: str, output_model: type[T], cancel: Event
    ) -> T: ...
