"""Pydantic schemas for the Engine <-> Product API contract v1.1.

These mirror docs/engine-product-api-contract-v1.1.md exactly. Enums are reused
from app.models so the product DB and the wire format share one vocabulary.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import (
    ConfidenceBand,
    EngineStage,
    JobStatus,
    SourceType,
    VariationEngineStatus,
)

CONTRACT_VERSION = "v1.1"


# --------------------------------------------------------------------------
# Input (Product -> Engine)
# --------------------------------------------------------------------------
class DocumentIn(BaseModel):
    type: SourceType
    content: str
    document_id: str | None = None          # engine assigns if absent
    timestamp: datetime | None = None
    source: str | None = None


class AnalysisRequest(BaseModel):
    request_id: uuid.UUID                    # idempotency key (contract §3.1)
    project_id: str
    company_id: str
    documents: list[DocumentIn]
    contract_version: str = CONTRACT_VERSION
    project_type: str = "construction_trade"
    country: str = "AU"
    callback_url: str | None = None          # MVP: always None (polling-only)


# --------------------------------------------------------------------------
# Output (Engine -> Product)
# --------------------------------------------------------------------------
class JobCreated(BaseModel):
    """202 response from POST /v1/analyses."""

    job_id: str
    status: JobStatus
    request_id: uuid.UUID
    created_at: datetime
    links: dict[str, str] = Field(default_factory=dict)


class Progress(BaseModel):
    stage: EngineStage | None = None
    percent: float | None = None


class EvidenceOut(BaseModel):
    type: SourceType
    source_document_id: str | None = None
    reference: str | None = None
    quote: str | None = None


class EstimatedValueOut(BaseModel):
    amount: Decimal | None = None
    currency: str = "AUD"
    valuation_confidence_score: float | None = None
    confidence: ConfidenceBand | None = None


class VariationOut(BaseModel):
    variation_id: str
    title: str
    description: str | None = None
    status: VariationEngineStatus = VariationEngineStatus.detected
    confidence_score: float
    confidence_band: ConfidenceBand | None = None   # engine-derived; product backfills if missing
    evidence: list[EvidenceOut] = Field(default_factory=list)
    estimated_value: EstimatedValueOut | None = None


class AnalysisResult(BaseModel):
    project_id: str
    engine_version: str
    variations: list[VariationOut] = Field(default_factory=list)


class ErrorOut(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict | None = None


class JobPoll(BaseModel):
    """200 response from GET /v1/analyses/{job_id}."""

    job_id: str
    status: JobStatus
    request_id: uuid.UUID | None = None
    project_id: str | None = None
    progress: Progress | None = None
    result: AnalysisResult | None = None
    result_url: str | None = None            # set instead of result when >1MB
    error: ErrorOut | None = None
    engine_version: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.succeeded, JobStatus.failed)
