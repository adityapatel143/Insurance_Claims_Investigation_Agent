"""System prompts; composed as the shared policy followed by a task-specific section."""

from functools import cache
from importlib import resources
from typing import Literal

PromptName = Literal["anomaly_signals", "risk_assessment", "report"]


@cache
def _read(name: str) -> str:
    return resources.files(__package__).joinpath(f"{name}.md").read_text("utf-8").strip()


def system_prompt(task: PromptName) -> str:
    return f"{_read('policy')}\n\n{_read(task)}"
