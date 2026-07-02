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
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
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
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()

    variations: Mapped[list[Variation]] = relationship(back_populates="job")


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
