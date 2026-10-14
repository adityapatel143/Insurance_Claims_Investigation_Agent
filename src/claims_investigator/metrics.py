"""CloudWatch Embedded Metric Format (EMF) emitter; Lambda extracts metrics from stdout."""

import json
import os
import sys
import time
from typing import Literal

NAMESPACE = "ClaimsInvestigator"
Unit = Literal["Count", "Milliseconds", "Seconds"]


def emit(name: str, value: float, unit: Unit = "Count", **dimensions: str) -> None:
    dims = {"Environment": os.environ.get("CLAIMS_ENVIRONMENT", "unknown"), **dimensions}
    record = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE,
                    "Dimensions": [sorted(dims)],
                    "Metrics": [{"Name": name, "Unit": unit}],
                }
            ],
        },
        **dims,
        name: value,
    }
    sys.stdout.write(json.dumps(record) + "\n")
