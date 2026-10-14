"""Assemble the static web app (web/ + config.json + synthetic samples) into a deployable folder.

Offline: copies files only. `--api-endpoint` is written to config.json as the default endpoint
(users can still change it in the page). Synthetic sample scenarios from sample-data/claims/ are
copied to samples/ with an index.json the page uses to prefill the form.

Example:
  uv run python scripts/build_web.py --out build/web \
    --api-endpoint "$(terraform -chdir=infra/environments/dev/platform output -raw api_endpoint)"
"""

import argparse
import json
import shutil
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from _common import REPO_ROOT, SAMPLE_DATA

WEB_SRC = REPO_ROOT / "web"
EXCLUDED = shutil.ignore_patterns("tests", "package.json", "node_modules", ".*")


def sample_index(samples_out: Path) -> list[dict[str, Any]]:
    scenarios = []
    for folder in sorted(p for p in (SAMPLE_DATA / "claims").iterdir() if p.is_dir()):
        manifest: dict[str, Any] = json.loads((folder / "claim.json").read_text("utf-8"))
        target = samples_out / folder.name
        target.mkdir(parents=True)
        for doc in manifest["documents"]:
            shutil.copy2(folder / doc["file"], target / doc["file"])
        shutil.copy2(folder / "claim.json", target / "claim.json")
        scenarios.append({"scenario": folder.name, "path": f"samples/{folder.name}/claim.json"})
    return scenarios


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "build" / "web")
    parser.add_argument("--api-endpoint", default="", help="Default HTTP API base URL (https).")
    args = parser.parse_args()

    endpoint = args.api_endpoint.strip().rstrip("/")
    if endpoint and urllib.parse.urlparse(endpoint).scheme != "https":
        sys.exit(f"Refusing non-HTTPS API endpoint: {endpoint}")

    out: Path = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(WEB_SRC, out, ignore=EXCLUDED)
    (out / "config.json").write_text(json.dumps({"apiEndpoint": endpoint}, indent=2) + "\n")
    scenarios = sample_index(out / "samples")
    (out / "samples" / "index.json").write_text(json.dumps(scenarios, indent=2) + "\n")
    print(f"Web app assembled in {out} ({len(scenarios)} sample scenarios)")


if __name__ == "__main__":
    main()
