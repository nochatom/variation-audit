"""HTTP client for the stateless detection engine (contract v1.1).

The product is the engine's client: it POSTs an analysis job, then polls with
backoff until a terminal state, honouring the 15-minute cap (decision .21.2).
Synchronous on purpose — it runs inside the polling worker (decision: separate
worker process). No webhook, no cancellation in MVP.
"""
from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from app.engine.schemas import AnalysisRequest, JobCreated, JobPoll

# Defaults from contract v1.1 §2.5 / §2.3
MAX_WAIT_SECONDS = 10 * 60      # 10-min job cap -> ENGINE_TIMEOUT (product SLA)
POLL_INITIAL_SECONDS = 2.0
POLL_CAP_SECONDS = 15.0
HTTP_TIMEOUT_SECONDS = 30.0

# Root-cause fix for intermittent "Server disconnected without sending a
# response" failures on long jobs: uvicorn closes idle keep-alive connections
# after ~5s, but our poll backoff idles up to POLL_CAP_SECONDS (15s) between
# polls, so a pooled connection is frequently closed server-side before the
# next poll reuses it. Two targeted mitigations (NOT a timeout increase):
#   1. keepalive_expiry below a typical server keep-alive, so httpx opens a
#      fresh connection for widely-spaced polls instead of racing a dead one;
#   2. a single retry on a transient connection drop (see _TRANSIENT_ERRORS),
#      which re-issues the request on a new connection.
KEEPALIVE_EXPIRY_SECONDS = 2.0

# Connection-level errors that are safe to retry on a fresh connection: the
# request never reached the app (or the socket was already closed), so a poll
# (GET) or submit (idempotent via request_id) can be re-sent without side
# effects. Deliberately excludes ReadTimeout — a genuine slow response must
# still surface, not be silently retried.
_TRANSIENT_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ReadError,
    httpx.WriteError,
)


class EngineError(RuntimeError):
    """Base for engine-call failures."""

    def __init__(self, message: str, *, code: str = "INTERNAL", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class EngineTimeout(EngineError):
    def __init__(self, message: str = "analysis exceeded the 10-minute limit and timed out"):
        super().__init__(message, code="ENGINE_TIMEOUT", retryable=True)


class EngineCancelled(EngineError):
    """The user requested cancellation mid-run — not a failure."""

    def __init__(self, message: str = "analysis cancelled by user"):
        super().__init__(message, code="CANCELLED", retryable=False)


class IdempotencyConflict(EngineError):
    def __init__(self, message: str = "request_id reused with a different body"):
        super().__init__(message, code="IDEMPOTENCY_KEY_REUSE", retryable=False)


class EngineClient:
    def __init__(self, base_url: str, *, api_key: str | None = None,
                 http_timeout: float = HTTP_TIMEOUT_SECONDS,
                 transport: httpx.BaseTransport | None = None):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers,
            timeout=http_timeout, transport=transport,
            # Don't reuse a keep-alive connection older than this — keeps our
            # widely-spaced polls off connections the server may have closed.
            limits=httpx.Limits(keepalive_expiry=KEEPALIVE_EXPIRY_SECONDS),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "EngineClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- low-level calls ----------------------------------------------------
    def _request(self, method: str, url: str, *, retries: int = 1, **kwargs) -> httpx.Response:
        """Send a request, retrying once on a transient connection drop.

        Fixes the idle keep-alive reuse race (see _TRANSIENT_ERRORS): the first
        attempt may fail on a stale pooled connection, the retry re-issues on a
        fresh one. Genuine HTTP errors and read timeouts are NOT retried here —
        they flow back to the caller unchanged.
        """
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return self._client.request(method, url, **kwargs)
            except _TRANSIENT_ERRORS as exc:
                last = exc
        raise EngineError(f"engine connection failed after {retries + 1} attempts: {last}",
                          code="ENGINE_UNAVAILABLE", retryable=True)

    def submit(self, request: AnalysisRequest) -> JobCreated:
        """POST /v1/analyses -> 202 (or 200 if idempotent replay)."""
        resp = self._request("POST", "/v1/analyses", json=request.model_dump(mode="json"))
        if resp.status_code == 409:
            raise IdempotencyConflict()
        if resp.status_code >= 400:
            self._raise_from_body(resp)
        return JobCreated.model_validate(resp.json())

    def poll(self, engine_job_id: str) -> JobPoll:
        """GET /v1/analyses/{job_id}."""
        resp = self._request("GET", f"/v1/analyses/{engine_job_id}")
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
        on_poll: Callable[[], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> JobPoll:
        """Submit a job and poll with exponential backoff until terminal.

        Raises EngineTimeout if the cap elapses before a terminal state.
        Returns the terminal JobPoll (status succeeded or failed).

        `on_poll` is invoked once per non-terminal poll — the worker uses it to
        emit a progress heartbeat while a long engine stage (AI Analysis can
        run for minutes) produces no sub-events, so the live stream keeps
        ticking and never trips a false "stalled" warning.

        `cancel_check` is polled once per iteration; when it returns True the
        run aborts with EngineCancelled so the worker can mark the job
        cancelled and stop waiting on the engine (cooperative cancellation).
        """
        created = self.submit(request)
        deadline = time.monotonic() + max_wait
        delay = initial
        while True:
            if cancel_check is not None and cancel_check():
                raise EngineCancelled()
            poll = self.poll(created.job_id)
            if poll.is_terminal:
                return poll
            if cancel_check is not None and cancel_check():
                raise EngineCancelled()
            if on_poll is not None:
                on_poll()
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
