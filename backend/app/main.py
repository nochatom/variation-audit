"""Product API entrypoint (FastAPI).

The product layer: auth, orgs, projects, ingestion intake, review, reporting.
The detection engine is a separate stateless service reached via the v1.2
contract (the worker is its client). This app is the user-facing surface.

Run locally:
    cd backend
    uvicorn app.main:app --reload
"""
from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.config import get_settings
from app.routers.projects import router as projects_router

app = FastAPI(
    title="Variation Audit API",
    version="0.1.0",
    description="AU construction variation recovery — product layer.",
)

app.include_router(auth_router)
app.include_router(projects_router)


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "region": s.s3_region}
