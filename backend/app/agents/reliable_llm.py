"""Production-reliability wrapper around ADK's LiteLlm.

Wraps a primary model (e.g. NVIDIA NIM's google/gemma-4-31b-it, which has a
measured 60-90s+ cold-start after idle — see the verification report from
this session) with:
  - an explicit timeout (the raw provider has none by default)
  - exponential-backoff retry, skipped entirely for auth failures
  - fallback to a secondary model, only for timeout/rate-limit/unavailable
    /schema-invalid failures
  - output-schema validation (+ safe repair) so primary and fallback models
    are held to the same contract (app/agents/schema_guard.py)
  - structured, credential- and content-free observability logging, plus a
    consolidated per-call metrics record (provider/model/tokens/latency/
    retries/fallback_used) handed to whatever sink app/agents/worker.py set
    — emitted exactly once per logical call (spanning both primary and
    fallback attempts) on EITHER success or terminal failure, via a
    try/finally around the whole attempt (see CallOutcome below; this was
    a real gap until this pass — success-only emission previously meant
    circuit_breaker.py/provider_health.py never saw a failure outcome)

Implements ADK's BaseLlm interface directly (not a LiteLlm subclass) so it
composes two ordinary LiteLlm instances as its transport rather than
depending on LiteLlm's internals — model_provider.py hands this back from
get_model() exactly where a bare LiteLlm used to go, so agent_definitions.py
needs no changes.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from google.adk.models import BaseLlm
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from pydantic import PrivateAttr

from app.agents.context import current_agent_name, current_job_id, current_llm_call_sink
from app.agents.errors import AIProviderError, classify_exception
from app.agents.schema_guard import extract_text, validate_or_repair

logger = logging.getLogger("app.agents.llm")

DEFAULT_MAX_RETRIES = 2       # attempts against the primary beyond the first
DEFAULT_BASE_BACKOFF_S = 2.0  # doubles each retry: 2s, 4s, ...


@dataclass(frozen=True)
class CallOutcome:
    """Immutable summary of one logical call (spanning primary + fallback
    attempts), consumed by _emit_metrics() to build the dict handed to the
    on_llm_call sink. A stable interface so future metadata (e.g. once the
    Provider Router is wired in: provider/model/routing_reason/
    selection_id) can be added here without repeatedly changing
    _emit_metrics()'s signature."""

    success: bool
    responses: list[LlmResponse] | None
    error: AIProviderError | None
    fallback_used: bool
    attempts: int
    elapsed_ms: float


class ReliableLlm(BaseLlm):
    """A BaseLlm that retries, times out, falls back, validates output
    schema, and logs safely."""

    _primary: LiteLlm = PrivateAttr()
    _fallback: LiteLlm | None = PrivateAttr()
    _primary_provider: str = PrivateAttr()
    _fallback_provider: str | None = PrivateAttr()
    _max_retries: int = PrivateAttr()
    _base_backoff_s: float = PrivateAttr()

    def __init__(
        self,
        primary: LiteLlm,
        primary_provider: str,
        fallback: LiteLlm | None = None,
        fallback_provider: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_backoff_s: float = DEFAULT_BASE_BACKOFF_S,
    ):
        super().__init__(model=primary.model)
        self._primary = primary
        self._fallback = fallback
        self._primary_provider = primary_provider
        self._fallback_provider = fallback_provider
        self._max_retries = max_retries
        self._base_backoff_s = base_backoff_s

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        call_start = time.monotonic()
        total_attempts = 0
        fallback_used = False
        responses: list[LlmResponse] | None = None
        final_error: AIProviderError | None = None

        try:
            try:
                responses, attempts = await self._call_with_retry(
                    self._primary, self._primary_provider, llm_request, stream
                )
                total_attempts += attempts
            except AIProviderError as primary_error:
                total_attempts += (
                    primary_error.attempts if hasattr(primary_error, "attempts") else self._max_retries + 1
                )
                if primary_error.retryable and self._fallback is not None:
                    fallback_used = True
                    self._log("llm.fallback.activated", self._primary_provider, self._primary.model,
                              error_type=primary_error.code)
                    try:
                        responses, attempts = await self._call_with_retry(
                            self._fallback, self._fallback_provider, llm_request, stream
                        )
                        total_attempts += attempts
                    except AIProviderError as fallback_error:
                        final_error = fallback_error
                else:
                    final_error = primary_error
        finally:
            # Exactly one metrics emission per logical call, on every path
            # (success, primary-only failure, or fallback-also-failed) —
            # see CallOutcome's docstring. The exception itself, if any, is
            # re-raised unchanged immediately below; this block never
            # alters what the caller sees.
            elapsed_ms = (time.monotonic() - call_start) * 1000
            self._emit_metrics(CallOutcome(
                success=final_error is None,
                responses=responses,
                error=final_error,
                fallback_used=fallback_used,
                attempts=total_attempts,
                elapsed_ms=elapsed_ms,
            ))

        if final_error is not None:
            raise final_error

        for response in responses:
            yield response

    async def _call_with_retry(
        self, model: LiteLlm, provider: str, llm_request: LlmRequest, stream: bool,
    ) -> tuple[list[LlmResponse], int]:
        attempt = 0
        last_error: AIProviderError | None = None
        response_schema = getattr(getattr(llm_request, "config", None), "response_schema", None)

        while attempt <= self._max_retries:
            t0 = time.monotonic()
            try:
                responses = [r async for r in model.generate_content_async(llm_request, stream)]
                self._validate_schema(responses, response_schema)
                elapsed_ms = (time.monotonic() - t0) * 1000
                self._log("llm.call.success", provider, model.model, elapsed_ms=elapsed_ms, attempt=attempt)
                return responses, attempt + 1
            except AIProviderError as classified:
                last_error = classified
            except Exception as exc:  # noqa: BLE001 - classified immediately below
                classified = classify_exception(exc, provider=provider, model=model.model)
                last_error = classified

            elapsed_ms = (time.monotonic() - t0) * 1000
            self._log("llm.call.error", provider, model.model, elapsed_ms=elapsed_ms,
                      attempt=attempt, error_type=last_error.code)

            if not last_error.retryable:
                last_error.attempts = attempt + 1
                raise last_error

            attempt += 1
            if attempt > self._max_retries:
                break
            backoff = self._base_backoff_s * (2 ** (attempt - 1))
            self._log("llm.call.retry", provider, model.model, attempt=attempt, backoff_s=backoff)
            await asyncio.sleep(backoff)

        last_error.attempts = attempt
        raise last_error

    def _validate_schema(self, responses: list[LlmResponse], response_schema) -> None:
        if not response_schema or not isinstance(response_schema, type):
            return
        try:
            from pydantic import BaseModel
            if not issubclass(response_schema, BaseModel):
                return
        except TypeError:
            return

        for response in responses:
            text = extract_text(response)
            if text:
                validate_or_repair(text, response_schema)  # raises AISchemaValidationError on failure

    def _emit_metrics(self, outcome: CallOutcome) -> None:
        usage = _usage_of(outcome.responses) if outcome.responses else None
        metrics = {
            "job_id": current_job_id.get(),
            "agent": current_agent_name.get(),
            "provider": self._fallback_provider if outcome.fallback_used else self._primary_provider,
            "model": (self._fallback.model if outcome.fallback_used and self._fallback else self._primary.model),
            "success": outcome.success,
            "error_code": outcome.error.code if outcome.error else None,
            "input_tokens": usage.get("prompt_tokens") if usage else None,
            "output_tokens": usage.get("completion_tokens") if usage else None,
            "latency_ms": round(outcome.elapsed_ms),
            "number_of_retries": max(0, outcome.attempts - 1),
            "fallback_used": outcome.fallback_used,
        }
        logger.info("llm.call.completed" if outcome.success else "llm.call.failed", extra=dict(metrics))
        sink = current_llm_call_sink.get()
        if sink is not None:
            sink(metrics)

    def _log(self, event: str, provider: str | None, model: str | None, **fields) -> None:
        # Deliberately excludes prompt/response content and any credential —
        # only provider/model identifiers, timing, and error classification.
        logger.info(event, extra={
            "job_id": current_job_id.get(),
            "agent": current_agent_name.get(),
            "provider": provider,
            "model": model,
            **fields,
        })


def _usage_of(responses: list[LlmResponse]) -> dict | None:
    for r in responses:
        if r.usage_metadata is not None:
            return {
                "prompt_tokens": getattr(r.usage_metadata, "prompt_token_count", None),
                "completion_tokens": getattr(r.usage_metadata, "candidates_token_count", None),
            }
    return None
