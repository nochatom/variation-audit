"""Provider-agnostic, production-reliable model resolution for the agent
scaffold.

Every LlmAgent constructor asks for a model by role via get_model() and
never hardcodes a provider — model_provider.py is the ONLY file that
changed for Phase 4 (plus a one-line worker.py telemetry addition); every
other agent/orchestrator file is unmodified. What get_model() returns is
still a ReliableLlm (app/agents/reliable_llm.py) — its retry/timeout/
fallback/schema-validation/metrics behavior is completely untouched.

Selection is now dynamic (docs/decisions/26-provider-router.md): role ->
ROLE_REQUIREMENTS (capability_requirements.py) -> ProviderRouter.select()
-> top-2 ProviderSelections -> primary/fallback ReliableLlm, using the
DB-backed health/circuit sources (provider_health.py, circuit_breaker.py)
so a provider that's actually tripped its circuit is genuinely excluded in
production, not just structurally capable of being excluded.

Backward compatibility (Phase 4 merge gate): with VA_AGENT_ROUTING_POLICY=
highest_priority and the current registry seed (only nvidia_nim/
openai/gpt-oss-120b enabled), this produces the exact same LiteLlm
model/api_key/timeout the old static agent_model_provider selection did —
see tests/test_model_provider_phase4.py's backward-compat test, which runs
both implementations side by side and asserts identical output.

If ProviderRouter.select() finds no viable candidate (every provider
disabled, or every candidate's circuit open), it raises
NoProviderAvailableError — get_model() lets it propagate unchanged. Never
silently falls back to an undefined provider.
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache

from app.agents.capability_requirements import ROLE_REQUIREMENTS
from app.agents.provider_selection import ProviderSelection

logger = logging.getLogger("app.agents.model_provider")

# In-process short-circuit for the telemetry DB itself (see
# _ResilientHealthSource/_ResilientCircuitSource below): one agent
# construction calls these up to twice per role (health + circuit) across
# up to 7 roles — without this, a genuinely unreachable telemetry DB would
# pay a fresh multi-second connect timeout on every single one of those
# calls. Once any call fails, skip attempting a new connection for this
# many seconds and degrade immediately instead.
_TELEMETRY_DB_RETRY_AFTER_S = 30.0
_telemetry_db_unavailable_until = 0.0


def _telemetry_db_marked_down() -> bool:
    return time.monotonic() < _telemetry_db_unavailable_until


def _mark_telemetry_db_down() -> None:
    global _telemetry_db_unavailable_until
    _telemetry_db_unavailable_until = time.monotonic() + _TELEMETRY_DB_RETRY_AFTER_S

# (provider, model) -> (settings field holding its API key, request timeout
# seconds). The provider/model values here must match capability_registry.py
# entries exactly — this is the only place secrets/timeouts are looked up,
# deliberately kept out of the registry (static, no credentials) and out of
# the router (selection only, never touches credentials or transport).
_MODEL_RUNTIME_CONFIG: dict[tuple[str, str], tuple[str, int]] = {
    ("nvidia_nim", "openai/gpt-oss-120b"): ("nvidia_nim_openai_api_key", 60),
    ("nvidia_nim", "z-ai/glm-5.2"): ("nvidia_nim_glm_api_key", 60),
    # gemma-4-31b-it measured a genuine 60-90s+ cold start live in an
    # earlier session — 120s gives headroom above the worst observed case.
    ("nvidia_nim", "google/gemma-4-31b-it"): ("nvidia_nim_gemini_api_key", 120),
    ("anthropic", "claude-sonnet-5"): ("anthropic_agent_api_key", 60),
}


@lru_cache
def _telemetry_session_factory():
    """A dedicated session factory for circuit/health reads at agent-
    construction time — deliberately separate from app.db's shared engine
    (used for the actual job/business data), with a short connect timeout,
    so an unreachable or slow telemetry DB fails fast (a few seconds)
    instead of blocking agent construction for the driver's full default
    connect timeout (which can be minutes). Cached: built once per process,
    not once per agent."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.config import get_settings

    engine = create_engine(
        get_settings().database_url,
        pool_pre_ping=False,
        connect_args={"connect_timeout": 2},
    )
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


class _ResilientHealthSource:
    """Wraps DbHealthSource: a telemetry-DB outage must never block agent
    construction — degrades to 'no data' on any error (routing_policies.py
    already handles that case explicitly), logging once rather than
    propagating. Checks the module-level short-circuit first so a known-down
    DB doesn't pay a fresh connect timeout on every call."""

    def __init__(self, delegate):
        self._delegate = delegate

    def get(self, provider: str):
        if _telemetry_db_marked_down():
            return None
        try:
            return self._delegate.get(provider)
        except Exception:  # noqa: BLE001 - a telemetry read must never block selection
            logger.warning("provider health lookup failed for %s — treating as no data",
                           provider, exc_info=True)
            _mark_telemetry_db_down()
            return None


class _ResilientCircuitSource:
    """Wraps DbCircuitBreaker with the same fail-open philosophy as
    _ResilientHealthSource above: an unreachable circuit-state DB degrades
    to 'treat as closed' (selectable), never blocks or crashes agent
    construction. When the DB is actually reachable, real circuit state is
    honored exactly as Phase 3 built it — this only changes behavior on a
    telemetry-infrastructure failure, not on a genuinely open circuit."""

    def __init__(self, delegate):
        self._delegate = delegate

    def is_open(self, provider: str) -> bool:
        if _telemetry_db_marked_down():
            return False
        try:
            return self._delegate.is_open(provider)
        except Exception:  # noqa: BLE001 - a telemetry read must never block selection
            logger.warning("circuit state check failed for %s — treating as closed",
                           provider, exc_info=True)
            _mark_telemetry_db_down()
            return False


def _build_router():
    from app.agents.circuit_breaker import DbCircuitBreaker
    from app.agents.provider_health import DbHealthSource
    from app.agents.provider_router import ProviderRouter

    session_factory = _telemetry_session_factory()
    return ProviderRouter(
        health_source=_ResilientHealthSource(DbHealthSource(session_factory)),
        circuit_source=_ResilientCircuitSource(DbCircuitBreaker(session_factory)),
    )


def _build_litellm_from_selection(selection: ProviderSelection):
    from google.adk.models.lite_llm import LiteLlm

    from app.config import get_settings

    settings = get_settings()
    key_setting, timeout = _MODEL_RUNTIME_CONFIG.get((selection.provider, selection.model), (None, 60))
    api_key = getattr(settings, key_setting) if key_setting else None
    return LiteLlm(model=f"{selection.provider}/{selection.model}", api_key=api_key, timeout=timeout)


def get_model(role: str) -> object:
    """Resolve the model to use for an agent, by role.

    Returns a ReliableLlm wrapping the top-ranked ProviderRouter selection
    as primary and the second-ranked (if any) as fallback — same
    ReliableLlm construction as before Phase 4, just fed dynamically
    selected models instead of a single static config value. Raises
    NoProviderAvailableError (app/agents/errors.py) if the router finds no
    viable candidate — never silently substitutes an undefined provider.
    """
    from app.agents.reliable_llm import ReliableLlm

    requirements = ROLE_REQUIREMENTS[role]
    router = _build_router()
    selections = router.select(requirements)  # raises NoProviderAvailableError if empty

    primary_selection = selections[0]
    primary = _build_litellm_from_selection(primary_selection)

    fallback = None
    fallback_provider = None
    if len(selections) > 1:
        fallback_selection = selections[1]
        fallback = _build_litellm_from_selection(fallback_selection)
        fallback_provider = fallback_selection.provider

    return ReliableLlm(
        primary=primary, primary_provider=primary_selection.provider,
        fallback=fallback, fallback_provider=fallback_provider,
    )
