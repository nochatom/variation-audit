"""Unit tests for the app/agents scaffold — no live model calls (no API key
available in this environment). Covers: tools.py against FakeSession, the
two deterministic BaseAgents (intake, human review gate), review_rules.py,
model_provider.py's provider switch, and full orchestrator construction.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from app.agents import review_rules
from app.agents.human_review_gate import (
    STATE_QUALITY_REVIEW,
    STATE_REQUIRES_HUMAN_REVIEW,
    STATE_REVIEW_REASONS,
    HumanReviewGate,
)
from app.agents.intake_agent import STATE_INTAKE_ERROR, ProjectIntakeAgent
from app.agents.orchestrator import build_orchestrator
from app.agents.schemas import (
    EvidenceCitation,
    ProjectReport,
    QualityReviewResult,
    ReportVariation,
)
from app.agents.tools import make_get_contract_baseline_tool, make_list_project_documents_tool
from app.models import Document, Project, SourceType
from tests.fakes import FakeResult, FakeSession


class _FakeState(dict):
    pass


class _FakeADKSession:
    def __init__(self):
        self.state = _FakeState()


class _FakeInvocationContext:
    def __init__(self):
        self.session = _FakeADKSession()


def _run(coro_factory):
    async def _drain():
        events = []
        async for event in coro_factory():
            events.append(event)
        return events

    return asyncio.run(_drain())


# --------------------------------------------------------------------------
# tools.py
# --------------------------------------------------------------------------
class _FakeLoader:
    def load(self, storage_key: str) -> str:
        return f"content-of:{storage_key}"


def test_list_project_documents_tool_wraps_query_and_loader():
    doc = Document(
        id=uuid.uuid4(), company_id=uuid.uuid4(), project_id=uuid.uuid4(),
        source_type=SourceType.email, storage_key="docs/1.txt",
    )
    session = FakeSession(results=[FakeResult(scalars=[doc])])
    tool = make_list_project_documents_tool(session, _FakeLoader(), str(doc.project_id))

    result = tool()

    assert result["documents"] == [
        {"document_id": str(doc.id), "source_type": "email", "content": "content-of:docs/1.txt"}
    ]


def test_get_contract_baseline_tool_reads_project_fields():
    project = Project(
        id=uuid.uuid4(), company_id=uuid.uuid4(), name="P",
        contract_text="the contract", scope_text="the scope", state="NSW",
    )
    session = FakeSession(get_obj=project)
    tool = make_get_contract_baseline_tool(session, str(project.id))

    result = tool()

    assert result == {"contract_text": "the contract", "scope_text": "the scope", "state": "NSW"}


def test_get_contract_baseline_tool_handles_missing_project():
    session = FakeSession(get_obj=None)
    tool = make_get_contract_baseline_tool(session, "missing-id")

    result = tool()

    assert result == {"contract_text": "", "scope_text": "", "state": None}


# --------------------------------------------------------------------------
# intake_agent.py
# --------------------------------------------------------------------------
def test_intake_agent_rejects_project_with_no_contract_text():
    project = Project(id=uuid.uuid4(), company_id=uuid.uuid4(), name="P", contract_text=None)
    session = FakeSession(get_obj=project)
    agent = ProjectIntakeAgent(name="intake", session=session, project_id=str(project.id))
    ctx = _FakeInvocationContext()

    _run(lambda: agent._run_async_impl(ctx))

    assert ctx.session.state[STATE_INTAKE_ERROR]
    assert "contract_text" in ctx.session.state[STATE_INTAKE_ERROR]
    assert "project_id" not in ctx.session.state


def test_intake_agent_seeds_state_for_valid_project():
    project = Project(
        id=uuid.uuid4(), company_id=uuid.uuid4(), name="P",
        contract_text="valid contract", scope_text="scope", state="VIC",
    )
    session = FakeSession(get_obj=project)
    agent = ProjectIntakeAgent(name="intake", session=session, project_id=str(project.id))
    ctx = _FakeInvocationContext()

    _run(lambda: agent._run_async_impl(ctx))

    assert ctx.session.state[STATE_INTAKE_ERROR] is None
    assert ctx.session.state["project_id"] == str(project.id)
    assert ctx.session.state["contract_text"] == "valid contract"
    assert ctx.session.state["state"] == "VIC"


# --------------------------------------------------------------------------
# review_rules.py
# --------------------------------------------------------------------------
def _quality(**overrides) -> QualityReviewResult:
    defaults = dict(
        passed=True,
        overall_confidence=0.9,
        conflicting_evidence=False,
        report=ProjectReport(
            project_id="p1",
            variations=[
                ReportVariation(
                    title="V1", confidence_score=0.9, time_bar_risk=False,
                    evidence=[EvidenceCitation(reference="ref", quote="q")],
                )
            ],
        ),
    )
    defaults.update(overrides)
    return QualityReviewResult(**defaults)


def test_review_rules_all_clear_needs_no_review():
    reasons = review_rules.evaluate(_quality(), review_rules.ReviewContext())
    assert reasons == []


def test_review_rules_low_confidence_triggers():
    reasons = review_rules.evaluate(_quality(overall_confidence=0.2), review_rules.ReviewContext())
    assert any("confidence" in r for r in reasons)


def test_review_rules_conflicting_evidence_triggers():
    reasons = review_rules.evaluate(_quality(conflicting_evidence=True), review_rules.ReviewContext())
    assert any("conflicting" in r for r in reasons)


def test_review_rules_missing_citation_triggers():
    report = ProjectReport(
        project_id="p1",
        variations=[ReportVariation(title="V1", confidence_score=0.9, time_bar_risk=False, evidence=[])],
    )
    reasons = review_rules.evaluate(_quality(report=report), review_rules.ReviewContext())
    assert any("citation" in r for r in reasons)


def test_review_rules_enterprise_policy_triggers():
    reasons = review_rules.evaluate(_quality(), review_rules.ReviewContext(is_enterprise_plan=True))
    assert any("enterprise" in r for r in reasons)


# --------------------------------------------------------------------------
# human_review_gate.py
# --------------------------------------------------------------------------
def test_human_review_gate_flags_when_a_rule_fires():
    agent = HumanReviewGate(name="gate", is_enterprise_plan=False)
    ctx = _FakeInvocationContext()
    ctx.session.state[STATE_QUALITY_REVIEW] = _quality(overall_confidence=0.1).model_dump()

    _run(lambda: agent._run_async_impl(ctx))

    assert ctx.session.state[STATE_REQUIRES_HUMAN_REVIEW] is True
    assert ctx.session.state[STATE_REVIEW_REASONS]


def test_human_review_gate_passes_through_when_clean():
    agent = HumanReviewGate(name="gate", is_enterprise_plan=False)
    ctx = _FakeInvocationContext()
    ctx.session.state[STATE_QUALITY_REVIEW] = _quality().model_dump()

    _run(lambda: agent._run_async_impl(ctx))

    assert ctx.session.state[STATE_REQUIRES_HUMAN_REVIEW] is False
    assert ctx.session.state[STATE_REVIEW_REASONS] == []


# --------------------------------------------------------------------------
# model_provider.py
# --------------------------------------------------------------------------
class _FakeAgentSettings:
    agent_model_provider = "openai"
    anthropic_agent_api_key = None
    nvidia_nim_openai_api_key = "key-openai"
    nvidia_nim_glm_api_key = "key-glm"
    nvidia_nim_gemini_api_key = "key-gemini"


@pytest.mark.parametrize("provider", ["openai", "glm", "gemini", "claude"])
def test_get_model_returns_reliable_llm_for_every_known_provider(monkeypatch, provider):
    from app.agents import model_provider
    from app.agents.reliable_llm import ReliableLlm

    settings = _FakeAgentSettings()
    settings.agent_model_provider = provider
    monkeypatch.setattr(model_provider, "get_settings", lambda: settings)
    model = model_provider.get_model("variation_detection")

    assert isinstance(model, ReliableLlm)
    # every non-openai provider gets an openai-role fallback; openai itself doesn't
    assert (model._fallback is not None) == (provider != "openai")


def test_get_model_rejects_unknown_provider(monkeypatch):
    from app.agents import model_provider

    settings = _FakeAgentSettings()
    settings.agent_model_provider = "bogus"
    monkeypatch.setattr(model_provider, "get_settings", lambda: settings)

    with pytest.raises(ValueError):
        model_provider.get_model("variation_detection")


# --------------------------------------------------------------------------
# orchestrator.py — full-tree construction, no DB/API key needed
# --------------------------------------------------------------------------
def test_orchestrator_constructs_matching_the_diagram_shape():
    tree = build_orchestrator()

    assert tree.name == "variation_iq_root_orchestrator"
    names = [a.name for a in tree.sub_agents]
    assert names == [
        "project_intake_agent",
        "gather_document_and_contract",
        "variation_detection_agent",
        "assess_evidence_and_cost_time",
        "report_generation_agent",
        "quality_review_agent",
        "human_review_gate",
    ]

    gather = tree.sub_agents[1]
    assert type(gather).__name__ == "ParallelAgent"
    assert [a.name for a in gather.sub_agents] == ["document_agent", "contract_agent"]

    assess = tree.sub_agents[3]
    assert type(assess).__name__ == "ParallelAgent"
    assert [a.name for a in assess.sub_agents] == ["evidence_agent", "cost_time_agent"]
