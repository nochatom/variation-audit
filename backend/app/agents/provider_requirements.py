"""What an agent role needs from a model — the ProviderRouter's actual
contract (see docs/decisions/26-provider-router.md, ADR-1). The router
accepts this object, never a bare role string, so it has no concept of
"agent role" at all — only of requirements.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderRequirements:
    """Declarative, immutable statement of what a caller needs. Resolved
    once per agent construction (capability_requirements.py) — never
    mutated afterward."""

    capabilities: list[str] = field(default_factory=list)
    min_context: int | None = None
    requires_json: bool = False
    requires_tools: bool = False
