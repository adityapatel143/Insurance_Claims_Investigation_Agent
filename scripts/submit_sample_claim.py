"""Upload a synthetic sample claim through the API and submit it for asynchronous investigation.

Example:
  uv run python scripts/submit_sample_claim.py \
    --api-endpoint "$(terraform -chdir=infra/environments/dev/platform output -raw api_endpoint)" \
    --scenario inconsistent
"""

import argparse
import json
import secrets
import uuid
from typing import Any

from _common import SAMPLE_DATA, post_presigned, resolve_region, signed_request

SCENARIOS = sorted(p.name for p in (SAMPLE_DATA / "claims").iterdir() if p.is_dir())


def build_submission(scenario: str, region: str, api: str, claim_id: str | None) -> dict[str, Any]:
    folder = SAMPLE_DATA / "claims" / scenario
    manifest: dict[str, Any] = json.loads((folder / "claim.json").read_text("utf-8"))
    claim_id = claim_id or f"{manifest['claim_id_prefix']}-{secrets.token_hex(3).upper()}"

    references = []
    for doc in manifest["documents"]:
        upload = signed_request(
            "POST",
            f"{api}/uploads",
            region,
            {"claim_id": claim_id, "file_name": doc["file"], "content_type": doc["content_type"]},
        )
        post_presigned(
            upload["upload_url"], upload["upload_fields"], folder / doc["file"], doc["content_type"]
        )
        print(f"Uploaded {doc['file']} as document {upload['document_id']}")
        references.append(
            {
                "document_id": upload["document_id"],
                "object_key": upload["object_key"],
                "document_type": doc["document_type"],
                "content_type": doc["content_type"],
            }
        )

    fields = (
        "policy_reference",
        "claim_type",
        "incident_date",
        "reported_date",
        "claimed_amount",
        "currency",
        "incident_description",
    )
    return {
        "client_request_id": str(uuid.uuid4()),
        "claim_id": claim_id,
        **{name: manifest[name] for name in fields},
        "documents": references,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--api-endpoint", required=True, help="HTTP API base URL (Terraform output api_endpoint)."
    )
    parser.add_argument("--scenario", choices=SCENARIOS, default="complete")
    parser.add_argument("--claim-id", help="Override the generated synthetic claim ID.")
    parser.add_argument("--region")
    args = parser.parse_args()

    region = resolve_region(args.region)
    api = args.api_endpoint.rstrip("/")
    submission = build_submission(args.scenario, region, api, args.claim_id)
    accepted = signed_request("POST", f"{api}/claims", region, submission)
    print(json.dumps(accepted, indent=2))
    print(
        "Check status with:\n  uv run python scripts/check_job.py "
        f"--api-endpoint {api} --claim-id {accepted['claim_id']} "
        f"--job-id {accepted['job_id']} --wait"
    )


if __name__ == "__main__":
    main()
