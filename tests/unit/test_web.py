"""Web app checks: JS unit tests (node --test) and SigV4 parity with botocore."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

WEB = Path(__file__).resolve().parents[2] / "web"
NODE = shutil.which("node")
FAKE_SECRET = "secret/key+example"  # pragma: allowlist secret
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def _node(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    assert NODE is not None
    return subprocess.run(  # noqa: S603
        [NODE, *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        cwd=WEB,
        timeout=120,
    )


def test_js_unit_tests_pass() -> None:
    result = _node("--test", "tests/")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("method", "url", "body", "token"),
    [
        (
            "POST",
            "https://abc123.execute-api.us-east-1.amazonaws.com/claims",
            '{"a": 1}',
            "tok/en+==",
        ),
        ("GET", "https://abc123.execute-api.eu-west-2.amazonaws.com/claims/CLM-1/jobs/x", "", None),
        ("POST", "https://abc123.execute-api.us-east-1.amazonaws.com/uploads", "{}", None),
    ],
)
def test_sigv4_matches_botocore(method: str, url: str, body: str, token: str | None) -> None:
    region = url.split(".")[2]
    credentials = Credentials("AKIDEXAMPLE", FAKE_SECRET, token)
    headers = {"x-correlation-id": "web-12345678"}
    if body:
        headers["content-type"] = "application/json"
    request = AWSRequest(method=method, url=url, data=body.encode(), headers=headers)
    SigV4Auth(credentials, "execute-api", region).add_auth(request)
    expected = dict(request.headers.items())

    payload = {
        "method": method,
        "url": url,
        "headers": headers,
        "body": body,
        "region": region,
        "service": "execute-api",
        "credentials": {
            "accessKeyId": credentials.access_key,
            "secretAccessKey": credentials.secret_key,
            "sessionToken": token,
        },
        "date": expected["X-Amz-Date"],
    }
    result = _node("tests/sign_cli.js", stdin=json.dumps(payload))
    assert result.returncode == 0, result.stderr
    signed = json.loads(result.stdout)
    assert signed["authorization"] == expected["Authorization"]
    assert signed.get("x-amz-security-token") == expected.get("X-Amz-Security-Token")
