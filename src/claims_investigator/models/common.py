"""Shared constrained identifier and value types."""

import re
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, Field, StringConstraints


class ClaimType(StrEnum):
    AUTO = "AUTO"
    PROPERTY = "PROPERTY"
    TRAVEL = "TRAVEL"


class DocumentType(StrEnum):
    CLAIM_FORM = "CLAIM_FORM"
    INVOICE = "INVOICE"
    REPAIR_ESTIMATE = "REPAIR_ESTIMATE"
    INCIDENT_REPORT = "INCIDENT_REPORT"
    CORRESPONDENCE = "CORRESPONDENCE"
    OTHER = "OTHER"


ClaimId = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9-]{3,63}$")]
JobId = UUID
DocumentId = UUID
CorrelationId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9-]{8,64}$")]
FileName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
EvidenceId = Annotated[str, StringConstraints(pattern=r"^[a-z]+:[A-Za-z0-9._:#/-]{1,200}$")]

_PROHIBITED_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bfraudulent\b",
        r"\bfraudster\b",
        r"\bcommitt?ed\s+fraud\b",
        r"\bis\s+(a\s+)?fraud\b",
        r"\b(approve[sd]?|deny|denie[sd]|reject(s|ed)?)\s+(the\s+|this\s+)?claim\b",
        r"\b(in)?eligible\s+for\s+(payment|payout|coverage)\b",
        r"\bdiagnos(is|es|ed|e)\b",
    )
)


def ensure_advisory_language(text: str) -> str:
    """Reject adjudication, fraud-labelling, or diagnostic wording in generated text."""
    for pattern in _PROHIBITED_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"prohibited wording matched: {pattern.pattern}")
    return text


AdvisoryText = Annotated[
    str, StringConstraints(min_length=1, max_length=2000), AfterValidator(ensure_advisory_language)
]
ShortAdvisoryText = Annotated[
    str, StringConstraints(min_length=1, max_length=300), AfterValidator(ensure_advisory_language)
]
