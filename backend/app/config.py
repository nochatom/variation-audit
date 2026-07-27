"""Runtime configuration (env-driven).

Centralises the knobs the worker + engine client need. Values come from the
environment / .env. Scope: Australia only -> S3 defaults to ap-southeast-2.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Provider Router (docs/decisions/26-provider-router.md §10). Must fail
# loudly on an invalid value at Settings() construction time rather than
# silently falling back to a default — see the field_validator below.
VALID_AGENT_ROUTING_POLICIES = frozenset({
    "highest_priority", "lowest_latency", "lowest_cost", "highest_quality", "longest_context",
})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="VA_", extra="ignore")

    # Deployment environment. "production" enables stricter startup checks
    # (see app.storage.validate_production_storage_config) that don't apply
    # to development/test — e.g. failing fast if no object-storage backend
    # is configured, instead of only discovering that at first upload.
    environment: str = "development"

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
    smtp_from: str = "VariationIQ <hello@variationiq.com>"

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

    # Supabase Storage — an additional object-storage backend for
    # app/storage.py's DocumentLoader, alongside the existing S3/local-dir
    # options (build_loader() prefers this when configured; see storage.py).
    # service_role key is required (not the anon key): the bucket is
    # private, and the backend is a trusted server context, same trust
    # level as this app's own DB connection string — never exposed to the
    # browser. Unset -> build_loader() falls back to S3/local exactly as
    # before, so this is purely additive.
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "project-documents"

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

    # Multi-agent scaffold (app/agents/) — additive, not wired into the
    # production worker->engine pipeline. agent_model_provider selects which
    # model app/agents/model_provider.py resolves for every LlmAgent:
    #   "openai" / "glm" / "gemini" -> routed through NVIDIA NIM's
    #     OpenAI-compatible endpoint (build.nvidia.com), each with its own
    #     key and model slug (nvidia_nim_*_api_key below). "gemini" here is
    #     an NVIDIA-hosted stand-in model, not the real Google Gemini API.
    #   "claude" -> ADK's native LiteLlm/Anthropic path (VA_ANTHROPIC_AGENT_API_KEY).
    # Unset keys -> agent construction still works, but a live run fails
    # clearly at the model call, same "not configured" pattern as Stripe above.
    agent_model_provider: str = "openai"
    anthropic_agent_api_key: str | None = None
    nvidia_nim_openai_api_key: str | None = None
    nvidia_nim_glm_api_key: str | None = None
    nvidia_nim_gemini_api_key: str | None = None

    # Provider Router (docs/decisions/26-provider-router.md). Picks which
    # routing_policies.py function ProviderRouter.select() uses to rank
    # capability-filtered, circuit-closed candidates. "highest_priority" is
    # the default and, with the Phase 1 registry seed (only one model
    # enabled), reproduces today's exact static agent_model_provider
    # behavior — see the Phase 4 backward-compatibility test.
    #
    # Deliberately fails loudly (raises at Settings() construction, i.e. at
    # process startup) on an unsupported value instead of silently falling
    # back to a default — an invalid VA_AGENT_ROUTING_POLICY is a
    # configuration bug, and masking it would mean silently routing every
    # agent through unintended logic instead of failing where the mistake
    # actually is.
    agent_routing_policy: str = "highest_priority"

    @field_validator("agent_routing_policy")
    @classmethod
    def _validate_agent_routing_policy(cls, v: str) -> str:
        if v not in VALID_AGENT_ROUTING_POLICIES:
            raise ValueError(
                f"VA_AGENT_ROUTING_POLICY={v!r} is not a supported routing "
                f"policy — expected one of {sorted(VALID_AGENT_ROUTING_POLICIES)}. "
                "Fix the environment variable; this fails loudly rather than "
                "silently falling back to a default."
            )
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "VA_JWT_SECRET is too weak — it must be at least 32 characters "
                "to secure HS256 JWT signatures against offline brute-force/dictionary attacks. "
                "Please generate a strong secret (e.g. `openssl rand -hex 32`) and set "
                "it in your environment."
            )
        return v

    # Circuit breaker defaults (docs/decisions/26-provider-router.md §9).
    # Independent per-provider state; these thresholds are conservative on
    # purpose — tune only once real provider_call_log data suggests they
    # should move, not speculatively.
    agent_circuit_failure_threshold: int = 5
    agent_circuit_cooldown_seconds: int = 60

    # PostHog analytics
    posthog_project_token: str = ""
    posthog_host: str = "https://eu.i.posthog.com"
    posthog_disabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
