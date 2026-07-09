"""Standalone entry point for the agent scaffold.

NOT wired into app/worker/job_worker.py's loop — this is an additive,
separately-invoked path (per the approved plan) until a real integration
decision is made about persisting agent output into
Variation/Evidence/ValueEstimate rows.
"""
from __future__ import annotations

from google.adk.runners import InMemoryRunner
from google.genai import types
from sqlalchemy.orm import Session

from collections.abc import Callable

from app.agents.context import current_job_id, current_llm_call_sink
from app.agents.human_review_gate import STATE_REQUIRES_HUMAN_REVIEW, STATE_REVIEW_REASONS
from app.agents.intake_agent import STATE_INTAKE_ERROR
from app.agents.orchestrator import OnAgentComplete, build_orchestrator
from app.agents.schemas import FinalResult, ProjectReport, QualityReviewResult

APP_NAME = "variationiq-agents"


async def analyze_project_with_agents(
    session: Session,
    project_id: str,
    user_id: str = "system",
    is_enterprise_plan: bool = False,
    job_id: str | None = None,
    on_agent_complete: OnAgentComplete | None = None,
    on_llm_call: Callable[[dict], None] | None = None,
) -> dict:
    """Run the full agent tree for one project and return a FinalResult dict.

    Raises RuntimeError if Project Intake rejects the project (e.g. no
    contract_text) — mirrors the existing /analyze endpoint's 400 guard,
    just surfaced as an exception since this has no HTTP layer of its own.
    Raises an AIProviderError subclass (app/agents/errors.py) if every model
    call — primary and fallback — ultimately fails.

    `job_id`, if given, is stamped into every LLM-call log line via a
    contextvar (app/agents/context.py) for the duration of this run, without
    threading it through every agent/tool constructor. `on_agent_complete`
    is forwarded straight to build_orchestrator() for progress reporting.
    `on_llm_call`, if given, receives one metrics dict (provider/model/
    tokens/latency_ms/number_of_retries/fallback_used) per completed LLM
    call — app/agents/worker.py uses this to collect AgentAnalysisJob.llm_calls.
    """
    job_token = current_job_id.set(job_id)
    sink_token = current_llm_call_sink.set(on_llm_call)
    try:
        return await _run(session, project_id, user_id, is_enterprise_plan, on_agent_complete)
    finally:
        current_job_id.reset(job_token)
        current_llm_call_sink.reset(sink_token)


async def _run(
    session: Session,
    project_id: str,
    user_id: str,
    is_enterprise_plan: bool,
    on_agent_complete: OnAgentComplete | None,
) -> dict:
    orchestrator = build_orchestrator(
        session=session, project_id=project_id, is_enterprise_plan=is_enterprise_plan,
        on_agent_complete=on_agent_complete,
    )

    runner = InMemoryRunner(agent=orchestrator, app_name=APP_NAME)
    adk_session = await runner.session_service.create_session(app_name=APP_NAME, user_id=user_id)

    final_state: dict = {}
    async for event in runner.run_async(
        user_id=user_id,
        session_id=adk_session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=f"Analyze project {project_id}")]),
    ):
        if event.actions and event.actions.state_delta:
            final_state.update(event.actions.state_delta)

    intake_error = final_state.get(STATE_INTAKE_ERROR)
    if intake_error:
        raise RuntimeError(intake_error)

    raw_quality = final_state.get("quality_review_result")
    quality = (
        raw_quality if isinstance(raw_quality, QualityReviewResult)
        else QualityReviewResult.model_validate(raw_quality)
        if raw_quality
        else QualityReviewResult(
            passed=False, overall_confidence=0.0,
            report=ProjectReport(project_id=project_id),
        )
    )

    result = FinalResult(
        project_id=project_id,
        report=quality.report,
        quality=quality,
        requires_human_review=bool(final_state.get(STATE_REQUIRES_HUMAN_REVIEW, False)),
        review_reasons=final_state.get(STATE_REVIEW_REASONS, []),
    )
    return result.model_dump()
