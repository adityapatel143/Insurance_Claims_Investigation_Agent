"""Destroy one environment (platform, web, foundation) and its untracked runtime log groups.

Steps per stack (platform, then web if initialised, then foundation): `terraform plan -destroy` ->
confirm -> apply that saved plan. After the platform stack, AgentCore Runtime log groups for this
environment's runtime are deleted. The bootstrap state bucket is never touched.

Safety: requires `--confirm <env>`; refuses `prod` unless `--allow-prod` (prod deletion protection
and the non-empty data bucket still block destroy until disabled or emptied deliberately).

Example:
  uv run python scripts/destroy_environment.py --env dev --confirm dev
"""

import argparse
import json
import shutil
import subprocess  # nosec B404
import sys

import boto3

from _common import REPO_ROOT, resolve_region
from claims_investigator.gateways.aws import client_config

RUNTIME_LOG_PREFIX = "/aws/bedrock-agentcore/runtimes/"
PLAN_FILE = "destroy.tfplan"
STACKS = ("platform", "foundation")


def terraform(tf_dir: str, *args: str, capture: bool = False) -> str:
    binary = shutil.which("terraform")
    if binary is None:
        sys.exit("terraform not found on PATH.")
    result = subprocess.run(  # noqa: S603  # nosec B603
        [binary, f"-chdir={tf_dir}", *args], check=False, text=True, capture_output=capture
    )
    if result.returncode != 0:
        detail = f" {result.stderr}" if capture else ""
        sys.exit(f"terraform {args[0]} failed ({result.returncode}).{detail}")
    return result.stdout if capture else ""


def runtime_id_from(outputs: dict[str, dict[str, object]]) -> str | None:
    arn = outputs.get("agent_runtime_arn", {}).get("value")
    return str(arn).rsplit("/", 1)[-1] if arn else None


def delete_runtime_log_groups(runtime_id: str, region: str) -> None:
    logs = boto3.client("logs", region_name=region, config=client_config())
    names = [
        group["logGroupName"]
        for page in logs.get_paginator("describe_log_groups").paginate(
            logGroupNamePrefix=RUNTIME_LOG_PREFIX
        )
        for group in page["logGroups"]
        if runtime_id in group["logGroupName"]
    ]
    for name in names:
        logs.delete_log_group(logGroupName=name)
        print(f"Deleted log group {name}")
    if not names:
        print(f"No runtime log groups found for {runtime_id}")


def destroy_stack(env: str, stack: str, *, assume_yes: bool) -> None:
    tf_dir = REPO_ROOT / "infra" / "environments" / env / stack
    terraform(
        str(tf_dir),
        "plan",
        "-destroy",
        "-input=false",
        "-var-file=../common.tfvars",
        f"-out={PLAN_FILE}",
    )
    prompt = f"Type '{env}' to apply this {stack} destroy plan: "
    if not assume_yes and input(prompt).strip() != env:
        (tf_dir / PLAN_FILE).unlink(missing_ok=True)
        sys.exit(f"Aborted; {stack} was not destroyed.")
    terraform(str(tf_dir), "apply", "-input=false", PLAN_FILE)
    (tf_dir / PLAN_FILE).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--env", choices=["dev", "prod"], default="dev")
    parser.add_argument("--confirm", required=True, help="Must equal --env.")
    parser.add_argument("--allow-prod", action="store_true", help="Required to destroy prod.")
    parser.add_argument(
        "--keep-runtime-logs", action="store_true", help="Do not delete runtime log groups."
    )
    parser.add_argument(
        "--yes", action="store_true", help="Skip the interactive prompt after the plan."
    )
    parser.add_argument("--region")
    args = parser.parse_args()

    if args.confirm != args.env:
        sys.exit(f"Refusing: --confirm must be '{args.env}'.")
    if args.env == "prod" and not args.allow_prod:
        sys.exit("Refusing to destroy prod without --allow-prod.")
    env_dir = REPO_ROOT / "infra" / "environments" / args.env
    for stack in STACKS:
        if not (env_dir / stack / ".terraform").is_dir():
            sys.exit(f"{env_dir / stack} is not initialised; run: tf_init.sh {args.env} {stack}")
    if not (env_dir / "common.tfvars").is_file():
        sys.exit(f"{env_dir / 'common.tfvars'} not found; copy common.tfvars.example")
    if not (REPO_ROOT / "dist" / "lambda.zip").is_file():
        sys.exit(
            "dist/lambda.zip is required to evaluate the configuration; "
            "run: scripts/sh/build_lambda.sh"
        )

    region = resolve_region(args.region)
    outputs = json.loads(
        terraform(str(env_dir / "platform"), "output", "-json", capture=True) or "{}"
    )
    runtime_id = runtime_id_from(outputs)

    destroy_stack(args.env, "platform", assume_yes=args.yes)
    if runtime_id and not args.keep_runtime_logs:
        delete_runtime_log_groups(runtime_id, region)
    if (env_dir / "web" / ".terraform").is_dir():
        destroy_stack(args.env, "web", assume_yes=args.yes)
    else:
        print(f"Skipping web stack ({env_dir / 'web'} is not initialised).")
    destroy_stack(args.env, "foundation", assume_yes=args.yes)

    print(
        "\nDone. Not removed by this script:\n"
        "  - Terraform state bucket and objects (infra/bootstrap; prevent_destroy)\n"
        "  - Previously managed KMS keys may be pending deletion\n"
        f"  - Local files: {env_dir}/common.tfvars, backend.hcl, platform/terraform.tfvars, dist/,"
        " build/ (scripts/sh/clean.sh), Docker images"
    )


if __name__ == "__main__":
    main()
