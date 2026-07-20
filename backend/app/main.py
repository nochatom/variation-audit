"""Product API entrypoint (FastAPI).

The product layer: auth, orgs, projects, ingestion intake, review, reporting.
The detection engine is a separate stateless service reached via the v1.2
contract (the worker is its client). This app is the user-facing surface.

Run locally:
    cd backend
    uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.auth.router import router as auth_router
from app.body_size_limit import MaxBodySizeMiddleware
from app.config import get_settings
from app.errors import install_error_handlers
from app.logging_config import configure_logging
from app.rate_limit import limiter
from app.request_logging import RequestLoggingMiddleware
from app.routers.agent_jobs import router as agent_jobs_router
from app.routers.analysis_events import router as analysis_events_router
from app.routers.audit import router as audit_router
from app.routers.billing import router as billing_router
from app.routers.billing import webhook_router as billing_webhook_router
from app.routers.dashboard import router as dashboard_router
from app.routers.internal_providers import router as internal_providers_router
from app.routers.internal_storage import router as internal_storage_router
from app.routers.invitations import org_router as org_invitations_router
from app.routers.invitations import public_router as invitations_router
from app.routers.notifications import router as notifications_router
from app.routers.orgs import router as orgs_router
from app.routers.projects import router as projects_router
from app.routers.reports import router as reports_router
from app.routers.review import router as review_router
from app.security_headers import SecurityHeadersMiddleware
from app.storage import validate_production_storage_config

configure_logging()

# Fails fast at process startup (module import) if production has no usable
# object-storage backend — see app.storage.validate_production_storage_config.
# A no-op outside production, so dev/test import behavior is unchanged.
validate_production_storage_config(get_settings())


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    from app.posthog_client import posthog_client
    posthog_client.flush()


app = FastAPI(
    title="Variation Audit API",
    version="0.1.0",
    description="AU construction variation recovery — product layer.",
    lifespan=lifespan,
)

# Rate limiting (per client IP) — a default limit applies to every endpoint via
# SlowAPIMiddleware; individual routers (e.g. auth login/signup) tighten this
# further with @limiter.limit(...) for brute-force protection.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Standard {"error": {"code","message","request_id"}} envelope for every
# error response — explicit HTTPExceptions, validation failures, and
# genuinely unexpected exceptions alike. See app/errors.py's docstring for
# why this also fixes 500s never reaching RequestLoggingMiddleware's log line.
install_error_handlers(app)

# Browser frontend and API are separate origins, so CORS is required.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Applies security headers to every response, including error responses from
# the middleware above.
app.add_middleware(SecurityHeadersMiddleware)

# Backstop body-size cap for every request, not just the multipart uploads in
# app/routers/projects.py (which already stream-cap themselves at 20MB/10MB
# — see app/body_size_limit.py's docstring). 25MB sits above both of those so
# it never interferes with a legitimate upload; it exists purely to bound
# plain-JSON/other endpoints that have no per-field size guard of their own.
app.add_middleware(MaxBodySizeMiddleware, max_bytes=25 * 1024 * 1024)

# Outermost — measures true end-to-end latency and logs every request as
# structured JSON (see app/logging_config.py), with auth failures (401/403)
# and rate-limit trips (429) elevated to WARNING for easy filtering/alerting.
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth_router)
app.include_router(agent_jobs_router)
app.include_router(analysis_events_router)
app.include_router(projects_router)
app.include_router(review_router)
app.include_router(orgs_router)
app.include_router(org_invitations_router)
app.include_router(invitations_router)
app.include_router(reports_router)
app.include_router(dashboard_router)
app.include_router(notifications_router)
app.include_router(audit_router)
app.include_router(billing_router)
app.include_router(billing_webhook_router)
app.include_router(internal_providers_router)
app.include_router(internal_storage_router)


# Exempt from rate limiting: load balancers and uptime monitors probe this
# frequently and must never consume budget or receive a 429.
@app.get("/health")
@limiter.exempt
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "region": s.s3_region}
