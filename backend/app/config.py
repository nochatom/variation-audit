"""Runtime configuration (env-driven).

Centralises the knobs the worker + engine client need. Values come from the
environment / .env. Scope: Australia only -> S3 defaults to ap-southeast-2.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="VA_", extra="ignore")

    # Database (product owns all persistence)
    database_url: str = Field(
        default="postgresql+psycopg://localhost/variation_audit",
        description="SQLAlchemy URL for the product Postgres DB",
    )

    # Engine service (stateless; contract v1.1 client target)
    engine_base_url: str = Field(default="http://localhost:8088")
    engine_api_key: str | None = None

    # Object storage (uploaded docs + >1MB result artifacts), AU region
    s3_bucket: str = Field(default="variation-audit-dev")
    s3_region: str = Field(default="ap-southeast-2")          # Sydney — AU residency
    s3_endpoint_url: str | None = None                        # set for MinIO/local
    local_doc_dir: str | None = None                          # dev/test: read docs from disk instead of S3

    # Behaviour
    idempotency_window_days: int = 7                          # decision .21.4
    worker_idle_sleep: float = 2.0

    # Auth (.2) — REQUIRED, no insecure default. Set VA_JWT_SECRET (32+ random
    # bytes, e.g. `openssl rand -hex 32`) in every environment, including local
    # dev (.env, git-ignored) and tests (see tests/conftest.py).
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15                     # short-lived; refresh_token carries the session
    refresh_token_expire_days: int = 30                       # rotated on every use (.2.1)

    # CORS — origins allowed to call the API (the frontend)
    cors_origins: list[str] = ["http://localhost:3000"]

    # Rate limiting (per client IP; slowapi/limits grammar, e.g. "5/minute").
    # Defaults are production values — tests relax only the app-wide default
    # (tests/conftest.py) so category limits stay genuinely exercised.
    #   default:  the SPA fans out 1+N parallel requests per page view (org
    #             dashboard + one review-queue call per project) and browsers
    #             add CORS preflights; offices also NAT many users behind one
    #             IP — so this is an abuse ceiling, not a capacity budget.
    #   auth:     login/signup/refresh mint tokens; strict per OWASP
    #             brute-force / credential-stuffing guidance.
    #   uploads:  a full project setup is 5 uploads (contract + 4 registers);
    #             allows that plus retries while capping parse/disk abuse.
    #   analysis: each request enqueues a multi-minute LLM job with real API
    #             cost; normal usage is a few runs/day, so cap cost abuse.
    rate_limit_default: str = "300/minute"
    rate_limit_auth: str = "5/minute"
    rate_limit_uploads: str = "20/minute"
    rate_limit_analysis: str = "10/hour"
    # Multi-worker/multi-instance deployments must share one budget: set this
    # to redis://... so all processes count against the same store. The
    # in-memory default is only correct for a single process.
    rate_limit_storage_uri: str = "memory://"


@lru_cache
def get_settings() -> Settings:
    return Settings()
