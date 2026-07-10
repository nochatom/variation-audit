"""What the ProviderRouter hands back — see docs/decisions/26-provider-router.md
ADR-4 for why this carries a reasoning string rather than four separate
numeric scores (not every routing policy computes all four).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProviderSelection:
    """One ranked candidate returned by ProviderRouter.select(). The
    caller (model_provider.py) takes the top entry as primary and the
    second as fallback — see docs/decisions/26-provider-router.md §7."""

    provider: str
    model: str
    policy: str
    routing_reason: str
    selection_id: uuid.UUID
    selected_at: datetime
