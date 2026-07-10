# .26 — Provider Router: Implementation Plan

Companion to `docs/decisions/26-provider-router.md` (the frozen, approved
architecture spec). **This document is planning only — no code has been
written or modified as part of producing it.**

Preserved, untouched by every phase below: the agent graph, Root
Orchestrator, agent definitions, worker execution model, PostgreSQL job
queue, heartbeat system, `ReliableLlm`'s implementation, retry logic,
schema validation, and the existing per-job metrics pipeline
(`AgentAnalysisJob.llm_calls`).

---

## 1. Implementation phases

Ordered so each phase is independently testable and safely mergeable —
nothing in an earlier phase depends on a later one, and the system remains
in its current (pre-router) working state until Phase 4 lands.

**Phase 1 — Data models and registry**
`ProviderRequirements`, `ProviderSelection`, `capability_registry.py`,
`capability_requirements.py`, new (inert) config settings. Pure data, no
selection logic yet, nothing wired to anything that runs today. Fully unit
testable in isolation.

**Phase 2 — Provider Router core (selection logic only)**
`routing_policies.py`, `provider_router.py`. Built against a small
`HealthSource`/`CircuitSource` interface so it can be fully tested with
fakes *before* Phase 3's real persistence exists — decouples "does
selection logic work" from "does the database layer work."

**Phase 3 — Circuit breaker and health tracking (persistence)**
Migration `0012`, `circuit_breaker.py`, `provider_health.py`. Implements
the real `HealthSource`/`CircuitSource` the router will use in production.
Still not wired into any live code path — purely additive tables and a new
module, testable against a real (or skipped) Postgres independent of
everything else.

**Phase 4 — Integration with `ReliableLlm`**
The only phase that changes behavior for real: `model_provider.py`
rewritten to route through the Phase 1–3 components; `worker.py` gets its
one-line metrics-sink addition. This is the cutover point — everything
before it is inert, everything after it is additive-only again.

**Phase 5 — Diagnostics**
`internal_providers.py` router, registered in `main.py`. Read-only,
additive, zero risk to existing behavior — can genuinely be skipped or
delayed without blocking Phase 4's go-live.

**Phase 6 — Testing and regression sign-off**
Full existing suite re-run (expect **zero** changed outcomes — that's the
backward-compatibility proof), plus everything from §6 below.

---

## 2. File-by-file changes

| File | Action | Responsibility | Depends on | Risk |
|---|---|---|---|---|
| `backend/app/agents/errors.py` | Modify | Add `NoProviderAvailableError(AIProviderError)` | — | **Low** — pure addition, no existing code path touches it |
| `backend/app/agents/provider_requirements.py` | Create | `ProviderRequirements` frozen dataclass | — | **Low** — new file, no consumers yet |
| `backend/app/agents/provider_selection.py` | Create | `ProviderSelection` frozen dataclass | — | **Low** |
| `backend/app/agents/capability_registry.py` | Create | Static `ModelSpec` list (today's 3 NVIDIA NIM models + openai fallback, all `enabled=True`) | — | **Low** |
| `backend/app/agents/capability_requirements.py` | Create | `ROLE_REQUIREMENTS` dict (7 roles) | `provider_requirements.py` | **Low** |
| `backend/app/config.py` | Modify | Add `agent_routing_policy` (default `"highest_priority"`), circuit breaker `failure_threshold`/`cooldown_s`; deprecate `agent_model_provider` (log warning if set, don't remove the field yet) | — | **Low** — additive settings; deprecation is a warning, not a break |
| `backend/app/agents/routing_policies.py` | Create | 5 ranking functions, each `(candidates, health) -> list[ProviderSelection]` | `provider_selection.py`, `capability_registry.py` | **Low** |
| `backend/app/agents/provider_router.py` | Create | `ProviderRouter.select(requirements)`; accepts injectable health/circuit sources | `provider_requirements.py`, `provider_selection.py`, `routing_policies.py`, `capability_registry.py`, `errors.py` | **Medium** — the core selection algorithm; bugs here affect which model every agent gets, though nothing calls it yet at this phase |
| `backend/alembic/versions/0012_provider_health.py` | Create (migrate) | `provider_call_log` + `provider_circuit_state` tables | Existing migration chain (`0011_agent_job_observability`) | **Medium** — schema change, but purely additive new tables, no existing table touched |
| `backend/app/agents/circuit_breaker.py` | Create | State machine over `provider_circuit_state` | migration `0012`, `errors.py` (for the trip/no-trip classification) | **Low** — new file, isolated table |
| `backend/app/agents/provider_health.py` | Create | `record()` + bounded read-time aggregation queries over `provider_call_log` | migration `0012` | **Low** |
| `backend/app/agents/model_provider.py` | Modify (rewrite `get_model`) | Role → requirements → router → build 2 `LiteLlm` → `ReliableLlm` (same constructor as today) | Everything from Phases 1–3 | **High** — every single agent's model construction goes through this function; a regression here breaks the whole agent pipeline, not just the router feature. Gets the most test coverage and the explicit backward-compat check (§6). |
| `backend/app/agents/worker.py` | Modify (one line) | `on_llm_call` sink also calls `provider_health.record(m)` | `provider_health.py` | **Low** — additive to an existing lambda; no change to job/progress/heartbeat/queue logic |
| `backend/app/routers/internal_providers.py` | Create | 5 read-only admin endpoints | `provider_health.py`, `circuit_breaker.py`, `capability_registry.py`, existing `require_admin` dep | **Low** — new, read-only, admin-gated |
| `backend/app/main.py` | Modify | Register `internal_providers` router | — | **Low** — one `include_router` line, same pattern as every existing router |

No file outside `backend/app/agents/`, `backend/app/routers/`,
`backend/app/config.py`, `backend/app/main.py`, and `backend/alembic/` is
touched. `reliable_llm.py`, `orchestrator.py`, `agent_definitions.py`,
`intake_agent.py`, `human_review_gate.py`, `run.py`, `jobs.py`, and every
file under `backend/app/worker/` (the production engine-pipeline worker,
a different system entirely) are **not in this change list at all.**

---

## 3. Database changes

One migration, additive only, two new tables, no changes to any existing
table (including `agent_analysis_jobs`).

### `provider_call_log` (append-only)

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` | |
| `provider` | `text NOT NULL` | |
| `model` | `text NOT NULL` | |
| `selection_id` | `uuid` | ties back to the `ProviderSelection` that led here; no FK constraint (selections aren't persisted as their own rows — see note below) |
| `success` | `boolean NOT NULL` | |
| `error_code` | `text` | `AI_AUTH_ERROR` / `AI_RATE_LIMIT_ERROR` / etc. when `success = false` |
| `latency_ms` | `integer` | |
| `input_tokens` | `integer` | |
| `output_tokens` | `integer` | |
| `created_at` | `timestamptz NOT NULL DEFAULT now()` | |

**Index:** `(provider, created_at)` — supports every bounded, per-provider
aggregation query in `provider_health.py`.

**Relationships:** none enforced at the DB level. `selection_id` is
carried for traceability/log-correlation only — `ProviderSelection`
objects are transient (constructed per agent, per job) and are not
persisted as their own table row, so there's nothing to foreign-key
against. This is a deliberate scope decision: persisting every selection
decision as its own row would be a second append-only log for no query
this design currently needs.

### `provider_circuit_state` (one mutable row per provider)

| Column | Type | Notes |
|---|---|---|
| `provider` | `text PRIMARY KEY` | |
| `state` | `text NOT NULL DEFAULT 'closed'` | `closed` \| `open` \| `half_open` |
| `failure_count` | `integer NOT NULL DEFAULT 0` | |
| `opened_at` | `timestamptz` | |
| `last_success` | `timestamptz` | |
| `last_failure` | `timestamptz` | |

**Relationships:** none — `provider` is a free-text key matching
`capability_registry.py` entries' `provider` field, not a foreign key
(the registry is static Python data, not a DB table, so there is nothing
to reference).

**Migration order:** single migration, `0012_provider_health.py`, both
`CREATE TABLE`s in one file (they have no dependency on each other, but
splitting them into two migrations would add nothing but ceremony).
Follows `0011_agent_job_observability` in the existing chain, same
`IF NOT EXISTS` convention as every migration since `0002`.

**Confirmed: no `provider_health_snapshot` table** (ADR-3, ratified in the
architecture spec) — all aggregates are computed at read time from
`provider_call_log`.

---

## 4. Data flow

```
Job start (build_orchestrator, unchanged)
      │
      ▼
agent_definitions.build_X_agent()  (unchanged)
      │  calls model_provider.get_model(role)
      ▼
capability_requirements.ROLE_REQUIREMENTS[role]
      │  ProviderRequirements
      ▼
ProviderRouter.select(requirements)
      │  filter capability_registry by capability/context/json/tools/enabled
      │  → filter out providers with circuit_breaker state = OPEN
      │  → rank survivors via the configured routing_policies function
      ▼
[ProviderSelection(primary), ProviderSelection(fallback)]
      │
      ▼
model_provider.py builds LiteLlm(primary), LiteLlm(fallback)
      │
      ▼
ReliableLlm(primary, fallback)   ← constructed exactly as today, UNCHANGED
      │
      │  (later, during the job — every generate_content_async() call)
      ▼
retries / timeout / schema validation / fallback execution / structured
logging / per-job metrics emission — all exactly as today, ZERO changes
      │
      ▼
worker.py's on_llm_call sink:
    llm_calls.append(m)          [existing — feeds AgentAnalysisJob.llm_calls]
    provider_health.record(m)    [NEW — one line]
      │
      ▼
provider_health.record(m):
    INSERT INTO provider_call_log (...)
      │
      ▼
circuit_breaker.py evaluates the outcome (via errors.py's existing
AIProviderError classification — no new classification logic):
    - AIProviderTimeoutError / AIProviderUnavailableError → may trip OPEN
    - AIAuthError / AISchemaValidationError / AIRateLimitError → never trips
    - updates provider_circuit_state if the state changes
```

**Where metrics are recorded:** exclusively in `provider_health.record()`,
called from the one line added to `worker.py`'s existing sink — never
inside `reliable_llm.py`, which continues to only know about its existing
`on_llm_call` callback contract.

**Where circuit state updates happen:** inside `circuit_breaker.py`,
triggered by the same `record()` call (health recording and circuit
evaluation happen together, from the same metrics dict, in the same
`worker.py`-owned call site — not two separate hooks into two separate
places).

**Where health information is consumed:** by `ProviderRouter.select()` (via
its injected `HealthSource`) at the *start* of each job, when agents are
constructed — and by the `/internal/providers/*` diagnostics endpoints
(read-only, on demand, via the same bounded aggregation queries).

---

## 5. Integration points

### `model_provider.py`
`get_model(role)` is rewritten internally; **its signature and return type
do not change** (still returns something `LlmAgent.model` accepts — a
`BaseLlm`, since `ReliableLlm` already satisfies that interface). Internally:
```
requirements = ROLE_REQUIREMENTS[role]
selections = ProviderRouter().select(requirements)
primary = _build_litellm(selections[0])
fallback = _build_litellm(selections[1]) if len(selections) > 1 else None
return ReliableLlm(primary=primary, primary_provider=selections[0].provider,
                    fallback=fallback, fallback_provider=selections[1].provider if fallback else None)
```
This is the same `ReliableLlm(...)` constructor call already in
production — only where `primary`/`fallback` come from changes.

### `worker.py`
The existing line in `_process_job_async`:
```python
on_llm_call=llm_calls.append,
```
becomes:
```python
on_llm_call=lambda m: (llm_calls.append(m), provider_health.record(m)),
```
No other line in `worker.py` changes. Heartbeat, progress/ETA, claim,
reclaim, and job persistence logic are untouched.

### `internal_providers.py` (new)
Standard FastAPI router, `require_admin` dependency on every route (same
pattern as every other admin-only endpoint in this codebase — no new auth
mechanism introduced). Registered in `main.py` with one `include_router`
call, same as every other router.

### Confirmation
**`reliable_llm.py` is not modified in any phase of this plan.** It
receives the same `LiteLlm` primary/fallback pair shape it receives today;
it has no awareness that a router now chose them.

---

## 6. Testing strategy

| Area | Test(s) |
|---|---|
| `ProviderRequirements` resolution | Every role in `ROLE_REQUIREMENTS` resolves to a valid, non-empty `ProviderRequirements`; unknown role raises a clear error |
| Capability filtering | Registry entries missing a required capability are excluded; `min_context` below requirement excluded; `requires_json`/`requires_tools` mismatches excluded; `enabled=False` always excluded |
| Routing policies | Each of the 5 policies ranks a fixed fake candidate set correctly in isolation, independent of the router |
| Provider ranking (router) | `ProviderRouter.select()` end-to-end against a fake `HealthSource`/`CircuitSource`: correct top-2 ordering, correct `routing_reason` content, tiebreak randomization doesn't crash with equal-ranked candidates |
| Circuit breaker transitions | CLOSED→OPEN at the failure threshold; OPEN→HALF_OPEN after cooldown; HALF_OPEN→CLOSED on success; HALF_OPEN→OPEN on failure (cooldown resets) |
| 429 behavior | `AIRateLimitError` outcomes recorded in `provider_call_log`, visible in health aggregates, **do not** change `provider_circuit_state` |
| 401/403 behavior | `AIAuthError` outcomes recorded, **do not** trip the circuit, recorded correctly with `error_code` |
| Timeout handling | `AIProviderTimeoutError` outcomes count toward the failure threshold and can trip the circuit |
| Provider unavailable | All candidates excluded (all circuits open, or none match capabilities) → `NoProviderAvailableError` raised, not a confusing downstream crash |
| Diagnostics endpoints | Each of the 5 endpoints returns correct real data (integration, real Postgres); non-admin user gets 403; no endpoint accepts a mutating verb |
| Backward compatibility | With `agent_routing_policy="highest_priority"` and exactly one `enabled=True` model per role (today's real registry seed), `model_provider.get_model(role)` selects the *identical* `(provider, model)` pair `ReliableLlm` receives today for every one of the 7 roles — this is the core regression proof, run against the actual current registry seed data, not a synthetic fixture |

Unit tests (no DB) cover everything except the circuit-state persistence
and diagnostics-endpoint rows, which need real Postgres — those follow the
existing `test_worker_integration.py` pattern: skip cleanly if no DB is
configured, run for real otherwise.

Full existing suite re-run at the end of Phase 6, expecting **zero**
changes to existing test outcomes.

---

## 7. Deployment strategy

**Migration order:** `0012_provider_health.py` can be applied any time
after `0011` — it creates two new, empty tables with no data dependency on
anything. Safe to run ahead of the Phase 4 code deploy (the tables simply
sit unused until `provider_health.record()` starts writing to them).

**Feature flag:** not needed as a separate mechanism — `agent_routing_policy
= "highest_priority"` with the registry seeded to exactly one
`enabled=True` model per role *is* the flag: it reproduces today's exact
static behavior. Going live is: deploy Phases 1–3 (fully inert), deploy
Phase 4 (cutover — but behaviorally identical output because of the
seed), then optionally enable a second model or switch the policy
afterward as a separate, deliberate change once the diagnostics endpoints
(Phase 5) are available to observe the effect.

**Rollback plan:** Phase 4 is the only behavior-changing deploy. Rolling it
back is a plain code revert of `model_provider.py` and `worker.py` to their
pre-Phase-4 versions — no data migration to undo, since `provider_call_log`/
`provider_circuit_state` are additive and harmless to leave in place
(nothing reads them if `provider_health.record()` isn't being called).
There is no scenario in this plan that requires a destructive rollback
(dropping tables, reverting agent output shape, etc.).

**Safe deployment sequencing:**
1. Ship Phases 1–3 (inert; full test suite green; nothing in production
   changes because nothing calls this code yet).
2. Apply migration `0012`.
3. Ship Phase 4 with the registry seeded 1:1 with today's static config —
   verify via the backward-compatibility test (§6) *before* this deploys,
   not after.
4. Ship Phase 5 (diagnostics) — observe real health/circuit data
   accumulate.
5. Only after step 4 gives real signal: consider enabling a second model
   or a non-default routing policy, as its own separate, reviewable change.

---

## 8. Risks

**Technical**
- `model_provider.py`'s rewrite is the single highest-risk file (§2) —
  mitigated by the explicit backward-compatibility test being a hard gate
  before Phase 4 ships, not an afterthought.
- Circuit breaker false-positives (tripping on a genuinely transient blip)
  would reduce effective provider diversity — mitigated by the threshold
  (5 consecutive failures) and cooldown (60s) defaults being conservative,
  and both being config-adjustable without a code change if real data
  shows they need tuning.

**Migration**
- Low — both new tables are additive with no foreign keys into existing
  tables and no backfill requirement. The only real migration risk
  (locking an existing table) doesn't apply here.

**Performance**
- Read-time aggregation from `provider_call_log` (ADR-3) is the plan's
  deliberate bet that current call volume doesn't need a snapshot table —
  correct at today's scale (§8 of the design spec), but if a routing
  decision is ever made *synchronously in the request path* at much higher
  frequency than "once per agent per job," this assumption should be
  re-checked. It is not re-checked as part of this plan because current
  volume doesn't warrant it.
- `provider_health.record()` adds one extra DB write per LLM call (in
  addition to the existing `llm_calls.append()`, which was already
  in-memory-only until job completion). This is a new per-call write that
  didn't exist before — acceptable at current volume, worth watching if
  call volume grows significantly.

**Operational**
- A misconfigured `agent_routing_policy` (typo, unsupported value) should
  fail loudly at `ProviderRouter` construction/first call, not silently
  fall back to a default — this needs to be an explicit validation in
  Phase 2, called out here so it isn't missed during implementation.
- The `agent_model_provider` deprecation warning (Phase 4) must actually be
  visible in logs someone monitors — otherwise it deprecates silently and
  nobody notices before the setting is eventually removed in a future pass.
