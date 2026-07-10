# .26 — Provider Router: policy-driven, health-aware model selection

**Status: FINAL — architecture review complete, approved for
implementation.** Not yet implemented (no code changes in this document).

Scope: `backend/app/agents/` (+ one new admin router) only. Additive
infrastructure — no change to the agent graph, orchestrator, worker, queue,
heartbeat, or `ReliableLlm`'s execution responsibilities. Explicitly out of
scope for this work: `app/models.py`, `app/services/billing.py`, and any
other large-file refactor flagged during the earlier tooling pass — those
are separate, unrelated future architecture tasks and are not touched by
anything in this document.

### Approved / rejected, for the record

**Approved:**
- `ProviderRequirements` abstraction (§4)
- `capability_requirements.py` as static configuration data (§5)
- `ProviderRouter.select(requirements)` (§7)
- `ProviderSelection` metadata object: `provider`, `model`, `routing_reason`,
  `policy`, `selection_id`, `selected_at` (§6)
- `provider_call_log` aggregation (read-time, indexed, bounded) as the
  source of truth for health/latency/rate metrics (§8)
- DB-backed circuit state (`provider_circuit_state`), readable cross-process
  by the API's diagnostic endpoints (§8, §9)
- HTTP 429 explicitly excluded from tripping the circuit breaker (§9) —
  confirmed, no longer just a flagged judgment call (see Change 1 below)

**Rejected:**
- `provider_health_snapshot` table (ADR-3) — read-time aggregation instead
- Class-per-agent capability profiles (ADR-2) — flat dict instead
- Replacing `ReliableLlm` — it is unmodified; only its inputs become dynamic
- Moving execution responsibilities into `ProviderRouter` — selection only,
  never execution, retries, fallback, parsing, or metrics (§3, §7)

This full list is repeated, with rationale, in §20 (Final review — decision
summary) at the end of this document.

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
| `capability_registry.py` | static model metadata (provider, model, capabilities, context, flags, priority, enabled, price_per_1k_tokens) | dynamic health, selection logic |
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
already produced today (§13 wiring), just also persisted per-provider
instead of only per-job.

### Cost model: static price vs. dynamic actuals — explicit separation

**Static Capability Registry** (`capability_registry.py`) holds
configuration metadata only: `provider`, `model_name`, `capabilities`,
`max_context`, `supports_json`, `supports_streaming`, `supports_reasoning`,
`supports_tools`, `priority`, `enabled`, `tags`, and `price_per_1k_tokens`.
**`price_per_1k_tokens` is configuration metadata, not runtime health
data** — it's a price list entry, unrelated to whether the provider is
currently healthy, and it never changes based on observed behavior. It is
used *only* for cost estimation math, never for capability matching or
filtering.

**Runtime Provider Health** (`provider_health.py`, backed by
`provider_call_log`) holds everything that's actually observed: real input
tokens, real output tokens, real latency, success rate, failure rate,
retry count, fallback count, and observed cost aggregates.

**Actual cost is always `real token usage logs × static model pricing
metadata`** — `provider_health.py` computes the `estimated_cost_per_token`
(and any windowed total-cost aggregate) by multiplying logged
`input_tokens`/`output_tokens` from `provider_call_log` by the matching
model's static `price_per_1k_tokens` from the registry, over the query
window. The rate is static; the resulting aggregate is dynamic. Neither
table duplicates the other's data — the registry never stores an observed
number, and the health layer never stores a price.

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

**Trips on:** `AIProviderTimeoutError`, `AIProviderUnavailableError`
(covers connection failures and HTTP 503 — both already classified into
`AIProviderUnavailableError` by `errors.py`'s existing `classify_exception`).

**Never trips on:** `AIAuthError` (401/403 — a config problem, not an
infrastructure one; retrying/routing around it fixes nothing),
`AISchemaValidationError` (a model-output-quality problem, not a
reachability one), and any other application-level error (invalid
prompts, etc.) — none of these indicate the provider is unreachable, so
none of them should remove it from rotation.

### HTTP 429 (rate limit) — explicit handling

**429 MUST NOT trip the circuit breaker.** A 429 means the provider is
reachable, healthy, and working — the caller simply exceeded its current
request allowance. That is not an infrastructure availability failure, and
treating it as one would pull a perfectly healthy provider out of rotation
over something `ReliableLlm` already handles correctly on its own.

```
HTTP 429 Rate Limit
      │
      ├──▶ Retry with exponential backoff        (ReliableLlm — unchanged, existing)
      │
      ├──▶ Recorded in provider_call_log          (success=false, error_code=AI_RATE_LIMIT_ERROR)
      │
      ├──▶ Visible in provider health metrics     (§8's read-time aggregation includes it
      │                                             in failure_rate/retry_rate like any other
      │                                             logged outcome — no special-casing needed,
      │                                             since it's just a row with an error_code)
      │
      └──▶ Circuit breaker: NOT evaluated          (AIRateLimitError is simply absent from the
                                                     "trips on" list above — no code path treats
                                                     it as a circuit-relevant outcome)
```

429s remain fully queryable for diagnostics (`/internal/providers/metrics`,
§11) and available as an input to routing policies (e.g. a future policy
could deprioritize a provider with a high recent 429 rate without ever
opening its circuit — see §10's `lowest_cost` note on retry/fallback
overhead) — being excluded from circuit-tripping doesn't mean the data is
discarded, only that it doesn't independently gate availability.

### Defaults

Configurable in `config.py`, matching this project's existing
`rate_limit_*`-style settings pattern: failure threshold 5, cooldown 60s.

### Not to be confused with: the Availability Cache (Phase 4, `model_provider.py`)

Phase 4's implementation added a second, much smaller mechanism that
**must not be conflated with the Circuit Breaker above** — they solve
different problems and were built for different reasons:

| | Circuit Breaker (`circuit_breaker.py`) | Availability Cache (`model_provider.py`) |
|---|---|---|
| Protects against | An unhealthy **LLM provider** | An unreachable **health/circuit database** |
| Tracks | Provider call failures (timeout, unavailable) | Nothing about providers — no concept of "provider health" |
| Storage | `provider_circuit_state`, Postgres-persisted, cross-process | A single in-process module-level timestamp, reset on restart |
| Governs | Whether `ProviderRouter` actually excludes a provider from selection | Whether this process even *attempts* a fresh DB read for a few seconds |
| Trips because | A provider genuinely failed calls | The telemetry DB connection was unreachable/slow — unrelated to any provider's health |
| Effect on `provider_circuit_state` | Is the thing that updates it | **None whatsoever** |

In short: the Circuit Breaker answers "is this LLM provider healthy?" The
Availability Cache answers "can this process currently reach the database
that would tell me?" — and when the answer is no, it **fails open**
(assumes healthy/closed) so a health/circuit database outage degrades
gracefully — see `_ResilientHealthSource`/`_ResilientCircuitSource` — rather
than blocking or crashing agent construction. It exists solely to preserve
agent startup and execution during an observability-infrastructure failure;
it never makes a provider-health decision and never touches
`provider_circuit_state`. See ADR-5.

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

### `lowest_cost`, scoped for the initial implementation

A cost-aware policy that only looked at static `price_per_1k_tokens` would
be misleading: a cheap-per-token model that retries constantly or falls
back often can end up *more* expensive per successful analysis than a
pricier model that rarely fails. The complete picture is static price
combined with observed token usage, retry overhead, fallback frequency, and
provider reliability.

**The initial implementation deliberately does not build all of that.** It
ranks by: static `price_per_1k_tokens` × recent observed average token
usage from `provider_health` where available (falling back to
registry price alone if a provider has no call history yet — a new or
rarely-used model shouldn't be unrankable just because
`provider_call_log` has no rows for it). Retry overhead, fallback
frequency, and a reliability-weighted cost score are **explicitly deferred
— documented here as a future enhancement, not built now.** Doing so before
there's real usage data to validate against would be tuning a formula
against numbers nobody has observed yet — the same shape of premature
optimization ADR-3 already rejected for the health-snapshot table.

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

### ADR-5: the Availability Cache is a separate mechanism from the Circuit Breaker
**Decision:** the 30-second in-process TTL added in Phase 4
(`model_provider.py`'s `_AVAILABILITY_CACHE_TTL_S` /
`_telemetry_db_marked_down()` / `_mark_telemetry_db_down()`) is named and
documented as an **Availability Cache**, explicitly distinct from — and
never described as part of — the Circuit Breaker (`circuit_breaker.py`,
§9). It never reads or writes `provider_circuit_state`.
**Why:** Phase 4 discovered that wiring `ProviderRouter`'s DB-backed
health/circuit sources into `get_model()` meant every agent construction
now needed a live database connection — a property the scaffold never had
before, and a real regression when that database is slow or unreachable
(observed live: 2+ minutes per orchestrator build against a stalled local
Postgres, since one construction reads health/circuit data up to twice per
role across 7 roles). The fix needed two parts: (1) fail fast rather than
wait out a multi-driver-default connect timeout, and (2) don't repeat that
fast-fail attempt on every one of those ~14 reads once the database is
known to be down. Both are about *this process's ability to reach a
database*, not about *any LLM provider's health* — conflating them into
"the circuit breaker" would misrepresent what actually trips it (a DB
outage, not a provider failure) and what it protects (agent construction
continuing to work, not routing away from a bad provider).
**Trade-off:** a provider whose circuit is *genuinely* open won't be
correctly excluded for up to the cache's 30-second window if a DB blip
happens to coincide with that check — acceptable, since the alternative
(no cache) is agent construction blocking for minutes on a routine
telemetry hiccup, which is a worse failure mode than routing to a
still-degraded provider for a few extra seconds (`ReliableLlm`'s own
retry/fallback layer remains the backstop either way, unchanged).

## 16. Provider onboarding guide

Steps to add a **new provider** (e.g. a future Anthropic-direct or OpenAI-
direct integration, not routed through NVIDIA NIM):

1. Confirm litellm has native support for the provider (check
   `litellm.provider_list`) — almost always yes; if not, it needs a
   `custom_llm_provider` registration, which is rare and out of scope for a
   routine onboarding.
2. Add the provider's API key setting to `config.py`, following the
   existing `nvidia_nim_*_api_key` / `anthropic_agent_api_key` naming
   pattern (one `Settings` field, `str | None = None`, "unset → not
   configured" — never a hard failure at import time).
3. Add one `capability_registry.py` entry per model that provider offers
   (see §17, Model onboarding, for the entry shape itself).
4. No changes to `provider_router.py`, `routing_policies.py`,
   `circuit_breaker.py`, or `provider_health.py` — all of them operate
   generically over whatever's in the registry and `provider_call_log`;
   a new provider is just new rows/data, not new code paths.
5. No changes to `model_provider.py`, `agent_definitions.py`, or the
   orchestrator — the whole point of this layer.

## 17. Model onboarding guide

Steps to add a **new model** (existing or new provider):

1. Add one entry to `capability_registry.py`:
   ```python
   ModelSpec(
       provider="nvidia_nim", model_name="z-ai/glm-6.0",
       supported_capabilities=["structured_json", "summarization", "fast_response"],
       max_context=64000, supports_json=True, supports_streaming=True,
       supports_reasoning=False, supports_tools=False,
       priority=8, enabled=True, tags=["general_purpose"],
       price_per_1k_tokens=0.0004,
   )
   ```
2. Set `enabled=True` when it's ready to receive traffic — that's the only
   switch; there is no admin UI toggle (§11 is read-only by design), so
   flipping this requires a code change + deploy, same as any other static
   config in this codebase (plan limits, rate limits).
3. If it should be preferred over what's currently selected for some role,
   either raise its `priority` (for `highest_priority` policy) or trust the
   `lowest_latency`/`lowest_cost` policies to pick it up once
   `provider_call_log` has enough real data for that provider.
4. No new capability string is required unless the model does something
   genuinely new — reuse existing capability tags (`legal_reasoning`,
   `contract_analysis`, `structured_json`, etc.) wherever they already
   describe what the model can do.

**Add a new capability** (only needed when a model does something no
existing tag captures): use the new string in whichever
`capability_registry.py` model entries actually support it, and in
whichever `capability_requirements.py` role entries need it. No schema
migration — capabilities are just strings in a list, not an enum.

**Add a new routing policy:** one new function in `routing_policies.py`
matching the standard `(candidates, health) -> list[ProviderSelection]`
signature; add its name as a new valid value for `VA_AGENT_ROUTING_POLICY`.

## 18. Testing strategy

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

## 19. Implementation plan (high-level — detailed plan via writing-plans)

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
12. Tests per §18.
13. Full existing suite re-run for regression (expect zero changes to
    existing test outcomes — this is the backward-compatibility proof).

## 20. Final review — decision summary

**Approved:**
- `ProviderRequirements` abstraction (§4)
- `capability_requirements.py` as static configuration data (§5)
- `ProviderRouter.select(requirements)` (§7)
- `ProviderSelection` metadata object (§6)
- `provider_call_log` aggregation — read-time, indexed, bounded window,
  no snapshot table (§8)
- DB-backed circuit state (`provider_circuit_state`), readable cross-process
  (§8, §9)
- HTTP 429 explicitly excluded from tripping the circuit breaker (§9) —
  retried by `ReliableLlm`, logged to `provider_call_log`, visible in
  health metrics and diagnostics, available to future routing decisions

**Rejected:**
- `provider_health_snapshot` table (ADR-3)
- Class-per-agent capability profiles (ADR-2)
- Replacing `ReliableLlm`
- Moving execution logic (retries, fallback execution, schema validation,
  parsing, metrics collection) into `ProviderRouter`

**Deferred (documented, not built now):**
- `lowest_cost` policy's full reliability-weighted formula (retry overhead,
  fallback frequency as first-class inputs) — §10. Initial version uses
  static price × observed average token usage only.
- Hourly-bucketed health rollups — only if call volume grows by orders of
  magnitude beyond current rate limits (ADR-3's revisit condition).

### Open questions

None outstanding. The one previously-flagged judgment call (429 vs. the
circuit breaker) is now an explicit, approved requirement rather than an
assumption — Change 1 in this revision formalizes exactly the behavior
already implemented in §9's design, so no design change to any component
was needed there, only clearer documentation of the rule and its
visibility guarantees.

No other ambiguity was identified while applying Changes 1–3. The document
is implementation-ready as it stands; the next step remains `writing-plans`
for a detailed implementation plan, per the brainstorming process.

### Phase 4 addendum

**Approved (added during implementation, documented after the fact):**
- The **Availability Cache** (`model_provider.py`, ADR-5, §9's "Not to be
  confused with" subsection) — a 30-second in-process TTL discovered to be
  necessary once Phase 4 actually wired live DB-backed health/circuit
  sources into `get_model()`. Explicitly **not** part of the Circuit
  Breaker: it protects agent construction from a health/circuit *database*
  outage, tracks nothing about provider health, never reads or writes
  `provider_circuit_state`, and fails open. No production behavior beyond
  what Phase 4's gates already required — this addendum is a naming/
  documentation clarification, not a new decision to approve or reject.
