"""Ambient run context for observability — set once per run/agent, read by
app/agents/reliable_llm.py so per-call logs and metrics carry job/agent
identity without threading them through every LlmAgent/tool constructor.
"""
from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar

current_job_id: ContextVar[str | None] = ContextVar("current_job_id", default=None)

# Set by app/agents/orchestrator.py's before/after_agent_callback for the
# duration of one agent's execution. Task-local under asyncio (each
# ParallelAgent branch runs as its own Task with its own copy of the
# context), so Document/Contract or Evidence/Cost&Time running concurrently
# never see each other's agent name.
current_agent_name: ContextVar[str | None] = ContextVar("current_agent_name", default=None)

# Set by app/agents/run.py for the duration of one job's run. Receives one
# dict per completed LLM call (see reliable_llm.py's consolidated metrics
# log) — app/agents/worker.py uses it to collect AgentAnalysisJob.llm_calls.
current_llm_call_sink: ContextVar[Callable[[dict], None] | None] = ContextVar(
    "current_llm_call_sink", default=None
)
