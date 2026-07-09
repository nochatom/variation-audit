"""Builds the Root Orchestrator agent tree, matching the approved diagram:

    intake
      -> Parallel[document, contract]
      -> variation_detection
      -> Parallel[evidence, cost_time]
      -> report_generation
      -> quality_review
      -> human_review_gate

Session/Memory/Tool Registry are infrastructure (ADK's InMemorySessionService
+ each LlmAgent's own `tools=[...]`), not agents — wired in run.py, not here.
Observability: ADK's before/after_agent_callback hooks are attached to every
node so every step logs its name and elapsed time via this backend's
existing structured `logging` module (no new logging framework introduced).

Progress reporting: an optional `on_agent_complete(agent_name, percent)` hook
lets a caller (app/agents/worker.py) persist progress to AgentAnalysisJob
without this module knowing anything about jobs or the DB — the orchestrator
only ever calls the hook it's given, keeping agent logic and execution
lifecycle management separate per the "worker only manages execution
lifecycle" requirement.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from google.adk.agents import ParallelAgent, SequentialAgent  # deprecated toward Workflow in ADK 2.4+;
                                                                # kept per requirements.txt pin — Workflow
                                                                # can't yet be an LlmAgent sub-agent.

from app.agents.agent_definitions import (
    build_contract_agent,
    build_cost_time_agent,
    build_document_agent,
    build_evidence_agent,
    build_quality_review_agent,
    build_report_generation_agent,
    build_variation_detection_agent,
)
from app.agents.context import current_agent_name
from app.agents.human_review_gate import HumanReviewGate
from app.agents.intake_agent import ProjectIntakeAgent

logger = logging.getLogger("app.agents")

_START_TIME_KEY = "_agent_start_time"

# Percent-complete reached once this agent finishes — matches the spec's
# example progress curve exactly (Intake 10 / Document+Contract 30 /
# Variation 55 / Evidence 70 / Cost&Time 85 / Report 95). Quality Review and
# the Human Review gate get the remaining headroom to 100, which the caller
# sets explicitly once the job is actually persisted as COMPLETED.
AGENT_PROGRESS: dict[str, int] = {
    "project_intake_agent": 10,
    "document_agent": 20,
    "contract_agent": 30,
    "variation_detection_agent": 55,
    "evidence_agent": 70,
    "cost_time_agent": 85,
    "report_generation_agent": 95,
    "quality_review_agent": 98,
    "human_review_gate": 99,
}

OnAgentComplete = Callable[[str, int], None]


def _before_agent_callback(callback_context) -> None:
    callback_context.state[_START_TIME_KEY] = time.monotonic()
    # Task-local under asyncio — see context.py's docstring. Left set (not
    # reset) after the agent finishes: reliable_llm.py only ever reads it
    # during this agent's own model call, and the next agent's own
    # before-callback overwrites it before its call happens.
    current_agent_name.set(callback_context.agent_name)
    logger.info("agent.start", extra={"agent": callback_context.agent_name})


def _make_after_callback(on_agent_complete: OnAgentComplete | None):
    def _after_agent_callback(callback_context) -> None:
        started = callback_context.state.get(_START_TIME_KEY)
        elapsed_ms = (time.monotonic() - started) * 1000 if started else None
        logger.info(
            "agent.end",
            extra={"agent": callback_context.agent_name, "elapsed_ms": elapsed_ms},
        )
        if on_agent_complete is not None:
            percent = AGENT_PROGRESS.get(callback_context.agent_name)
            if percent is not None:
                on_agent_complete(callback_context.agent_name, percent)

    return _after_agent_callback


def _with_observability(agent, on_agent_complete: OnAgentComplete | None):
    agent.before_agent_callback = _before_agent_callback
    agent.after_agent_callback = _make_after_callback(on_agent_complete)
    return agent


def build_orchestrator(
    session: Session | None = None,
    project_id: str | None = None,
    is_enterprise_plan: bool = False,
    on_agent_complete: OnAgentComplete | None = None,
) -> SequentialAgent:
    """Construct the full agent tree.

    `session`/`project_id` are only required to build the DB-backed
    Document/Contract agents' tools; both may be omitted purely to prove
    the tree constructs (see tests/test_agents_scaffold.py), in which case
    the Document/Contract agents are built with placeholder identifiers
    that error clearly if ever actually invoked.

    `on_agent_complete`, if given, is called as `(agent_name, percent)`
    after every agent finishes — see AGENT_PROGRESS above.
    """
    session = session if session is not None else _NullSession()
    project_id = project_id or "unset-project-id"

    def wrap(agent):
        return _with_observability(agent, on_agent_complete)

    intake = wrap(ProjectIntakeAgent(name="project_intake_agent", session=session, project_id=project_id))
    document = wrap(build_document_agent(session, project_id))
    contract = wrap(build_contract_agent(session, project_id))
    variation_detection = wrap(build_variation_detection_agent())
    evidence = wrap(build_evidence_agent())
    cost_time = wrap(build_cost_time_agent())
    report = wrap(build_report_generation_agent())
    quality_review = wrap(build_quality_review_agent())
    human_review_gate = wrap(
        HumanReviewGate(name="human_review_gate", is_enterprise_plan=is_enterprise_plan)
    )

    gather = ParallelAgent(name="gather_document_and_contract", sub_agents=[document, contract])
    assess = ParallelAgent(name="assess_evidence_and_cost_time", sub_agents=[evidence, cost_time])

    return SequentialAgent(
        name="variation_iq_root_orchestrator",
        sub_agents=[
            intake,
            gather,
            variation_detection,
            assess,
            report,
            quality_review,
            human_review_gate,
        ],
    )


class _NullSession:
    """Placeholder DB session for construction-only use (no query ever runs)."""

    def get(self, *_args, **_kwargs):
        raise RuntimeError("orchestrator built without a real DB session — cannot execute")

    def execute(self, *_args, **_kwargs):
        raise RuntimeError("orchestrator built without a real DB session — cannot execute")
