"""Product API entrypoint (FastAPI).

The product layer: auth, orgs, projects, ingestion intake, review, reporting.
The detection engine is a separate stateless service reached via the v1.2
contract (the worker is its client). This app is the user-facing surface.

Run locally:
    cd backend
    uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.auth.router import router as auth_router
from app.config import get_settings
from app.logging_config import configure_logging
from app.rate_limit import limiter
from app.request_logging import RequestLoggingMiddleware
from app.routers.audit import router as audit_router
from app.routers.dashboard import router as dashboard_router
from app.routers.notifications import router as notifications_router
from app.routers.orgs import router as orgs_router
from app.routers.projects import router as projects_router
from app.routers.reports import router as reports_router
from app.routers.review import router as review_router
from app.security_headers import SecurityHeadersMiddleware

configure_logging()

app = FastAPI(
    title="Variation Audit API",
    version="0.1.0",
    description="AU construction variation recovery — product layer.",
)

# Rate limiting (per client IP) — a default limit applies to every endpoint via
# SlowAPIMiddleware; individual routers (e.g. auth login/signup) tighten this
# further with @limiter.limit(...) for brute-force protection.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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

# Outermost — measures true end-to-end latency and logs every request as
# structured JSON (see app/logging_config.py), with auth failures (401/403)
# and rate-limit trips (429) elevated to WARNING for easy filtering/alerting.
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(review_router)
app.include_router(orgs_router)
app.include_router(reports_router)
app.include_router(dashboard_router)
app.include_router(notifications_router)
app.include_router(audit_router)


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "region": s.s3_region}
