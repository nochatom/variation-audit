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
        start = time.monotonic()
        response = await call_next(request)
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
