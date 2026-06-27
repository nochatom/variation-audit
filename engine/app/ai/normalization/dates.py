"""Australian date normalization (deterministic, no LLM).

AU construction comms use day-first dates (DD/MM/YYYY). This normalizes common
formats to ISO-8601 so downstream stages and the product layer get one shape.
Stdlib only — no external date parser dependency.
"""
from __future__ import annotations

from datetime import datetime

# Tried in order. Day-first only (AU convention) to avoid US MM/DD ambiguity.
_FORMATS = (
    "%Y-%m-%d",       # already ISO
    "%d/%m/%Y",       # 05/03/2026
    "%d/%m/%y",       # 05/03/26
    "%d-%m-%Y",       # 05-03-2026
    "%d.%m.%Y",       # 05.03.2026
    "%d %B %Y",       # 5 March 2026
    "%d %b %Y",       # 5 Mar 2026
    "%B %d, %Y",      # March 5, 2026
    "%b %d, %Y",      # Mar 5, 2026
)


def normalize_date(value: str | None) -> str | None:
    """Return an ISO-8601 date (YYYY-MM-DD) for a recognised AU date, else None."""
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    for fmt in _FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None
