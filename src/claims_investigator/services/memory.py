"""Hashing of principals into memory actor IDs and privacy-preserving session summaries."""

import hashlib
import logging
from uuid import UUID

from claims_investigator.errors import DependencyUnavailableError
from claims_investigator.logging import get_logger, log_event
from claims_investigator.models.result import InvestigationResult
from claims_investigator.services.ports import MemoryContext, MemoryStore

_LOG = get_logger(__name__)


def actor_id_for(principal: str) -> str:
    return hashlib.sha256(principal.encode()).hexdigest()


def memory_session_id(job_id: UUID) -> str:
    return f"claims-job-{job_id}"


def build_session_summary(result: InvestigationResult) -> str:
    """Summaries contain only codes and counts, never claim text or identities."""
    signal_codes = sorted({s.code for s in result.anomaly_signals})
    risk_levels = sorted({f"{r.category}:{r.level}" for r in result.risk_indicators})
    reasons = sorted(str(r) for r in result.review_reasons)
    return (
        f"status={result.status}; confidence={result.confidence:.2f}; "
        f"anomaly_signal_codes={','.join(signal_codes) or 'none'}; "
        f"risk_indicators={','.join(risk_levels) or 'none'}; "
        f"review_reasons={','.join(reasons) or 'none'}; "
        f"missing_information_count={len(result.missing_information)}; "
        f"retrieved_source_count={len(result.retrieved_sources)}"
    )


class MemoryService:
    """Memory is non-critical: failures degrade to empty context and are logged."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def load(self, actor_id: str, job_id: UUID) -> MemoryContext:
        try:
            return self._store.load(actor_id, memory_session_id(job_id))
        except DependencyUnavailableError:
            log_event(_LOG, logging.WARNING, "memory_load_failed", job_id=str(job_id))
            return MemoryContext()

    def save_summary(self, actor_id: str, result: InvestigationResult) -> None:
        try:
            self._store.save_session_summary(
                actor_id, memory_session_id(result.job_id), build_session_summary(result)
            )
        except DependencyUnavailableError:
            log_event(_LOG, logging.WARNING, "memory_save_failed", job_id=str(result.job_id))
