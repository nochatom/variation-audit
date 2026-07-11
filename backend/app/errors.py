"""Standardized API error envelope + global exception handlers.

Every error response — whatever raised it, an explicit `HTTPException`, a
Pydantic validation failure, or a genuinely unexpected exception — comes back
in the same shape:

    {"error": {"code": "...", "message": "...", "request_id": "..."}}

Rationale for *where* this lives, and a real Starlette wrinkle worth being
explicit about: handlers for `HTTPException`/`RequestValidationError` are
dispatched by Starlette's `ExceptionMiddleware`, which sits *inside* every
middleware added with `app.add_middleware` (SlowAPI, CORS, SecurityHeaders,
RequestLoggingMiddleware — see app/main.py) — so for those two, converting
an exception to a Response here means it flows back out through those
middlewares as an ordinary response. The bare `Exception` handler is
different: Starlette special-cases it and dispatches it from
`ServerErrorMiddleware`, the *outermost* layer — a genuinely unhandled
exception propagates straight up through every user middleware (including
RequestLoggingMiddleware) uncaught before this handler ever runs. That's why
`RequestLoggingMiddleware.dispatch` wraps `call_next` in its own try/except
(see app/request_logging.py) — without it, an unhandled exception would
produce no request log line at all — and why `unhandled_exception_handler`
below sets `X-Request-ID` on its own response directly, rather than relying
on RequestLoggingMiddleware to add it (that response never passes back
through that middleware to have the header attached).

Never includes a stack trace, a secret, or a provider credential in the
response body — those stay in the log line only (`logger.exception`, which
captures the traceback server-side).
"""
from __future__ import annotations

import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("va.errors")

# Fallback machine-readable code per HTTP status, used whenever a raised
# HTTPException's `detail` is a plain string rather than a structured
# {"error_code", "message"} dict (the pre-existing pattern used for plan-limit
# errors — see app/routers/projects.py etc.). Keeps every response in the
# same envelope without requiring every one of the ~60 existing
# `HTTPException(...)` call sites to be rewritten.
_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    410: "GONE",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    402: "PAYMENT_REQUIRED",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "unknown"


def _envelope(code: str, message: str, request_id: str) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Covers every explicit `HTTPException(...)` raise site, plus
    framework-raised ones (404 route not found, 405 method not allowed)."""
    request_id = _request_id(request)
    detail = exc.detail
    if isinstance(detail, dict) and "message" in detail:
        # The existing {"error_code", "message"} pattern (plan-limit errors,
        # and the DOCUMENT_UPLOAD_FAILED case below) — reuse it as-is.
        code = detail.get("error_code") or _STATUS_CODES.get(exc.status_code, "ERROR")
        message = str(detail["message"])
    else:
        code = _STATUS_CODES.get(exc.status_code, "ERROR")
        message = str(detail) if detail else "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code, message, request_id),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Pydantic/FastAPI request validation failures (422) — field-level
    errors are about the caller's own input, not internal state, so they're
    safe to return; still wrapped in the standard envelope."""
    request_id = _request_id(request)
    content = _envelope("VALIDATION_ERROR", "Request data failed validation.", request_id)
    content["error"]["fields"] = [
        {"loc": [str(p) for p in e["loc"]], "message": e["msg"]} for e in exc.errors()
    ]
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content=content)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort catch-all — a genuinely unexpected exception. Logged in
    full (traceback via logger.exception) server-side only; the client gets
    a generic message and a request_id to quote when reporting the issue,
    never the exception's own message (which could be a raw DB/library
    error containing internal details)."""
    request_id = _request_id(request)
    log.exception(
        "unhandled exception",
        extra={
            "event": "unhandled_exception",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(
            "INTERNAL_SERVER_ERROR",
            "Something went wrong on our end. Please try again.",
            request_id,
        ),
        # RequestLoggingMiddleware can't add this itself for a truly
        # unhandled exception — see module docstring — so it's set here.
        headers={"X-Request-ID": request_id},
    )


def install_error_handlers(app) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
