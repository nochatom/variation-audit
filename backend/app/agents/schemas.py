"""Structured output schemas for the agent scaffold.

Shaped after app/engine/schemas.py's VariationOut/EvidenceOut/
EstimatedValueOut so a future step that persists this into
Variation/Evidence/ValueEstimate rows has a straightforward mapping. Kept
separate from app/engine/schemas.py because these are ADK `output_schema`
contracts for LLM-agent structured output, not the Engine<->Product wire
contract.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    document_id: str
    source_type: str
    summary: str


class DocumentAgentOutput(BaseModel):
    documents: list[DocumentSummary] = Field(default_factory=list)


class ContractBaseline(BaseModel):
    inclusions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    notice_clause: str | None = None
    time_bar_days: int | None = None


class ContractAgentOutput(BaseModel):
    baseline: ContractBaseline


class EvidenceCitation(BaseModel):
    source_document_id: str | None = None
    reference: str | None = None
    quote: str | None = None


class DetectedVariation(BaseModel):
    title: str
    description: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    time_bar_risk: bool = False


class VariationDetectionOutput(BaseModel):
    variations: list[DetectedVariation] = Field(default_factory=list)


class EvidenceAgentOutput(BaseModel):
    """Keyed by variation title (index-free join, since detection has no ids yet)."""

    citations_by_variation: dict[str, list[EvidenceCitation]] = Field(default_factory=dict)


class CostTimeEstimate(BaseModel):
    amount: float | None = None
    estimate_low: float | None = None
    estimate_high: float | None = None
    currency: str = "AUD"
    basis_quality: str = "none"
    valuation_confidence_score: float | None = None


class CostTimeAgentOutput(BaseModel):
    estimates_by_variation: dict[str, CostTimeEstimate] = Field(default_factory=dict)


class ReportVariation(BaseModel):
    title: str
    description: str | None = None
    confidence_score: float
    time_bar_risk: bool
    evidence: list[EvidenceCitation] = Field(default_factory=list)
    estimated_value: CostTimeEstimate | None = None


class ProjectReport(BaseModel):
    project_id: str
    variations: list[ReportVariation] = Field(default_factory=list)
    recoverable_total: float | None = None


class QualityReviewResult(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    conflicting_evidence: bool = False
    report: ProjectReport


class FinalResult(BaseModel):
    """The scaffold's terminal output — run.py returns this as a dict."""

    project_id: str
    report: ProjectReport
    quality: QualityReviewResult
    requires_human_review: bool
    review_reasons: list[str] = Field(default_factory=list)
