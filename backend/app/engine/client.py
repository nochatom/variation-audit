"""HTTP client for the stateless detection engine (contract v1.1).

The product is the engine's client: it POSTs an analysis job, then polls with
backoff until a terminal state, honouring the 15-minute cap (decision .21.2).
Synchronous on purpose — it runs inside the polling worker (decision: separate
worker process). No webhook, no cancellation in MVP.
"""
from __future__ import annotations

import time

import httpx

from app.engine.schemas import AnalysisRequest, JobCreated, JobPoll

# Defaults from contract v1.1 §2.5 / §2.3
MAX_WAIT_SECONDS = 15 * 60      # 15-min job cap -> ENGINE_TIMEOUT
POLL_INITIAL_SECONDS = 2.0
POLL_CAP_SECONDS = 15.0
HTTP_TIMEOUT_SECONDS = 30.0


class EngineError(RuntimeError):
    """Base for engine-call failures."""

    def __init__(self, message: str, *, code: str = "INTERNAL", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class EngineTimeout(EngineError):
    def __init__(self, message: str = "engine job exceeded the 15-minute cap"):
        super().__init__(message, code="ENGINE_TIMEOUT", retryable=True)


class IdempotencyConflict(EngineError):
    def __init__(self, message: str = "request_id reused with a different body"):
        super().__init__(message, code="IDEMPOTENCY_KEY_REUSE", retryable=False)


class EngineClient:
    def __init__(self, base_url: str, *, api_key: str | None = None,
                 http_timeout: float = HTTP_TIMEOUT_SECONDS):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(base_url=base_url.rstrip("/"), headers=headers,
                                    timeout=http_timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "EngineClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- low-level calls ----------------------------------------------------
    def submit(self, request: AnalysisRequest) -> JobCreated:
        """POST /v1/analyses -> 202 (or 200 if idempotent replay)."""
        resp = self._client.post("/v1/analyses", json=request.model_dump(mode="json"))
        if resp.status_code == 409:
            raise IdempotencyConflict()
        if resp.status_code >= 400:
            self._raise_from_body(resp)
        return JobCreated.model_validate(resp.json())

    def poll(self, engine_job_id: str) -> JobPoll:
        """GET /v1/analyses/{job_id}."""
        resp = self._client.get(f"/v1/analyses/{engine_job_id}")
        if resp.status_code >= 400:
            self._raise_from_body(resp)
        return JobPoll.model_validate(resp.json())

    # -- high-level orchestration ------------------------------------------
    def run_to_completion(
        self,
        request: AnalysisRequest,
        *,
        max_wait: float = MAX_WAIT_SECONDS,
        initial: float = POLL_INITIAL_SECONDS,
        cap: float = POLL_CAP_SECONDS,
        sleep=time.sleep,
    ) -> JobPoll:
        """Submit a job and poll with exponential backoff until terminal.

        Raises EngineTimeout if the cap elapses before a terminal state.
        Returns the terminal JobPoll (status succeeded or failed).
        """
        created = self.submit(request)
        deadline = time.monotonic() + max_wait
        delay = initial
        while True:
            poll = self.poll(created.job_id)
            if poll.is_terminal:
                return poll
            if time.monotonic() >= deadline:
                raise EngineTimeout()
            remaining = deadline - time.monotonic()
            sleep(min(delay, max(0.0, remaining)))
            delay = min(delay * 2, cap)

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _raise_from_body(resp: httpx.Response) -> None:
        code, message, retryable = "INTERNAL", resp.text, False
        try:
            err = resp.json().get("error") or {}
            code = err.get("code", code)
            message = err.get("message", message)
            retryable = bool(err.get("retryable", False))
        except Exception:  # noqa: BLE001 - non-JSON error body
            pass
        raise EngineError(f"engine returned {resp.status_code}: {message}",
                          code=code, retryable=retryable)
