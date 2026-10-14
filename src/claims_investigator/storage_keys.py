"""Single source of truth for S3 object key layout."""

from uuid import UUID

INTAKE_PREFIX = "intake/"
NORMALIZED_PREFIX = "normalized/"
REPORTS_PREFIX = "reports/"
QUARANTINE_PREFIX = "quarantine/"
SAMPLE_DATA_PREFIX = "sample-data/"


def intake_document_prefix(claim_id: str, document_id: UUID) -> str:
    return f"{INTAKE_PREFIX}{claim_id}/{document_id}/"


def intake_document_key(claim_id: str, document_id: UUID, file_name: str) -> str:
    return f"{intake_document_prefix(claim_id, document_id)}{file_name}"


def quarantine_key(intake_key: str) -> str:
    return f"{QUARANTINE_PREFIX}{intake_key.removeprefix(INTAKE_PREFIX)}"


def submission_key(claim_id: str, job_id: UUID) -> str:
    return f"{NORMALIZED_PREFIX}{claim_id}/{job_id}/submission.json"


def normalized_document_key(claim_id: str, job_id: UUID, document_id: UUID) -> str:
    return f"{NORMALIZED_PREFIX}{claim_id}/{job_id}/documents/{document_id}.json"


def report_json_key(claim_id: str, job_id: UUID) -> str:
    return f"{REPORTS_PREFIX}{claim_id}/{job_id}/report.json"


def report_markdown_key(claim_id: str, job_id: UUID) -> str:
    return f"{REPORTS_PREFIX}{claim_id}/{job_id}/report.md"
