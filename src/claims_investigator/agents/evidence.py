"""Evidence agent: deterministic extraction and normalization of text-based claim artifacts."""

import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from claims_investigator.errors import ClaimsInvestigatorError
from claims_investigator.models.api import ClaimSubmission, DocumentReference
from claims_investigator.models.common import ClaimType, DocumentType
from claims_investigator.models.evidence import (
    EvidenceBundle,
    EvidenceReference,
    EvidenceSource,
    ExtractedField,
    FieldInconsistency,
    MissingInformation,
    NormalizedDocument,
)
from claims_investigator.services.guardrails import find_injection_markers
from claims_investigator.services.ports import ObjectStore
from claims_investigator.storage_keys import normalized_document_key
from claims_investigator.tools.schemas import DocumentMetadata

TEXT_CONTENT_TYPES = frozenset({"text/plain", "text/csv", "application/json"})
MAX_LINES = 500
MAX_PROMPT_CHARS_PER_DOCUMENT = 20_000
REQUIRED_DOCUMENTS: dict[ClaimType, frozenset[DocumentType]] = {
    ClaimType.AUTO: frozenset(
        {DocumentType.CLAIM_FORM, DocumentType.REPAIR_ESTIMATE, DocumentType.INCIDENT_REPORT}
    ),
    ClaimType.PROPERTY: frozenset({DocumentType.CLAIM_FORM, DocumentType.REPAIR_ESTIMATE}),
    ClaimType.TRAVEL: frozenset({DocumentType.CLAIM_FORM, DocumentType.INVOICE}),
}
FIELD_ALIASES: dict[str, frozenset[str]] = {
    "claimed_amount": frozenset(
        {"claimed_amount", "claim_amount", "total_amount", "amount", "total", "invoice_total"}
    ),
    "incident_date": frozenset({"incident_date", "date_of_loss", "loss_date", "date_of_incident"}),
    "policy_reference": frozenset({"policy_reference", "policy_number", "policy_id"}),
}
_KEY_VALUE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _/-]{0,60}?)\s*[:=]\s*(\S.*?)\s*$")
_FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
Status = Literal["EXTRACTED", "EMPTY", "UNSUPPORTED", "FAILED"]


@dataclass(frozen=True, slots=True)
class EvidenceOutput:
    bundle: EvidenceBundle
    document_texts: dict[str, str]
    injection_markers: tuple[str, ...]


def meta_id(name: str) -> str:
    return f"meta:{name}"


def _snake(key: str) -> str | None:
    name = re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")
    return name if _FIELD_NAME.match(name) else None


def _pretty(document_type: DocumentType) -> str:
    return document_type.value.replace("_", " ").lower()


class EvidenceAgent:
    def __init__(self, store: ObjectStore, max_document_bytes: int) -> None:
        self._store = store
        self._max_bytes = max_document_bytes

    def run(
        self, job_id: UUID, submission: ClaimSubmission, metadata: list[DocumentMetadata]
    ) -> EvidenceOutput:
        references, fields = _metadata_evidence(submission)
        missing: list[MissingInformation] = []
        documents: list[NormalizedDocument] = []
        texts: dict[str, str] = {}
        markers = set(find_injection_markers(submission.incident_description))
        present_by_id = {m.document_id: m.present for m in metadata}

        for doc in submission.documents:
            status, text, doc_fields = self._extract(doc, present_by_id.get(doc.document_id, False))
            doc_ref_id = f"doc:{doc.document_id}"
            references.append(
                EvidenceReference(
                    evidence_id=doc_ref_id,
                    source=EvidenceSource.CLAIM_DOCUMENT,
                    document_id=doc.document_id,
                    locator="whole document",
                    description=f"Submitted {_pretty(doc.document_type)} ({status.lower()})",
                )
            )
            if status != "EXTRACTED":
                missing.append(
                    MissingInformation(
                        item=f"Readable {_pretty(doc.document_type)} content",
                        reason=_status_reason(status),
                        related_evidence_ids=[doc_ref_id],
                    )
                )
            for field in doc_fields:
                label = field.name.replace("_", " ")
                references.append(
                    EvidenceReference(
                        evidence_id=field.evidence_id,
                        source=EvidenceSource.CLAIM_DOCUMENT,
                        document_id=doc.document_id,
                        locator=field.evidence_id.split("#", 1)[1],
                        description=f"{label} in {_pretty(doc.document_type)}",
                    )
                )
            fields.extend(doc_fields)
            if text:
                texts[str(doc.document_id)] = text[:MAX_PROMPT_CHARS_PER_DOCUMENT]
                markers.update(find_injection_markers(text))
            normalized = NormalizedDocument(
                document_id=doc.document_id,
                document_type=doc.document_type,
                content_type=doc.content_type,
                source_key=doc.object_key,
                normalized_key=normalized_document_key(
                    submission.claim_id, job_id, doc.document_id
                ),
                extraction_status=status,
                line_count=len(text.splitlines()),
                fields=doc_fields,
            )
            self._store.put_bytes(
                str(normalized.normalized_key),
                normalized.model_dump_json().encode(),
                "application/json",
            )
            documents.append(normalized)

        missing.extend(_missing_required_documents(submission, documents))
        bundle = EvidenceBundle(
            claim_id=submission.claim_id,
            job_id=job_id,
            documents=documents,
            references=references,
            fields=fields,
            missing_information=missing,
            inconsistencies=_inconsistencies(fields, submission),
        )
        return EvidenceOutput(bundle, texts, tuple(sorted(markers)))

    def _extract(
        self, doc: DocumentReference, present: bool
    ) -> tuple[Status, str, list[ExtractedField]]:
        if not present:
            return "FAILED", "", []
        if doc.content_type not in TEXT_CONTENT_TYPES:
            return "UNSUPPORTED", "", []
        try:
            text = self._store.get_bytes(doc.object_key, self._max_bytes).decode("utf-8", "replace")
        except ClaimsInvestigatorError:
            return "FAILED", "", []
        if not text.strip():
            return "EMPTY", "", []
        try:
            fields = _parse(doc.content_type, text, f"doc:{doc.document_id}")
        except ValueError:
            return "FAILED", text, []
        return "EXTRACTED", text, fields


def _status_reason(status: Status) -> str:
    return {
        "FAILED": "The document was not available or could not be parsed.",
        "EMPTY": "The document contained no text.",
        "UNSUPPORTED": "The document format is not supported for automated extraction.",
    }.get(status, "The document could not be processed.")


def _metadata_evidence(
    submission: ClaimSubmission,
) -> tuple[list[EvidenceReference], list[ExtractedField]]:
    values = {
        "claim_type": str(submission.claim_type),
        "claimed_amount": f"{submission.claimed_amount} {submission.currency}",
        "incident_date": submission.incident_date.isoformat(),
        "reported_date": submission.reported_date.isoformat(),
        "policy_reference": submission.policy_reference,
    }
    refs = [
        EvidenceReference(
            evidence_id=meta_id(name),
            source=EvidenceSource.CLAIM_METADATA,
            locator=f"submission field {name}",
            description=f"Submitted {name.replace('_', ' ')}",
        )
        for name in (*values, "incident_description")
    ]
    fields = [
        ExtractedField(name=name, value=value, evidence_id=meta_id(name))
        for name, value in values.items()
    ]
    return refs, fields


def _parse(content_type: str, text: str, prefix: str) -> list[ExtractedField]:
    lines = text.splitlines()[:MAX_LINES]
    pairs: list[tuple[str, str, str]] = []
    if content_type == "application/json":
        for key, value in _flatten(json.loads(text)).items():
            pairs.append((key, value, f"{prefix}#key:{key}"))
    elif content_type == "text/csv":
        rows = list(csv.reader(lines))
        header = [h.strip().lower() for h in rows[0]] if rows else []
        if header[:2] == ["field", "value"]:
            pairs += [
                (r[0], r[1], f"{prefix}#L{i}") for i, r in enumerate(rows[1:], 2) if len(r) > 1
            ]
        elif len(rows) > 1:
            pairs += [(h, v, f"{prefix}#L2") for h, v in zip(rows[0], rows[1], strict=False)]
    else:
        for i, line in enumerate(lines, 1):
            if match := _KEY_VALUE.match(line):
                pairs.append((match.group(1), match.group(2), f"{prefix}#L{i}"))

    fields: dict[str, ExtractedField] = {}
    for raw_key, value, evidence_id in pairs:
        name = _snake(raw_key)
        if name and value.strip():
            fields.setdefault(
                name, ExtractedField(name=name, value=value.strip()[:500], evidence_id=evidence_id)
            )
    return list(fields.values())


def _flatten(data: Any, parent: str = "", depth: int = 0) -> dict[str, str]:
    if not isinstance(data, dict):
        raise ValueError("JSON document must be an object")
    out: dict[str, str] = {}
    for key, value in data.items():
        name = _snake(f"{parent}_{key}" if parent else str(key))
        if not name:
            continue
        if isinstance(value, dict) and depth < 1:
            out.update(_flatten(value, name, depth + 1))
        elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
            out[name] = str(value)
    return out


def _missing_required_documents(
    submission: ClaimSubmission, documents: list[NormalizedDocument]
) -> list[MissingInformation]:
    usable = {d.document_type for d in documents if d.extraction_status == "EXTRACTED"}
    submitted = {d.document_type for d in documents}
    return [
        MissingInformation(
            item=f"{_pretty(required).capitalize()} document",
            reason=(
                f"Expected for {submission.claim_type} claims; "
                + ("submitted but not readable." if required in submitted else "not submitted.")
            ),
            related_evidence_ids=[meta_id("claim_type")],
        )
        for required in sorted(REQUIRED_DOCUMENTS[submission.claim_type] - usable)
    ]


def _inconsistencies(
    fields: list[ExtractedField], submission: ClaimSubmission
) -> list[FieldInconsistency]:
    found: list[FieldInconsistency] = []
    parsers = {
        "claimed_amount": _parse_amount,
        "incident_date": _parse_date,
        "policy_reference": _parse_reference,
    }
    for canonical, aliases in FIELD_ALIASES.items():
        observed: dict[str, list[str]] = {}
        for field in fields:
            if field.name in aliases and (value := parsers[canonical](field.value)) is not None:
                observed.setdefault(str(value), []).append(field.evidence_id)
        if len(observed) > 1:
            found.append(
                FieldInconsistency(
                    field=canonical,
                    observed_values=sorted(observed),
                    evidence_ids=sorted({i for ids in observed.values() for i in ids}),
                )
            )
    if submission.reported_date < submission.incident_date:
        found.append(
            FieldInconsistency(
                field="reported_date",
                observed_values=[
                    f"incident {submission.incident_date.isoformat()}",
                    f"reported {submission.reported_date.isoformat()}",
                ],
                evidence_ids=[meta_id("incident_date"), meta_id("reported_date")],
            )
        )
    return found


def _parse_amount(value: str) -> str | None:
    cleaned = re.sub(r"[^0-9.\-]", "", value.replace(",", ""))
    try:
        return str(Decimal(cleaned).quantize(Decimal("0.01"))) if cleaned else None
    except InvalidOperation:
        return None


def _parse_reference(value: str) -> str | None:
    return value.strip().upper() or None


def _parse_date(value: str) -> str | None:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            parsed: date = datetime.strptime(value.strip()[:10], fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
        return parsed.isoformat()
    return None
