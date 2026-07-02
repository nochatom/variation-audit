"""Shared rate limiter instance + per-category limits.

Lives in its own module (not app.main) so routers can import it for
per-route limits without a circular import with app.main, which wires the
limiter into the FastAPI app + middleware.

All limits are env-configurable (see Settings.rate_limit_* in app/config.py
for values and the reasoning behind each). Decorated routes use their
category limit INSTEAD of the app-wide default; undecorated routes get the
default via SlowAPIMiddleware.

Deployment notes (production):
- Keying is per client IP via ``get_remote_address`` (request.client.host).
  Behind a reverse proxy/load balancer, run uvicorn with ``--proxy-headers
  --forwarded-allow-ips=<proxy IPs>`` so request.client reflects the real
  client, not the proxy — otherwise every user shares one bucket. Never
  trust X-Forwarded-For from arbitrary sources.
- With more than one worker/instance, set VA_RATE_LIMIT_STORAGE_URI to a
  shared Redis so all processes count against one budget; the in-memory
  default is per-process.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

_s = get_settings()

# Category limits for routers to apply with @limiter.limit(...). Endpoints
# using these must accept a `request: Request` parameter (slowapi requirement).
AUTH_LIMIT = _s.rate_limit_auth            # login / signup / refresh (token-minting)
UPLOAD_LIMIT = _s.rate_limit_uploads       # contract + the 4 document-register uploads
ANALYSIS_LIMIT = _s.rate_limit_analysis    # enqueues a costly multi-minute LLM job

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_s.rate_limit_default],
    storage_uri=_s.rate_limit_storage_uri,
    # Emit X-RateLimit-Limit/-Remaining/-Reset and Retry-After so well-behaved
    # clients can back off instead of hammering into 429s.
    headers_enabled=True,
)
