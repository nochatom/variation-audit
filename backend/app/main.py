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

from app.auth.router import router as auth_router
from app.config import get_settings
from app.routers.audit import router as audit_router
from app.routers.dashboard import router as dashboard_router
from app.routers.notifications import router as notifications_router
from app.routers.orgs import router as orgs_router
from app.routers.projects import router as projects_router
from app.routers.reports import router as reports_router
from app.routers.review import router as review_router

app = FastAPI(
    title="Variation Audit API",
    version="0.1.0",
    description="AU construction variation recovery — product layer.",
)

# Browser frontend and API are separate origins, so CORS is required.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
