"""Check (and optionally wait for) an investigation job; optionally download the advisory report.

Example:
  uv run python scripts/check_job.py --api-endpoint "$API" --claim-id CLM-SYN-AUTO-1A2B3C \
    --job-id <job_id> --wait --download-report report.json
"""

import argparse
import json
import time
from pathlib import Path

from _common import https_open, resolve_region, signed_request

TERMINAL = {"COMPLETED", "REVIEW_REQUIRED", "FAILED"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api-endpoint", required=True)
    parser.add_argument("--claim-id", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--region")
    parser.add_argument(
        "--wait", action="store_true", help="Poll until the job reaches a terminal state."
    )
    parser.add_argument("--interval", type=int, default=15, help="Polling interval in seconds.")
    parser.add_argument("--timeout", type=int, default=1800, help="Maximum wait in seconds.")
    parser.add_argument("--download-report", type=Path, help="Write the JSON report to this path.")
    args = parser.parse_args()

    region = resolve_region(args.region)
    url = f"{args.api_endpoint.rstrip('/')}/claims/{args.claim_id}/jobs/{args.job_id}"
    deadline = time.monotonic() + args.timeout
    status = signed_request("GET", url, region)
    while args.wait and status["status"] not in TERMINAL and time.monotonic() < deadline:
        print(f"{status['status']} (updated {status['updated_at']})")
        time.sleep(args.interval)
        status = signed_request("GET", url, region)

    report_url = status.pop("report_url", None)
    print(json.dumps(status, indent=2))
    if status["status"] == "REVIEW_REQUIRED":
        print("Advisory result: human review is required before any decision.")

    if args.download_report:
        if not report_url:
            raise SystemExit(
                "No report URL available (job not finished or caller is not the submitter)."
            )
        with https_open(report_url) as response:
            args.download_report.write_bytes(response.read())
        print(f"Report written to {args.download_report}")


if __name__ == "__main__":
    main()
