"""Strands/Bedrock implementation of `StructuredModel` with Guardrails applied."""

import logging
import time
from threading import Event

from pydantic import BaseModel, ValidationError
from strands import Agent
from strands.models import BedrockModel
from strands.types.exceptions import StructuredOutputException

from claims_investigator.errors import ModelOutputError
from claims_investigator.gateways.aws import client_config
from claims_investigator.logging import get_logger, log_event
from claims_investigator.services.guardrails import ensure_not_blocked

_LOG = get_logger(__name__)


class StrandsStructuredModel:
    def __init__(
        self,
        *,
        model_id: str,
        guardrail_id: str,
        guardrail_version: str,
        region: str,
        timeout_seconds: int,
        max_output_retries: int,
    ) -> None:
        self._model = BedrockModel(
            model_id=model_id,
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_version,
            guardrail_trace="enabled",
            region_name=region,
            boto_client_config=client_config(read_timeout=timeout_seconds),
            temperature=0.0,
            max_tokens=4096,
        )
        self._max_output_retries = max_output_retries

    def generate[T: BaseModel](
        self, system_prompt: str, prompt: str, output_model: type[T], cancel: Event
    ) -> T:
        for attempt in range(self._max_output_retries + 1):
            # A fresh agent per call: no conversation state leaks between steps or jobs.
            agent = Agent(
                model=self._model, system_prompt=system_prompt, tools=[], callback_handler=None
            )
            started = time.perf_counter()
            try:
                result = agent(prompt, structured_output_model=output_model, cancel_signal=cancel)
            except (StructuredOutputException, ValidationError) as exc:
                log_event(
                    _LOG,
                    logging.WARNING,
                    "model_output_invalid",
                    output_model=output_model.__name__,
                    attempt=attempt,
                    exception_type=type(exc).__name__,
                )
                continue
            log_event(
                _LOG,
                logging.INFO,
                "model_call_completed",
                output_model=output_model.__name__,
                stop_reason=str(result.stop_reason),
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            ensure_not_blocked(str(result.stop_reason))
            if isinstance(result.structured_output, output_model):
                return result.structured_output
        raise ModelOutputError(f"{output_model.__name__} output invalid after retries")
