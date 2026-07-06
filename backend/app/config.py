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

    password_reset_expire_minutes: int = 60

    # Supabase Auth — used ONLY as an additional Google-login entry point
    # (see app/auth/supabase_jwt.py, app/services/oauth_google.py). The
    # existing email/password + JWT + refresh-token system is untouched and
    # remains the sole session mechanism: a successful Google sign-in via
    # Supabase is exchanged for this app's own token pair, never used
    # directly as a session. Unset -> POST /auth/google reports 503, same
    # "not configured" pattern as VA_STRIPE_SECRET_KEY.
    supabase_url: str | None = None
    supabase_jwt_aud: str = "authenticated"

    # Billing (.23). Unset stripe_secret_key -> NullBillingProvider: the
    # billing UI still renders (subscription defaults to Free/active, usage
    # is always real), but checkout/portal actions report "not configured"
    # instead of fabricating a payment flow (see app/billing/provider.py).
    # Price IDs are per-plan and deliberately have no default — a plan with
    # no configured price cannot be self-serve-purchased until product/
    # pricing sets one, rather than silently using a wrong/placeholder price.
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    # Monthly price IDs (existing fields, kept as-is for backward compat).
    stripe_price_pro: str | None = None
    stripe_price_enterprise: str | None = None
    # Annual price IDs (.25) — additive; monthly checkout keeps working
    # unchanged when these are unset. Enterprise has no self-serve annual
    # price (Contact Sales handles custom/annual terms directly).
    stripe_price_pro_annual: str | None = None
    # Seat-overage price (.25) — a metered/per-unit price billed for seats
    # beyond a paid plan's included count. Unset -> overage seats are simply
    # not billed (enforce_seat_limit falls back to a hard block instead).
    stripe_price_seat_overage: str | None = None
    # Grace period (.24): days a subscription stays `past_due` (access
    # unaffected) after a recurring payment fails before lazily flipping to
    # `suspended`. Cleared immediately on the next successful payment.
    billing_grace_period_days: int = 7

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
    #   billing:  checkout/portal/cancel/resume each mint a real Stripe
    #             session or mutate a subscription — money-adjacent actions
    #             an admin account (or a compromised one) shouldn't be able
    #             to hammer, same category as auth/invitations above.
    rate_limit_default: str = "300/minute"
    rate_limit_auth: str = "5/minute"
    rate_limit_uploads: str = "20/minute"
    rate_limit_analysis: str = "10/hour"
    rate_limit_invitations: str = "20/hour"
    rate_limit_billing: str = "10/minute"
    # Multi-worker/multi-instance deployments must share one budget: set this
    # to redis://... so all processes count against the same store. The
    # in-memory default is only correct for a single process.
    rate_limit_storage_uri: str = "memory://"


@lru_cache
def get_settings() -> Settings:
    return Settings()
