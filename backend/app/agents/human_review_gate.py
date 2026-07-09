"""Human Review Gate — deterministic, rule-driven, no model call.

Evaluates review_rules.py against the Quality Review Agent's output. ADK's
InMemoryRunner is a single async pass, not a durable workflow engine with
suspend/resume — so this gate does not pause the run. Instead it sets
requires_human_review + review_reasons on the final state, so a caller can
route flagged output into VariationIQ's *existing* human-review mechanism
(Variation.review_status pending/confirmed/rejected via
/variations/{id}/review) once this scaffold is wired into persistence.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.events.event_actions import EventActions
from pydantic import PrivateAttr

from app.agents.review_rules import DEFAULT_RULES, ReviewContext, Rule, evaluate
from app.agents.schemas import QualityReviewResult

STATE_QUALITY_REVIEW = "quality_review_result"
STATE_REQUIRES_HUMAN_REVIEW = "requires_human_review"
STATE_REVIEW_REASONS = "review_reasons"


class HumanReviewGate(BaseAgent):
    """Reads `quality_review_result` from state, writes the review verdict back."""

    _is_enterprise_plan: bool = PrivateAttr()
    _rules: list[Rule] = PrivateAttr()

    def __init__(self, name: str, is_enterprise_plan: bool = False, rules: list[Rule] = DEFAULT_RULES):
        super().__init__(name=name)
        self._is_enterprise_plan = is_enterprise_plan
        self._rules = rules

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        raw_quality = ctx.session.state.get(STATE_QUALITY_REVIEW)
        quality = (
            raw_quality if isinstance(raw_quality, QualityReviewResult)
            else QualityReviewResult.model_validate(raw_quality)
        )

        reasons = evaluate(quality, ReviewContext(is_enterprise_plan=self._is_enterprise_plan), self._rules)

        state_delta = {
            STATE_REQUIRES_HUMAN_REVIEW: bool(reasons),
            STATE_REVIEW_REASONS: reasons,
        }
        for key, value in state_delta.items():
            ctx.session.state[key] = value

        yield Event(author=self.name, actions=EventActions(state_delta=state_delta))
