"""The six LlmAgent constructors: Document, Contract, Variation Detection,
Evidence, Cost & Time, Report Generation, Quality Review.

Each agent reads its inputs via `{state_key}` instruction placeholders (ADK
resolves these from session state at call time — see LlmAgent.instruction)
and writes its structured output back to state via `output_key`, so the
next agent in the tree can reference it. Models come from
app.agents.model_provider.get_model(), never hardcoded, per the
provider-agnostic requirement.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from google.adk.agents import LlmAgent

from app.agents.model_provider import get_model
from app.agents.schemas import (
    ContractAgentOutput,
    CostTimeAgentOutput,
    DocumentAgentOutput,
    EvidenceAgentOutput,
    ProjectReport,
    QualityReviewResult,
    VariationDetectionOutput,
)
from app.agents.tools import make_get_contract_baseline_tool, make_list_project_documents_tool


def build_document_agent(session: Session, project_id: str) -> LlmAgent:
    return LlmAgent(
        name="document_agent",
        model=get_model("document"),
        description="Summarizes every uploaded project document (RFIs, site instructions, emails).",
        instruction=(
            "Call list_project_documents to fetch every document for this project. "
            "For each one, write a concise summary of anything that could indicate "
            "a scope change, instruction, or variation from the contracted works."
        ),
        tools=[make_list_project_documents_tool(session, _worker_loader(), project_id)],
        output_schema=DocumentAgentOutput,
        output_key="document_agent_output",
    )


def build_contract_agent(session: Session, project_id: str) -> LlmAgent:
    return LlmAgent(
        name="contract_agent",
        model=get_model("contract"),
        description="Extracts the contract baseline: inclusions, exclusions, notice/time-bar clauses.",
        instruction=(
            "Call get_contract_baseline to fetch this project's contract_text and "
            "scope_text. Extract the baseline scope (inclusions/exclusions) and any "
            "notice or time-bar clause, per Australian construction contract conventions."
        ),
        tools=[make_get_contract_baseline_tool(session, project_id)],
        output_schema=ContractAgentOutput,
        output_key="contract_agent_output",
    )


def build_variation_detection_agent() -> LlmAgent:
    return LlmAgent(
        name="variation_detection_agent",
        model=get_model("variation_detection"),
        description="Detects variations by comparing document findings against the contract baseline.",
        instruction=(
            "Contract baseline: {contract_agent_output}\n"
            "Document findings: {document_agent_output}\n\n"
            "Identify every instance where a document indicates work, instruction, or "
            "change outside the contract baseline's scope. For each, produce a title, "
            "description, a confidence_score in [0,1], and whether it may be time-barred."
        ),
        output_schema=VariationDetectionOutput,
        output_key="variation_detection_output",
    )


def build_evidence_agent() -> LlmAgent:
    return LlmAgent(
        name="evidence_agent",
        model=get_model("evidence"),
        description="Links each detected variation back to its source document and quote.",
        instruction=(
            "Detected variations: {variation_detection_output}\n"
            "Document findings: {document_agent_output}\n\n"
            "For each variation, cite the source document(s) and an exact quote that "
            "supports it. Key the output by the variation's title."
        ),
        output_schema=EvidenceAgentOutput,
        output_key="evidence_agent_output",
    )


def build_cost_time_agent() -> LlmAgent:
    return LlmAgent(
        name="cost_time_agent",
        model=get_model("cost_time"),
        description="Estimates the value and time-bar risk of each detected variation.",
        instruction=(
            "Detected variations: {variation_detection_output}\n"
            "Contract baseline: {contract_agent_output}\n\n"
            "For each variation, estimate a cost (amount, low/high range, currency AUD, "
            "basis_quality) using rate-card or inferred pricing. Key the output by the "
            "variation's title."
        ),
        output_schema=CostTimeAgentOutput,
        output_key="cost_time_agent_output",
    )


def build_report_generation_agent() -> LlmAgent:
    return LlmAgent(
        name="report_generation_agent",
        model=get_model("report_generation"),
        description="Synthesizes detection, evidence, and cost/time output into one report.",
        instruction=(
            "Project id: {project_id}\n"
            "Detected variations: {variation_detection_output}\n"
            "Evidence: {evidence_agent_output}\n"
            "Cost & time estimates: {cost_time_agent_output}\n\n"
            "Combine these into one ProjectReport: one ReportVariation per detected "
            "variation, merging in its evidence and estimated value, plus a "
            "recoverable_total summing all estimated amounts."
        ),
        output_schema=ProjectReport,
        output_key="project_report",
    )


def build_quality_review_agent() -> LlmAgent:
    return LlmAgent(
        name="quality_review_agent",
        model=get_model("quality_review"),
        description="Validates the report before it's returned: citations, non-negative values, contradictions.",
        instruction=(
            "Report: {project_report}\n\n"
            "Check: every variation has at least one evidence citation; all estimated "
            "values are non-negative; no two variations' evidence directly contradicts "
            "each other. Set passed accordingly, list any issues, compute an "
            "overall_confidence in [0,1] (the average of the variations' confidence "
            "scores, or 1.0 if there are none), and set conflicting_evidence if any "
            "contradiction was found. Include the report unchanged."
        ),
        output_schema=QualityReviewResult,
        output_key="quality_review_result",
    )


def _worker_loader():
    """Reuse the exact same document loader the production worker uses."""
    from app.storage import build_loader

    return build_loader()
