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

    # Organization invitations (.19a)
    invitation_expire_days: int = 7
    # Frontend origin used to build the accept-invite link embedded in the
    # invitation email (and returned as accept_url for a "copy invite link"
    # fallback — see app/routers/invitations.py).
    frontend_base_url: str = "http://localhost:3000"

    # Outbound email (invitations). Unset smtp_host -> ConsoleMailer: the
    # accept link is written to the structured log instead of sent, so the
    # invitation flow is fully testable without real mail infrastructure
    # (see app/mailer.py, mirrors the S3/local-dir split in app/storage.py).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_from: str = "VariationIQ <noreply@variationiq.example>"

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
    #   invitations: sends real outbound email to an admin-supplied address —
    #             an authenticated admin account is still a viable spam/abuse
    #             vector (compromised credentials, or relaying junk mail to
    #             arbitrary addresses), and SMTP relay reputation is a real
    #             cost. Bulk team onboarding is a rare, bounded event, not
    #             everyday traffic, so this is tighter than uploads.
    rate_limit_default: str = "300/minute"
    rate_limit_auth: str = "5/minute"
    rate_limit_uploads: str = "20/minute"
    rate_limit_analysis: str = "10/hour"
    rate_limit_invitations: str = "20/hour"
    # Multi-worker/multi-instance deployments must share one budget: set this
    # to redis://... so all processes count against the same store. The
    # in-memory default is only correct for a single process.
    rate_limit_storage_uri: str = "memory://"


@lru_cache
def get_settings() -> Settings:
    return Settings()
