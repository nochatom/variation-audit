"""Configurable rules deciding whether a run needs Human Review.

Each rule is a small pure function: (QualityReviewResult, context) -> reason
string or None. Kept independent of ADK/BaseAgent so they're trivially
unit-testable and easy to extend — human_review_gate.py just runs the list
and collects whichever reasons fire. Mirrors the diagram's stated triggers:
low confidence, conflicting evidence, missing citations, enterprise policy.
"""
from __future__ import annotations

from collections.abc import Callable

from app.agents.schemas import QualityReviewResult

LOW_CONFIDENCE_THRESHOLD = 0.6

Rule = Callable[[QualityReviewResult, "ReviewContext"], str | None]


class ReviewContext:
    """Non-report inputs a rule may need — kept minimal and explicit."""

    def __init__(self, is_enterprise_plan: bool = False):
        self.is_enterprise_plan = is_enterprise_plan


def rule_low_confidence(quality: QualityReviewResult, ctx: ReviewContext) -> str | None:
    del ctx
    if quality.overall_confidence < LOW_CONFIDENCE_THRESHOLD:
        return f"overall confidence {quality.overall_confidence:.2f} below threshold {LOW_CONFIDENCE_THRESHOLD}"
    return None


def rule_conflicting_evidence(quality: QualityReviewResult, ctx: ReviewContext) -> str | None:
    del ctx
    if quality.conflicting_evidence:
        return "quality review flagged conflicting evidence"
    return None


def rule_missing_citations(quality: QualityReviewResult, ctx: ReviewContext) -> str | None:
    del ctx
    missing = [v.title for v in quality.report.variations if not v.evidence]
    if missing:
        return f"{len(missing)} variation(s) missing evidence citations: {', '.join(missing)}"
    return None


def rule_enterprise_policy(quality: QualityReviewResult, ctx: ReviewContext) -> str | None:
    del quality
    if ctx.is_enterprise_plan:
        return "enterprise plan policy requires human review of every run"
    return None


DEFAULT_RULES: list[Rule] = [
    rule_low_confidence,
    rule_conflicting_evidence,
    rule_missing_citations,
    rule_enterprise_policy,
]


def evaluate(
    quality: QualityReviewResult,
    ctx: ReviewContext,
    rules: list[Rule] = DEFAULT_RULES,
) -> list[str]:
    """Run every rule, return the reasons that fired (empty = no review needed)."""
    reasons = []
    for rule in rules:
        reason = rule(quality, ctx)
        if reason:
            reasons.append(reason)
    return reasons
