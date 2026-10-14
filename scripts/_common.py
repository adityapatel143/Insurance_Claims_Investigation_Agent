"""Shared helpers for operator scripts: SigV4 API calls, presigned POST uploads, front matter."""

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.client import HTTPResponse
from pathlib import Path
from typing import Any

import boto3
import certifi
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATA = REPO_ROOT / "sample-data"
HTTP_TIMEOUT = 30
# Explicit CA bundle: uv-managed Python on macOS may not locate the system trust store for urllib.
TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def https_open(request: urllib.request.Request | str) -> HTTPResponse:
    """Open an HTTPS URL or request with certificate verification against the certifi bundle."""
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    require_https(url)
    response: HTTPResponse = urllib.request.urlopen(  # noqa: S310  # nosec B310
        request, timeout=HTTP_TIMEOUT, context=TLS_CONTEXT
    )
    return response


def resolve_region(explicit: str | None) -> str:
    region = explicit or os.environ.get("AWS_REGION") or boto3.Session().region_name
    if not region:
        sys.exit("Region not set: pass --region or set AWS_REGION.")
    return region


def host_of(endpoint: str) -> str:
    """Accept a bare host or an https URL (Terraform outputs the URL)."""
    return urllib.parse.urlparse(endpoint).hostname or endpoint


def require_https(url: str) -> str:
    if urllib.parse.urlparse(url).scheme != "https":
        sys.exit(f"Refusing non-HTTPS URL: {url}")
    return url


def signed_request(
    method: str, url: str, region: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Call the HTTP API with SigV4 (service `execute-api`) using the caller's credentials."""
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        sys.exit("No AWS credentials found for SigV4 signing.")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"content-type": "application/json", "x-correlation-id": f"cli-{uuid.uuid4()}"}
    aws_request = AWSRequest(method=method, url=require_https(url), data=data, headers=headers)
    SigV4Auth(credentials.get_frozen_credentials(), "execute-api", region).add_auth(aws_request)
    request = urllib.request.Request(  # noqa: S310
        aws_request.url, data=data, headers=dict(aws_request.headers.items()), method=method
    )
    try:
        with https_open(request) as response:
            result: dict[str, Any] = json.loads(response.read())
            return result
    except urllib.error.HTTPError as exc:
        sys.exit(
            f"{method} {url} failed with HTTP {exc.code}: {exc.read().decode(errors='replace')}"
        )


def post_presigned(url: str, fields: dict[str, str], file_path: Path, content_type: str) -> None:
    """Upload a file with an S3 presigned POST; the file part must come last."""
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in fields.items()
    ]
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{file_path.name}"\r\nContent-Type: {content_type}\r\n\r\n'
        ).encode()
        + file_path.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(  # noqa: S310
        require_https(url),
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        https_open(request).close()
    except urllib.error.HTTPError as exc:
        sys.exit(f"Upload of {file_path.name} failed with HTTP {exc.code}: {exc.read()[:500]!r}")


def read_front_matter(path: Path) -> tuple[dict[str, str], str]:
    """Parse a minimal `---`-delimited `key: value` header; return (metadata, body)."""
    text = path.read_text("utf-8")
    if not text.startswith("---\n"):
        return {}, text
    header, _, body = text[4:].partition("\n---\n")
    metadata = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            metadata[key.strip()] = value.strip()
    return metadata, body
