"""Application-layer guardrails: untrusted-data fencing, injection markers, output validation.

Bedrock Guardrails filter model input/output in the service; these controls add defence in depth.
"""

import re
import unicodedata

from pydantic import BaseModel, ValidationError

from claims_investigator.errors import GuardrailInterventionError, ModelOutputError

# Bedrock Converse stop reasons that indicate the response was blocked or filtered.
BLOCKED_STOP_REASONS = frozenset({"guardrail_intervened", "content_filtered"})
_LABEL = re.compile(r"^[a-z0-9:._#/-]{1,200}$", re.IGNORECASE)
_FENCE_TAG = re.compile(r"</?\s*untrusted_data[^>]*>", re.IGNORECASE)
_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")
_INJECTION_MARKERS: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in {
        "override_instructions": (
            r"\b(ignore|disregard|forget)\b.{0,40}\b(instructions|rules|prompt)\b"
        ),
        "role_reassignment": r"\byou\s+are\s+now\b|\bact\s+as\b",
        "system_prompt_probe": r"\bsystem\s+prompt\b",
        "decision_coercion": r"\b(approve|pay|mark)\b.{0,30}\b(claim|payment)\b",
        "tool_coercion": r"\b(call|invoke|use)\s+the\s+\w+\s+tool\b",
    }.items()
}


def sanitize_untrusted(text: str, max_chars: int) -> str:
    cleaned = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    return _FENCE_TAG.sub("[removed-tag]", cleaned)[:max_chars]


def wrap_untrusted(label: str, text: str, max_chars: int = 20_000) -> str:
    """Fence claim/retrieved text so prompts can instruct the model to treat it as data only."""
    if not _LABEL.match(label):
        raise ValueError("invalid untrusted-data label")
    return (
        f'<untrusted_data source="{label}">\n'
        f"{sanitize_untrusted(text, max_chars)}\n"
        "</untrusted_data>"
    )


def find_injection_markers(text: str) -> list[str]:
    return [name for name, pattern in _INJECTION_MARKERS.items() if pattern.search(text)]


def ensure_not_blocked(stop_reason: str) -> None:
    if stop_reason in BLOCKED_STOP_REASONS:
        raise GuardrailInterventionError(f"model response blocked: {stop_reason}")


def parse_model_output[T: BaseModel](raw: str, model: type[T]) -> T:
    try:
        return model.model_validate_json(_CODE_FENCE.sub("", raw.strip()))
    except ValidationError as exc:
        raise ModelOutputError(
            "model output failed validation",
            tuple(f"{'.'.join(map(str, e['loc']))}: {e['type']}" for e in exc.errors()),
        ) from exc
