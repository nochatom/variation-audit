"""Project Intake Agent — deterministic validation, no model call.

A custom BaseAgent, not an LlmAgent: intake is a routing/validation step
(load the Project row, verify contract_text is non-empty, seed session
state), not a reasoning step, so it shouldn't burn a model call. Writes a
clear error into state rather than raising, mirroring the existing
/analyze endpoint's own 400 guard (app/routers/projects.py).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.events.event_actions import EventActions
from pydantic import PrivateAttr
from sqlalchemy.orm import Session

from app.models import Project

STATE_INTAKE_ERROR = "intake_error"


class ProjectIntakeAgent(BaseAgent):
    """Loads the Project row for `project_id` and seeds initial session state."""

    _session: Session = PrivateAttr()
    _project_id: str = PrivateAttr()

    def __init__(self, name: str, session: Session, project_id: str):
        super().__init__(name=name)
        self._session = session
        self._project_id = project_id

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        project = self._session.get(Project, self._project_id)

        if project is None or not (project.contract_text or "").strip():
            ctx.session.state[STATE_INTAKE_ERROR] = (
                f"project {self._project_id} has no contract_text — cannot run analysis"
            )
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={STATE_INTAKE_ERROR: ctx.session.state[STATE_INTAKE_ERROR]}),
            )
            return

        state_delta = {
            "project_id": str(project.id),
            "company_id": str(project.company_id),
            "contract_text": project.contract_text,
            "scope_text": project.scope_text or "",
            "state": project.state,
            STATE_INTAKE_ERROR: None,
        }
        for key, value in state_delta.items():
            ctx.session.state[key] = value

        yield Event(author=self.name, actions=EventActions(state_delta=state_delta))
