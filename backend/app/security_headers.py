"""Security response headers — applied to every response.

This API only ever returns JSON (or a PDF attachment); it never renders HTML,
so the CSP can be maximally restrictive. Defense in depth: even if a client
were tricked into rendering an API response directly, these headers limit
what that context could do.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    # Ignored by clients over plain HTTP (harmless in local dev); takes effect once served over HTTPS.
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    # Every response here is either private (auth-scoped JSON/PDF) or an
    # error — nothing this API returns should ever sit in a shared/CDN cache
    # or a browser's disk cache. Applies uniformly rather than per-route
    # since there is no genuinely cacheable authenticated response today.
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers[key] = value
        return response
