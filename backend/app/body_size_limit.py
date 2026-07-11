"""Global request body size cap.

app/routers/projects.py's `_read_capped` already streams-and-caps every
multipart file upload (never trusts Content-Length, counts real bytes as it
reads). This middleware closes the remaining gap: every OTHER endpoint —
plain JSON bodies — has no size backstop beyond Pydantic field-level
`max_length` validators, which only run after Starlette has already buffered
the *entire* body into memory. A client that omits or lies about
Content-Length and streams an arbitrarily large body could force that
buffering before any validation ever gets a chance to reject it.

Two layers, neither trusting the client alone:
  1. A fast Content-Length pre-check — rejects an honestly-labeled oversized
     request before any of it is read.
  2. A running byte counter on the actual ASGI receive channel — catches a
     request with no/spoofed Content-Length by aborting as soon as the real
     bytes read exceed the cap, regardless of what the header claimed.

Implemented as a plain ASGI middleware (not `BaseHTTPMiddleware`) — a
`BaseHTTPMiddleware`-based first attempt at this was tried and discarded:
its internal disconnect-watching task group reads the body via a second
concurrent path, and an exception raised while wrapping `receive` surfaces
as an unhandled `ExceptionGroup` deep inside the route handler's own
`request.body()` call instead of propagating back through this middleware's
own `try/except`. A raw ASGI middleware controls `receive`/`send` directly
with no such indirection, so the cap is enforced reliably. Confirmed by
testing both the honest-Content-Length and the no-Content-Length/streamed
cases directly before wiring this into app/main.py.

Set generously above the largest legitimate single request (20MB contract
PDFs, 10MB CSVs — app/routers/projects.py) so this is a backstop for
plain-JSON/other endpoints, not a second cap on uploads that already have
their own tighter, purpose-specific limit.
"""
from __future__ import annotations

from starlette.responses import JSONResponse


class _BodyTooLarge(Exception):
    pass


class MaxBodySizeMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(scope, send)
                    return
            except ValueError:
                pass  # malformed header — fall through to the streaming cap below

        received = 0
        response_started = False

        async def capped_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # Raise rather than silently truncate — a route handler
                    # awaiting request.body()/request.json() must see this as
                    # a real failure, not quietly get back a short body and
                    # respond 200 as if nothing happened.
                    raise _BodyTooLarge()
            return message

        async def send_and_track(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, capped_receive, send_and_track)
        except _BodyTooLarge:
            if not response_started:
                await self._reject(scope, send)

    async def _reject(self, scope, send) -> None:
        request_id = "unknown"
        for key, value in scope.get("headers") or []:
            if key == b"x-request-id":
                request_id = value.decode("latin-1")
                break
        response = JSONResponse(
            status_code=413,
            content={"error": {
                "code": "PAYLOAD_TOO_LARGE",
                "message": f"Request body exceeds the {self.max_bytes // (1024 * 1024)}MB limit.",
                "request_id": request_id,
            }},
        )
        await response(scope, self._noop_receive, send)

    @staticmethod
    async def _noop_receive():
        return {"type": "http.disconnect"}
