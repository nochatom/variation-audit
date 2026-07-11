"""Structured request logging middleware.

Logs one JSON line per request: method, path, status, duration, client IP,
a per-request correlation id (also returned as X-Request-ID), and the caller's
user_id when resolvable from the bearer token (best-effort — never blocks or
fails the request). Auth failures and rate-limit trips (401/403/429) log at
WARNING so they're easy to filter/alert on; 5xx logs at ERROR.
"""
from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth.tokens import TokenError, decode_token

log = logging.getLogger("va.request")


def _user_id_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    try:
        payload = decode_token(auth[7:])
    except TokenError:
        return None
    return payload.get("sub")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = uuid.uuid4().hex
        # Set before call_next so app/errors.py's exception handlers can
        # quote the same id as this request's log line — including the
        # bare-Exception handler, which (unlike the HTTPException/
        # RequestValidationError ones) Starlette dispatches from
        # ServerErrorMiddleware, *outside* this middleware. That means an
        # unhandled exception propagates up through this call_next rather
        # than coming back as an ordinary response — hence the try/except
        # below: without it, a genuinely unexpected exception would skip
        # this method's own log line entirely (no record that the request
        # ever happened) and the X-Request-ID header would never be set.
        request.state.request_id = request_id
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            log.log(
                logging.ERROR,
                "%s %s -> 500 (unhandled)",
                request.method,
                request.url.path,
                extra={
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "client_ip": request.client.host if request.client else None,
                    "user_id": _user_id_from_request(request),
                },
            )
            # Re-raise — app/errors.py's unhandled_exception_handler (run by
            # ServerErrorMiddleware) still builds the actual client response
            # and sets X-Request-ID on it directly, since it never passes
            # back through this method to have the header added below.
            raise
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        status = response.status_code
        level = logging.ERROR if status >= 500 else logging.WARNING if status in (401, 403, 429) else logging.INFO
        log.log(
            level,
            "%s %s -> %d",
            request.method,
            request.url.path,
            status,
            extra={
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status,
                "duration_ms": duration_ms,
                "client_ip": request.client.host if request.client else None,
                "user_id": _user_id_from_request(request),
            },
        )
        return response
