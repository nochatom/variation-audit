"""Variation Audit — SQLAlchemy 2.0 models (product database).

Mirror of backend/db/schema.sql. Engine is stateless; this product DB owns all
persistence. Aligns with docs/architecture.md §5 and the Engine<->Product API
contract v1.1. Scope: Australia only, all construction trades.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------
# Enums (names match the PostgreSQL CREATE TYPE identifiers in schema.sql)
# --------------------------------------------------------------------------
class MembershipRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class ProjectStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"


class SourceType(str, enum.Enum):
    email = "email"
    rfi = "rfi"
    site_instruction = "site_instruction"
    meeting_note = "meeting_note"
    sms = "sms"
    document = "document"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class EngineStage(str, enum.Enum):
    ingest = "ingest"
    baseline = "baseline"
    classify = "classify"
    quantify = "quantify"
    confidence = "confidence"


class VariationEngineStatus(str, enum.Enum):
    detected = "detected"
    confirmed = "confirmed"
    uncertain = "uncertain"


class ConfidenceBand(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"


class BasisQuality(str, enum.Enum):
    boq = "boq"
    rate_card = "rate_card"
    inferred = "inferred"
    none = "none"


class PlanTier(str, enum.Enum):
    free = "free"
    pro = "pro"
    enterprise = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    trialing = "trialing"
    past_due = "past_due"     # payment failed; inside the grace period, access unaffected
    suspended = "suspended"   # grace period expired with no successful payment
    canceled = "canceled"


class InvoiceStatus(str, enum.Enum):
    paid = "paid"
    open = "open"
    void = "void"


class AgentJobStatus(str, enum.Enum):
    """Lifecycle of one app/agents/ scaffold run (app/agents/jobs.py,
    app/agents/worker.py). Separate from JobStatus (the production
    worker->engine AnalysisJob) — this is the additive ADK scaffold's own
    queue, deliberately not sharing a table with the engine pipeline."""

    pending = "pending"
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


# --------------------------------------------------------------------------
# Reusable column helpers
# --------------------------------------------------------------------------
def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())


def _company_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


_created = lambda: mapped_column(server_default=func.now(), nullable=False)  # noqa: E731
_updated = lambda: mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)  # noqa: E731


# --------------------------------------------------------------------------
# Tenancy
# --------------------------------------------------------------------------
class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    memberships: Mapped[list[Membership]] = relationship(back_populates="organization")
    projects: Mapped[list[Project]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(Text)
    # Nullable: an SSO-only account (e.g. a future Supabase-authenticated
    # user) genuinely has no local password — this is not
    # optional-but-usually-set, some real users will have NULL here
    # permanently until/unless they set one.
    password_hash: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    memberships: Mapped[list[Membership]] = relationship(back_populates="user")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_membership_user_company"),)

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = _company_fk()
    role: Mapped[MembershipRole] = mapped_column(nullable=False, default=MembershipRole.member)
    created_at: Mapped[datetime] = _created()

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class Invitation(Base):
    """A pending organization invitation (.19a) — email-addressed, not user-addressed.

    Unlike Membership, an Invitation does not require the invited email to
    already belong to a User: the row is created immediately either way, and
    a User is only required at *acceptance* time (register-and-accept for a
    new email, or accept for an existing account). Only the SHA-256 hash of
    the opaque token secret is ever stored, matching RefreshToken. Status is
    derived from accepted_at/revoked_at/expires_at rather than a separate
    enum column, also matching RefreshToken's convention.
    """

    __tablename__ = "invitations"

    # Partial unique index: at most one *active* (non-accepted, non-revoked)
    # invitation per (company, email) — backstops app-level duplicate
    # rejection (services/invitations.py:create_invitation) against a race
    # between two concurrent invites for the same email. Can't also exclude
    # expired rows here (index predicates must be immutable — now() isn't
    # allowed), so the service layer auto-revokes expired dangling rows
    # before insert to keep this constraint satisfiable.
    __table_args__ = (
        Index(
            "idx_invitations_active_unique", "company_id", "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, index=True)
    role: Mapped[MembershipRole] = mapped_column(nullable=False, default=MembershipRole.member)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column()
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column()

    organization: Mapped[Organization] = relationship()


class RefreshToken(Base):
    """A rotating, revocable refresh token (.2.1). Only the SHA-256 hash of the
    opaque secret half is ever stored — never the raw token. `replaced_by_id`
    chains rotations; a token presented after it's been revoked (i.e. already
    rotated) signals possible theft (see auth/refresh_tokens.py)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped[User] = relationship()


class PasswordResetToken(Base):
    """A short-lived, single-use password reset token. Same opaque-token-hash
    shape as RefreshToken/Invitation — only the SHA-256 hash is ever stored.
    used_at (not a boolean) records when it was consumed, for audit."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column()

    user: Mapped[User] = relationship()


# --------------------------------------------------------------------------
# Billing & subscriptions (.23)
# --------------------------------------------------------------------------
class Subscription(Base):
    """One row per organization — created lazily (Free/active) the first time
    billing is viewed, so no signup-flow change was needed. `stripe_customer_id`
    /`stripe_subscription_id` are populated once a Stripe Checkout session for
    that org completes (see app/billing/provider.py, services/billing.py); both
    stay NULL for an org that has never gone through Checkout (the common case
    today, since no plan currently has a live Stripe Price configured)."""

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    plan: Mapped[PlanTier] = mapped_column(nullable=False, default=PlanTier.free)
    status: Mapped[SubscriptionStatus] = mapped_column(nullable=False, default=SubscriptionStatus.active)
    current_period_end: Mapped[datetime | None] = mapped_column()
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    stripe_customer_id: Mapped[str | None] = mapped_column(Text)
    stripe_subscription_id: Mapped[str | None] = mapped_column(Text)
    # Set when a recurring payment fails (invoice.payment_failed) — status
    # becomes past_due and access is NOT cut immediately; a lazy check
    # (services/billing.py:_apply_grace_period_expiry) flips status to
    # suspended once this passes, and clears both on a subsequent
    # invoice.paid. NULL whenever status isn't past_due.
    grace_period_expires_at: Mapped[datetime | None] = mapped_column()
    # NULL = use PLAN_LIMITS[plan]["seats"] (the common case). Set only for a
    # negotiated deal that overrides the plan default — seat-based billing
    # groundwork (.24), not yet wired to a per-seat Stripe price.
    included_seats: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    organization: Mapped[Organization] = relationship()


class StripeEvent(Base):
    """Records every Stripe webhook event id we've processed (.24) — the
    idempotency guard for services/billing.py:handle_webhook_event. Stripe
    retries webhook deliveries on anything other than a 2xx response, and
    the same event can genuinely be delivered more than once even without a
    failure; `id` (Stripe's own event id, globally unique) as the primary
    key means a concurrent duplicate delivery hits a unique-violation on
    insert rather than double-applying the event."""

    __tablename__ = "stripe_events"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime] = _created()


class PaymentMethod(Base):
    """A card on file, mirrored from Stripe (never holds a raw card number —
    only the last4/brand/expiry Stripe returns, plus its own payment method
    id). Card capture itself always happens inside Stripe Checkout/Billing
    Portal, never on a form we host — raw card data must never reach our
    backend."""

    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    brand: Mapped[str] = mapped_column(Text, nullable=False)
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    exp_month: Mapped[int] = mapped_column(Integer, nullable=False)
    exp_year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    stripe_payment_method_id: Mapped[str | None] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = _created()


class Invoice(Base):
    """Mirrored from Stripe's `invoice.paid`/`invoice.finalized` webhook
    events (see services/billing.py:handle_webhook_event) — this table is
    never written to directly from a user-facing request; it exists so
    invoice history renders instantly without a live Stripe API call, and
    survives if Stripe is briefly unreachable."""

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    plan: Mapped[PlanTier] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="AUD")
    status: Mapped[InvoiceStatus] = mapped_column(nullable=False, default=InvoiceStatus.paid)
    period_start: Mapped[datetime] = mapped_column(nullable=False)
    period_end: Mapped[datetime] = mapped_column(nullable=False)
    stripe_invoice_id: Mapped[str | None] = mapped_column(Text, unique=True)
    hosted_invoice_url: Mapped[str | None] = mapped_column(Text)  # Stripe-hosted PDF link
    created_at: Mapped[datetime] = _created()


# --------------------------------------------------------------------------
# Projects & documents
# --------------------------------------------------------------------------
class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint("country = 'AU'", name="ck_project_country_au"),)

    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    project_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="construction_trade")
    country: Mapped[str] = mapped_column(String(2), nullable=False, server_default="AU")
    status: Mapped[ProjectStatus] = mapped_column(nullable=False, default=ProjectStatus.in_progress)
    # Soft archive: hidden from the default dashboard/list, fully recoverable.
    # NULL = active. Orthogonal to status (also records WHEN it was archived).
    archived_at: Mapped[datetime | None] = mapped_column()
    # Engine baseline inputs (contract v1.2) — required to drive run_recovery.
    contract_text: Mapped[str | None] = mapped_column(Text)
    scope_text: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(String(8))   # AU state/territory (SoP regime hint)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    organization: Mapped[Organization] = relationship(back_populates="projects")
    documents: Mapped[list[Document]] = relationship(back_populates="project")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _pk()  # == contract document_id
    company_id: Mapped[uuid.UUID] = _company_fk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[SourceType] = mapped_column(nullable=False)
    doc_timestamp: Mapped[datetime | None] = mapped_column()
    source: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)  # S3 ap-southeast-2 key
    content_hash: Mapped[str | None] = mapped_column(Text)
    # Nullable: rows created before this column existed have no recorded
    # size. Used only for plan storage-limit enforcement (services/billing.py)
    # — treated as 0 when NULL, which undercounts pre-existing docs rather
    # than overcounting, the safer direction for a limit check.
    size_bytes: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = _created()

    project: Mapped[Project] = relationship(back_populates="documents")


# --------------------------------------------------------------------------
# Analysis jobs (mirror engine job; request_id = idempotency key)
# --------------------------------------------------------------------------
class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        CheckConstraint("progress_percent BETWEEN 0 AND 1", name="ck_job_progress_range"),
        Index("idx_jobs_queue", "status", "created_at"),  # FOR UPDATE SKIP LOCKED claim
    )

    id: Mapped[uuid.UUID] = _pk()  # product job_id
    company_id: Mapped[uuid.UUID] = _company_fk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    contract_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="v1.2")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # Engine result rollups (contract v1.2)
    baseline: Mapped[dict | None] = mapped_column(JSONB)            # notice_clause/time_bar_days/sop_regime/counts
    recoverable_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    time_bar_at_risk: Mapped[int | None] = mapped_column(Integer)
    engine_job_id: Mapped[str | None] = mapped_column(Text)
    engine_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[JobStatus] = mapped_column(nullable=False, default=JobStatus.queued)
    progress_stage: Mapped[EngineStage | None] = mapped_column()
    progress_percent: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    result_ref: Mapped[str | None] = mapped_column(Text)  # result_url when >1MB
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_retryable: Mapped[bool | None] = mapped_column(Boolean)
    # Cooperative cancellation signal: set by the cancel endpoint; the worker
    # observes it between engine polls and transitions the job to "cancelled".
    cancel_requested_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()

    variations: Mapped[list[Variation]] = relationship(back_populates="job")


class AgentAnalysisJob(Base):
    """Queue + lifecycle tracking for one app/agents/ (ADK scaffold) run.

    Deliberately a separate table from AnalysisJob: that one is the
    production worker's contract with the external engine service
    (request_id, engine_job_id, baseline rollups, etc.); this one tracks the
    additive multi-agent scaffold's own execution — same DB-backed
    SKIP-LOCKED queue pattern as job_worker.py (see app/agents/worker.py),
    just a different table so neither pipeline's concerns leak into the
    other's schema.
    """

    __tablename__ = "agent_analysis_jobs"
    __table_args__ = (
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="ck_agent_job_progress_range"),
        Index("idx_agent_jobs_queue", "status", "created_at"),  # FOR UPDATE SKIP LOCKED claim
    )

    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[AgentJobStatus] = mapped_column(nullable=False, default=AgentJobStatus.pending, index=True)
    current_agent: Mapped[str | None] = mapped_column(Text)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Elapsed-time / progress-so-far linear extrapolation, recomputed on
    # every agent-completion callback (app/agents/worker.py) — a rough ETA,
    # not a scheduling guarantee.
    estimated_remaining_seconds: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[dict | None] = mapped_column(JSONB)          # FinalResult.model_dump() on success
    error_code: Mapped[str | None] = mapped_column(Text)        # AI_AUTH_ERROR / AI_RATE_LIMIT_ERROR / ...
    error_message: Mapped[str | None] = mapped_column(Text)
    # Per-LLM-call observability (app/agents/reliable_llm.py's consolidated
    # metrics, one dict per logical call: agent/provider/model/tokens/
    # latency_ms/number_of_retries/fallback_used). Never prompt/response
    # content, never credentials.
    llm_calls: Mapped[list | None] = mapped_column(JSONB)
    # Worker heartbeat (production hardening): worker_id identifies which
    # process claimed the job; heartbeat_at is refreshed every 30-60s while
    # that process is actively working it (see app/agents/worker.py's
    # _heartbeat_loop) — reclaim_stale_jobs() keys off heartbeat_at, not a
    # fixed wall-clock timeout, so a job is only recovered once its actual
    # worker has genuinely gone silent. last_progress_at is distinct: it
    # only moves when an agent actually finishes, for observability on
    # "is this job moving" vs. "is the worker process alive."
    worker_id: Mapped[str | None] = mapped_column(Text, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column()
    last_progress_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()

    project: Mapped[Project] = relationship()


# --------------------------------------------------------------------------
# Variations, evidence, value estimates
# --------------------------------------------------------------------------
class Variation(Base):
    __tablename__ = "variations"
    __table_args__ = (
        CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_variation_confidence_range"),
    )

    id: Mapped[uuid.UUID] = _pk()  # == contract variation_id
    company_id: Mapped[uuid.UUID] = _company_fk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    engine_status: Mapped[VariationEngineStatus] = mapped_column(
        nullable=False, default=VariationEngineStatus.detected
    )
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    confidence_band: Mapped[ConfidenceBand] = mapped_column(nullable=False)
    confidence_factors: Mapped[dict | None] = mapped_column(JSONB)   # engine deterministic breakdown
    time_bar_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")  # AU SoP
    review_status: Mapped[ReviewStatus] = mapped_column(
        nullable=False, default=ReviewStatus.pending, index=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = _created()

    job: Mapped[AnalysisJob] = relationship(back_populates="variations")
    evidence: Mapped[list[Evidence]] = relationship(back_populates="variation")
    value_estimate: Mapped[ValueEstimate | None] = relationship(back_populates="variation", uselist=False)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = _pk()
    variation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[SourceType] = mapped_column(nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    reference: Mapped[str | None] = mapped_column(Text)
    quote: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()

    variation: Mapped[Variation] = relationship(back_populates="evidence")


class ValueEstimate(Base):
    __tablename__ = "value_estimates"
    __table_args__ = (
        CheckConstraint("currency = 'AUD'", name="ck_value_currency_aud"),
        CheckConstraint(
            "valuation_confidence_score BETWEEN 0 AND 1", name="ck_value_confidence_range"
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    variation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    estimate_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    estimate_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="AUD")
    basis_quality: Mapped[BasisQuality] = mapped_column(nullable=False, default=BasisQuality.none)
    valuation_confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    confidence: Mapped[ConfidenceBand] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = _created()

    variation: Mapped[Variation] = relationship(back_populates="value_estimate")


# --------------------------------------------------------------------------
# Audit log (immutable) & notifications
# --------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("idx_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("idx_notifications_user", "user_id", "read_at"),)

    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    read_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = _created()


class ReviewComment(Base):
    """Commercial-team comment on a variation during review (.14)."""

    __tablename__ = "review_comments"
    __table_args__ = (Index("idx_review_comments_variation", "variation_id", "created_at"),)

    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = _company_fk()
    variation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variations.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()


# --------------------------------------------------------------------------
# Analysis job progress events (real, worker-emitted; streamed over SSE by
# app/routers/analysis_events.py). Append-only: one row per major processing
# step the worker actually performs — never synthesised/faked. Auxiliary to
# the job itself, so a failed event write never affects job execution
# (app/worker/progress.py swallows emit errors).
# --------------------------------------------------------------------------
class AnalysisJobEvent(Base):
    __tablename__ = "analysis_job_events"
    __table_args__ = (
        # SSE tails "events for this job after seq N" — this index serves it.
        Index("idx_job_events_job_seq", "job_id", "seq"),
    )

    id: Mapped[uuid.UUID] = _pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # monotonic per job, for ordering/resume
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # pending | running | completed | failed
    percentage: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    current_document: Mapped[str | None] = mapped_column(Text)
    processed_documents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_documents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    variations_found: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    evidence_links: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    elapsed_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    estimated_remaining: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = _created()
