# .26 — Provider Router: policy-driven, health-aware model selection

Status: Approved (design). Not yet implemented.
Scope: `backend/app/agents/` only. Additive infrastructure — no change to the
agent graph, orchestrator, worker, queue, heartbeat, or `ReliableLlm`'s
execution responsibilities.

## 1. Problem

`model_provider.get_model(role)` today picks a model via one flat setting
(`VA_AGENT_MODEL_PROVIDER`) applied identically to every agent, with a
hardcoded fallback. There's no way to: express that different agents need
different capabilities (e.g. `variation_detection_agent` needs long-context
legal reasoning, `cost_time_agent` doesn't); route around a provider that's
currently unhealthy; or add a new provider/model without touching code that
also knows how to build `LiteLlm`/`ReliableLlm` instances.

This adds a **Provider Router** layer between agent construction and
`ReliableLlm`, responsible *only* for deciding which provider/model to hand
`ReliableLlm` — never for executing, retrying, validating, or logging a
call. Those stay exactly where they are today.

## 2. Architecture

```
Agent (agent_definitions.py — unchanged)
      │  calls model_provider.get_model(role)
      ▼
Capability Requirements (capability_requirements.py)
      │  role -> ProviderRequirements
      ▼
Provider Router (provider_router.py)
      │  filters registry by capability + circuit state,
      │  applies routing policy, ranks candidates
      ▼
ProviderSelection (top-2: primary + fallback)
      │  model_provider.py builds LiteLlm instances from these
      ▼
ReliableLlm (reliable_llm.py — UNCHANGED)
      │  retries, timeout, schema validation, fallback execution,
      │  metrics, structured logging — exactly as today
      ▼
Provider  →  Model
```

Everything below the `ReliableLlm` line, and everything above the `Agent`
line (orchestrator, worker, queue), is out of scope and untouched.

## 3. Component responsibilities

| Component | Owns | Does NOT own |
|---|---|---|
| `capability_requirements.py` | role → `ProviderRequirements` static data | provider selection, execution |
| `capability_registry.py` | static model metadata (provider, model, capabilities, context, flags, priority, enabled) | dynamic health, selection logic |
| `provider_health.py` | reads/writes `provider_call_log`; computes aggregates | circuit state transitions |
| `circuit_breaker.py` | circuit state machine, reads/writes `provider_circuit_state` | health metrics, selection |
| `routing_policies.py` | pure ranking functions given health + registry data | filtering, circuit checks |
| `provider_router.py` | orchestrates the above into one `select()` call | executing the LLM call in any way |
| `reliable_llm.py` | retries, timeout, schema validation, fallback execution, metrics, logging | choosing *which* provider/model to use |
| `model_provider.py` | glue: role → requirements → router → `ReliableLlm` construction | everything else |

## 4. `ProviderRequirements`

```python
@dataclass(frozen=True)
class ProviderRequirements:
    capabilities: list[str]
    min_context: int | None = None
    requires_json: bool = False
    requires_tools: bool = False
```

Frozen because it's a declarative fact about what a role needs, resolved
once per agent construction — never mutated. The router accepts this
object, not a role string: **the router has no concept of "agent role,"**
only of requirements, so it stays reusable for any future non-agent LLM
caller without ever needing to learn what a "document_agent" is.

## 5. `capability_requirements.py`

```python
ROLE_REQUIREMENTS: dict[str, ProviderRequirements] = {
    "document_agent": ProviderRequirements(
        capabilities=["document_extraction", "summarization"], requires_json=True),
    "contract_agent": ProviderRequirements(
        capabilities=["contract_analysis", "long_context"], min_context=32000, requires_json=True),
    "variation_detection_agent": ProviderRequirements(
        capabilities=["legal_reasoning", "contract_analysis", "structured_json"],
        min_context=32000, requires_json=True),
    "evidence_agent": ProviderRequirements(
        capabilities=["citation_generation", "structured_json"], requires_json=True),
    "cost_time_agent": ProviderRequirements(
        capabilities=["structured_json", "fast_response"], requires_json=True),
    "report_generation_agent": ProviderRequirements(
        capabilities=["formatting", "summarization", "long_context"], min_context=32000),
    "quality_review_agent": ProviderRequirements(
        capabilities=["structured_json", "legal_reasoning"], requires_json=True),
}
```

Plain dict, plain dataclass instances — **no per-agent classes, no
inheritance.** This is homogeneous configuration data (every entry has the
identical shape); a class per agent would model data as behavior for no
behavioral gain (see ADR-2). `model_provider.py`'s only interaction with
this module is a dict lookup by role.

## 6. `ProviderSelection`

```python
@dataclass(frozen=True)
class ProviderSelection:
    provider: str
    model: str
    policy: str
    routing_reason: str
    selection_id: uuid.UUID
    selected_at: datetime
```

`routing_reason` is a short human-readable string the winning policy
function builds while it ranks candidates (e.g. `"nvidia_nim: healthy,
circuit closed, highest configured priority (10)"`) — free to produce
since the policy already computes this internally, and it's exactly what
an admin looking at `/internal/providers` will want to know. No separate
numeric `health_score`/`latency_score`/`capability_score`/`estimated_cost`
fields (see ADR-4) — not every policy computes all four, and forcing every
policy to populate fields it doesn't use is worse than one flexible string.

`selection_id` + `selected_at` exist purely for traceability — so a
`provider_call_log` row (§8) can reference exactly which selection decision
led to it, useful when debugging "why did this job use openai."

## 7. `ProviderRouter`

```python
class ProviderRouter:
    def select(self, requirements: ProviderRequirements) -> list[ProviderSelection]:
        """Returns a ranked list; caller takes [0] as primary, [1] as fallback."""
```

Selection pipeline, in order:
1. **Capability filter** — registry entries whose `supported_capabilities`
   is a superset of `requirements.capabilities`, `max_context >=
   min_context` (if set), `supports_json`/`supports_tools` as required,
   `enabled == True`.
2. **Circuit filter** — exclude any provider whose `circuit_breaker.py`
   state is currently OPEN.
3. **Policy ranking** — the configured `routing_policies.py` function
   (`VA_AGENT_ROUTING_POLICY` setting) ranks the remaining candidates.
4. **Tiebreak** — random shuffle among equally-ranked candidates (load
   balancing).

Returns the ranked list as `ProviderSelection` objects; `model_provider.py`
takes the top 2. If fewer than 2 candidates survive filtering, the second
slot is simply omitted (`ReliableLlm` already handles `fallback=None`).
If zero candidates survive, raises `NoProviderAvailableError` (new, in
`errors.py`) — a clear, immediate failure rather than a confusing crash
inside `ReliableLlm`.

**The router never touches the network, never retries, never parses a
response.** Every one of those stays in `ReliableLlm`, completely
unmodified.

## 8. Provider health & circuit storage

Two new tables (migration `0012_provider_health.py`), living alongside
`agent_analysis_jobs` in the same product database — no new infrastructure.

### `provider_call_log` (append-only)
```sql
CREATE TABLE provider_call_log (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider          text NOT NULL,
    model             text NOT NULL,
    selection_id      uuid,              -- ties back to the ProviderSelection that led here
    success           boolean NOT NULL,
    error_code        text,              -- AI_AUTH_ERROR / AI_RATE_LIMIT_ERROR / ... when failed
    latency_ms        integer,
    input_tokens      integer,
    output_tokens     integer,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_provider_call_log_provider_time ON provider_call_log (provider, created_at);
```
One row per completed `ReliableLlm` call — the exact same metrics dict
already produced today (§9 wiring), just also persisted per-provider
instead of only per-job.

**Cost derivation:** `estimated_cost_per_token` is dynamic health data (Part
3 of the original design explicitly separates it from static registry
metadata), but computing a dollar figure needs a price rate from
somewhere. That rate itself doesn't change with provider health, so each
`capability_registry.py` entry carries one extra static field —
`price_per_1k_tokens` — used *only* for this multiplication, never for
capability matching or filtering. `provider_health.py` computes the actual
`estimated_cost_per_token` aggregate by multiplying logged
`input_tokens`/`output_tokens` by that static rate over the query window —
so the rate is static, the resulting cost aggregate is dynamic, consistent
with the Part 2/Part 3 split.

### `provider_circuit_state` (one mutable row per provider)
```sql
CREATE TABLE provider_circuit_state (
    provider          text PRIMARY KEY,
    state             text NOT NULL DEFAULT 'closed',   -- closed | open | half_open
    failure_count     integer NOT NULL DEFAULT 0,
    opened_at         timestamptz,
    last_success       timestamptz,
    last_failure       timestamptz
);
```

**No `provider_health_snapshot` table** (ADR-3). Aggregates
(`average_latency`, `p95_latency`, `success_rate`, `failure_rate`,
`retry_rate`) are computed **at read time** from `provider_call_log`, always
bounded — e.g.:

```sql
SELECT
    avg(latency_ms),
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),
    avg(success::int)
FROM provider_call_log
WHERE provider = :provider AND created_at > now() - interval '24 hours';
```

With the `(provider, created_at)` index, this is a fast indexed range scan
regardless of table growth, at a volume (a handful of LLM calls per
analysis job, rate-limited to `10/hour` per company today) nowhere near
where a materialized snapshot would earn its keep.

## 9. Circuit breaker

Independent state per provider, transitions driven by outcomes already
classified by `errors.py`'s existing `AIProviderError` taxonomy — **no new
error types needed for this**:

```
CLOSED --[N consecutive AIProviderTimeoutError/AIProviderUnavailableError
           within the current window]--> OPEN
OPEN --[cooldown elapses]--> HALF_OPEN
HALF_OPEN --[next call succeeds]--> CLOSED
HALF_OPEN --[next call fails]--> OPEN (reset cooldown)
```

Trips on: `AIProviderTimeoutError`, `AIProviderUnavailableError`.
Never trips on: `AIAuthError` (401/403 — a config problem, not an
infrastructure one; retrying/routing around it fixes nothing),
`AISchemaValidationError` (a model-output-quality problem, not a
reachability one), `AIRateLimitError` is deliberately **excluded from
tripping the circuit** — a 429 means the provider is reachable and working,
just temporarily throttled; that's already handled by `ReliableLlm`'s own
retry/backoff, and treating it as a circuit-breaker trigger would take a
perfectly healthy provider out of rotation for a transient rate limit.

Defaults (configurable in `config.py`, matching this project's existing
`rate_limit_*`-style settings pattern): failure threshold 5, cooldown 60s.

## 10. Routing policies

`VA_AGENT_ROUTING_POLICY` setting, one of:

| Policy | Ranks by |
|---|---|
| `highest_priority` (default) | registry `priority` field, descending |
| `lowest_latency` | `provider_health`'s recent `average_latency`, ascending |
| `lowest_cost` | `provider_health`'s tracked `estimated_cost_per_token`, ascending |
| `highest_quality` | registry `priority` among only providers tagged `"high_quality"` |
| `longest_context` | registry `max_context`, descending |

Each policy function has the same signature — `(candidates: list[ModelSpec],
health: dict[str, HealthSnapshot]) -> list[ProviderSelection]` — and builds
its own `routing_reason` string. `highest_priority` as the default
reproduces today's exact static behavior when only one provider/model is
`enabled=True` per capability set — so shipping this changes nothing about
current runtime behavior until a second model is enabled in the registry.

`VA_AGENT_MODEL_PROVIDER` is deprecated in favor of the registry's `enabled`
flags + this policy setting — see the deprecation note in §13.

## 11. Diagnostics endpoints

`app/routers/internal_providers.py`, admin-protected via the existing
`require_admin` dependency (`app/auth/deps.py`) — same pattern as every
other admin-only route in this codebase, no new auth mechanism:

| Endpoint | Returns |
|---|---|
| `GET /internal/providers` | registry entries + `enabled` state |
| `GET /internal/providers/models` | full capability registry (raw) |
| `GET /internal/providers/health` | per-provider aggregates from `provider_call_log` (§8 query) |
| `GET /internal/providers/circuits` | `provider_circuit_state` rows |
| `GET /internal/providers/metrics` | requests/successes/failures/retries/fallbacks/latency/tokens/cost, per provider, bounded window |

All read-only. No endpoint can mutate routing, circuit state, or the
registry — changing those requires editing `capability_registry.py`/
`config.py` and redeploying, consistent with every other "static config,
no admin UI" surface in this codebase (e.g. plan limits, rate limits).

## 12. Sequence diagram

```
Job start (build_orchestrator)
      │
      ▼
agent_definitions.build_X_agent()  ──calls──▶  model_provider.get_model(role)
                                                      │
                                                      ▼
                                    capability_requirements.ROLE_REQUIREMENTS[role]
                                                      │  ProviderRequirements
                                                      ▼
                                          ProviderRouter.select(requirements)
                                             │  filter registry → filter circuits
                                             │  → apply policy → rank
                                             ▼
                                    [ProviderSelection(primary), ProviderSelection(fallback)]
                                                      │
                                                      ▼
                                 model_provider.py builds LiteLlm(primary), LiteLlm(fallback)
                                                      │
                                                      ▼
                                          ReliableLlm(primary, fallback)  ← unchanged
                                                      │
                            (later, during the job) each generate_content_async() call:
                                                      │
                                                      ▼
                                    retries / timeout / schema validation / fallback
                                    execution / metrics emission — exactly as today
                                                      │
                                                      ▼
                          worker.py's on_llm_call sink: llm_calls.append(m)  [existing]
                                                    AND  provider_health.record(m)  [NEW, one line]
                                                      │
                                                      ▼
                              provider_health.record() writes provider_call_log row,
                              circuit_breaker.py evaluates the outcome and updates
                              provider_circuit_state if it changes
```

## 13. Wiring into existing files (the only touches to code that already exists)

- **`model_provider.py`**: `get_model(role)` becomes: look up
  `ROLE_REQUIREMENTS[role]` → `router.select(requirements)` → build
  `LiteLlm` × 2 from the top-2 `ProviderSelection`s → `ReliableLlm(...)`,
  same constructor call as today. `agent_model_provider` setting is
  deprecated (kept as a no-op alias for one release, logged as a
  deprecation warning if set, per this codebase's existing pattern of never
  silently ignoring a configured-but-defunct setting).
- **`worker.py`**: the existing `on_llm_call=llm_calls.append` becomes
  `on_llm_call=lambda m: (llm_calls.append(m), provider_health.record(m))`
  — one line. No other change to job/progress/heartbeat/queue logic.
- **Everything else — `reliable_llm.py`, `orchestrator.py`,
  `agent_definitions.py`, `intake_agent.py`, `human_review_gate.py`,
  `run.py`, the worker's claim/heartbeat/reclaim logic, the queue table,
  the migration history for `agent_analysis_jobs` — is untouched.**

## 14. New file structure

```
backend/app/agents/
  provider_requirements.py      # ProviderRequirements dataclass
  capability_requirements.py    # ROLE_REQUIREMENTS dict
  capability_registry.py        # static ModelSpec list
  provider_selection.py         # ProviderSelection dataclass
  provider_router.py            # ProviderRouter class
  provider_health.py            # record() + aggregate queries against provider_call_log
  circuit_breaker.py            # state machine against provider_circuit_state
  routing_policies.py           # the 5 ranking functions

backend/app/routers/
  internal_providers.py         # 5 read-only admin endpoints

backend/alembic/versions/
  0012_provider_health.py       # provider_call_log + provider_circuit_state
```

## 15. Architecture Decision Records

### ADR-1: `ProviderRequirements` object instead of a bare role string
**Decision:** the router's public API is `select(requirements)`, not
`select(role)`.
**Why:** if the router accepted a role string, it would need to either
duplicate `capability_requirements.py`'s role→capability knowledge
internally, or reach back into `model_provider.py` — both couple the
router to a concept ("agent role") it has no business knowing about. A
`ProviderRequirements` object is the router's actual contract: given a
need, find who can serve it. This also means the router works unmodified
if VariationIQ ever has a non-agent LLM caller.
**Trade-off:** one more dataclass to define — negligible, it's pure data.

### ADR-2: `capability_requirements.py` as flat data, not per-agent classes
**Decision:** `ROLE_REQUIREMENTS: dict[str, ProviderRequirements]`, not
`DocumentAgentProfile`/`ContractAgentProfile`/etc. classes.
**Why:** every "profile" has an identical shape (capabilities, min_context,
requires_json, requires_tools) — this is homogeneous configuration data,
not polymorphic behavior. A class per agent adds a new file/class for
every future agent with zero behavioral gain, and scatters what should be
one at-a-glance table across N files. Moving it out of `model_provider.py`
into its own module *is* worthwhile (keeps that file focused on model
construction, not requirements data) — just as plain data, not classes.
**Trade-off:** none identified; this is strictly less code than the
rejected alternative for the same information.

### ADR-3: no `provider_health_snapshot` table
**Decision:** health/latency/rate aggregates are computed at read time from
`provider_call_log`, not maintained in a continuously-updated snapshot row.
**Why:** at this product's actual volume (rate-limited to 10 analyses/hour
per company, ~7 LLM calls per analysis), an indexed, time-bounded SQL
aggregation resolves in single-digit milliseconds — a snapshot table would
buy no measurable read-performance win. It would cost real things: a second
source of truth that can drift from the log, write amplification on every
call (two writes instead of one), and a sync mechanism (trigger vs. inline
update vs. cron) that's itself a maintenance burden. This is the textbook
shape of premature optimization.
**Revisit when:** call volume grows by orders of magnitude beyond what
today's rate limits allow — at that point, an hourly-bucketed rollup job
(not a synchronously-updated single-row snapshot) is the better next step.

### ADR-4: `ProviderSelection` carries a reasoning string, not four scores
**Decision:** `ProviderSelection.routing_reason: str`, not separate
`health_score`/`latency_score`/`capability_score`/`estimated_cost` fields.
**Why:** not every routing policy computes all four — `highest_priority`
never touches latency or cost. Four named numeric fields that are `None`
under most policies implies a precision the system doesn't have and invites
callers to assume they're always populated. A short human-readable string,
built by whichever policy actually ran, gives the same observability value
(this is exactly the "why did it pick X" question `/internal/providers`
exists to answer) without over-specifying a schema every policy must
partially fake.
**Trade-off:** a string is less machine-parseable than four numeric fields
would be — acceptable, since the fields this decision rejects wouldn't have
been reliably populated anyway.

## 16. Extension guide

**Add a new provider:** add entries to `capability_registry.py` with that
provider's models; add the provider's API key setting to `config.py`
following the existing `nvidia_nim_*_api_key` pattern; no other file
changes needed unless it needs a new litellm custom_llm_provider prefix
(rare — litellm already supports most providers natively).

**Add a new model (existing provider):** one new entry in
`capability_registry.py` — `enabled=True` makes it eligible for routing
immediately, no other changes.

**Add a new capability:** use the new capability string in whichever
`capability_registry.py` model entries actually support it, and in
whichever `capability_requirements.py` role entries need it. No schema
migration — capabilities are just strings in a list.

**Add a new routing policy:** one new function in `routing_policies.py`
matching the standard `(candidates, health) -> list[ProviderSelection]`
signature; add its name as a new valid value for `VA_AGENT_ROUTING_POLICY`.

## 17. Testing strategy

Unit (no DB): capability filtering (matches/excludes correctly on each
requirement field), each routing policy's ranking logic in isolation,
circuit breaker state transitions (closed→open on threshold, open→half-open
after cooldown, half-open→closed on success, half-open→open on failure),
`NoProviderAvailableError` when the candidate list is empty after
filtering, `ProviderRouter.select()` end-to-end with a fake registry/health
source, backward-compatibility check that `highest_priority` with one
enabled model per role reproduces today's exact `(provider, model)` pair.

Integration (real Postgres, skip-if-unavailable — same pattern as
`test_worker_integration.py`): `provider_health.record()` writes a real row
and the bounded aggregation query returns correct numbers; circuit state
persists and is readable cross-"process" (two separate sessions); the 5
diagnostic endpoints return real data end-to-end through a `TestClient`
with an admin user.

## 18. Implementation plan (high-level — detailed plan via writing-plans)

1. `errors.py`: add `NoProviderAvailableError`.
2. `provider_requirements.py`, `provider_selection.py` — the two dataclasses.
3. `capability_registry.py` — static model metadata (seed with today's 3
   NVIDIA NIM models + the openai fallback, all `enabled=True`).
4. `capability_requirements.py` — the 7-role `ROLE_REQUIREMENTS` map.
5. `routing_policies.py` — 5 policy functions, `highest_priority` first
   (it's the default and the backward-compat baseline).
6. `circuit_breaker.py` + migration `0012` (both tables).
7. `provider_health.py` — `record()` + the bounded aggregation queries.
8. `provider_router.py` — ties 3-7 together.
9. `model_provider.py` — rewritten `get_model(role)` per §13.
10. `worker.py` — one-line sink change per §13.
11. `internal_providers.py` router + registration in `main.py`.
12. Tests per §17.
13. Full existing suite re-run for regression (expect zero changes to
    existing test outcomes — this is the backward-compatibility proof).
