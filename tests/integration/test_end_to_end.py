"""Opt-in end-to-end test against a deployed stack (never runs by default).

Run only with explicit approval and a deployed dev stack:
  CLAIMS_IT_API_ENDPOINT=https://<api-id>.execute-api.<region>.amazonaws.com \
  uv run pytest -m integration tests/integration
Uses the caller's AWS credentials (SigV4) and synthetic fixture documents only.
"""

import json
import os
import ssl
import time
import urllib.request
import uuid
from typing import Any

import boto3
import certifi
import pytest
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from tests.fakes import FIXTURES

TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())

pytestmark = pytest.mark.integration
ENDPOINT = os.environ.get("CLAIMS_IT_API_ENDPOINT", "")
TERMINAL = {"COMPLETED", "REVIEW_REQUIRED", "FAILED"}


def _signed(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    session = boto3.Session()
    data = json.dumps(body).encode() if body is not None else None
    request = AWSRequest(
        method=method,
        url=f"{ENDPOINT}{path}",
        data=data,
        headers={"content-type": "application/json"},
    )
    SigV4Auth(
        session.get_credentials(), "execute-api", session.region_name or "us-east-1"
    ).add_auth(request)
    prepared = urllib.request.Request(  # noqa: S310
        request.url, data=data, headers=dict(request.headers), method=method
    )
    with urllib.request.urlopen(prepared, timeout=30, context=TLS_CONTEXT) as response:  # noqa: S310
        result: dict[str, Any] = json.loads(response.read())
        return result


def _upload(claim_id: str, file_name: str, content_type: str) -> dict[str, Any]:
    upload = _signed(
        "POST",
        "/uploads",
        {"claim_id": claim_id, "file_name": file_name, "content_type": content_type},
    )
    body = (FIXTURES / "documents" / file_name).read_bytes()
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, v in upload["upload_fields"].items()
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode()
        + body
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(  # noqa: S310
        upload["upload_url"],
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    urllib.request.urlopen(request, timeout=30, context=TLS_CONTEXT).close()  # noqa: S310
    return upload


@pytest.mark.skipif(not ENDPOINT, reason="CLAIMS_IT_API_ENDPOINT not set")
def test_synthetic_claim_reaches_a_terminal_advisory_state() -> None:
    claim_id = f"CLM-IT-{uuid.uuid4().hex[:8].upper()}"
    documents = [
        ("claim_form.txt", "text/plain", "CLAIM_FORM"),
        ("repair_estimate.csv", "text/csv", "REPAIR_ESTIMATE"),
        ("incident_report.json", "application/json", "INCIDENT_REPORT"),
    ]
    refs = []
    for file_name, content_type, document_type in documents:
        upload = _upload(claim_id, file_name, content_type)
        refs.append(
            {
                "document_id": upload["document_id"],
                "object_key": upload["object_key"],
                "document_type": document_type,
                "content_type": content_type,
            }
        )
    accepted = _signed(
        "POST",
        "/claims",
        {
            "client_request_id": str(uuid.uuid4()),
            "claim_id": claim_id,
            "policy_reference": "POL-SYN-1001",
            "claim_type": "AUTO",
            "incident_date": "2025-05-02",
            "reported_date": "2025-05-04",
            "claimed_amount": "1250.00",
            "currency": "USD",
            "incident_description": "SYNTHETIC integration test claim.",
            "documents": refs,
        },
    )
    assert accepted["status"] == "QUEUED"

    deadline = time.monotonic() + 900
    status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status = _signed("GET", accepted["status_url"])
        if status["status"] in TERMINAL:
            break
        time.sleep(15)
    assert status["status"] in {"COMPLETED", "REVIEW_REQUIRED"}
    assert status.get("report_url")
