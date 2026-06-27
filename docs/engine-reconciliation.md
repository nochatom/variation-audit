# Engine Reconciliation — variation-audit ↔ changeorder-recovery

> Date: 2026-06-27. Cloned the real engine to `C:\Users\EauBr\Projects\changeorder-recovery`
> (private, owner `nochatom`) and compared it against this project's plan
> (architecture `.1`, contract v1.1, `.9` reference). **Outcome: several plan
> assumptions don't hold. Decisions below are required before more build.**

## What the real engine actually is
A **self-contained FastAPI product** (`backend/app/`), not a stateless black box:

- **Pipeline** (`app/ai/`): `ingest` → `baseline` → `classify` → `quantify` → `confidence`, orchestrated by `pipeline.run_recovery(...)`.
  - **INGEST** (`ingest.py`) — *non-LLM* structural normalize → `NormalisedDoc` (id, kind, text, author, occurred_at).
  - **BASELINE** (`baseline.py`) — LLM extracts the **contract** `ScopeBaseline`: inclusions, exclusions, **notice clause**, **time-bar days**, **SoP regime**.
  - **CLASSIFY** (`classify.py`) — LLM finds `flags` (title, rationale, evidence_doc_ids, estimate_low/likely/high, confidence 0–100, **time_bar_risk**).
  - **QUANTIFY** + **CONFIDENCE** — refine $ basis and re-score confidence *deterministically* (`confidence_factors`).
  - `client.py` — `structured_call()`: `claude-opus-4-8`, **streaming**, adaptive thinking, `output_config.effort:"high"` + json_schema, `refusal` handling.
- **Own DB** (`models.py`): `Organisation, User, Project, Contract, ScopeBaselineItem, Document, VariationFlag, EvidenceLink, ClaimPack, AuditEvent`.
- **Own HTTP API** (`main.py`): `POST /api/recovery/run` (**synchronous**, persists), `/api/ingest/*`, `/api/projects`, `/api/flags/{id}/triage` (CA accept/reject), dashboard reads.
- Its own **frontend** (`frontend/`).

## Mismatch 1 — `.9` was misframed (now corrected)
My `engine/app/ai/normalization` reference did per-document LLM scope extraction. That is **not** ingest/baseline — it's closer to CLASSIFY. The real INGEST is non-LLM; the real BASELINE is contract→baseline. **`.9` is already implemented in the real engine.** → The reference module is removed; this project should reference the real engine, not vendor a parallel one.

## Mismatch 2 — the engine is NOT stateless (architecture `.1`)
Architecture `.1` and contract v1.1 assume a **stateless** engine with the **product owning all persistence**. The real engine has full persistence + triage + dashboard that **overlaps** product tasks `.2` (auth/org), `.3` (projects/upload), `.14` (review/triage), `.16` (dashboard), `.17` (audit).
**Salvage:** `pipeline.run_recovery()` itself does **no** persistence (persistence lives in `main.py`/`services.py`). So the stateless-engine model holds **iff** we call `run_recovery(...)` directly and skip the engine's own DB/endpoints. The overlapping product features must be de-duplicated against the engine, not built twice.

## Mismatch 3 — interface: sync + `flags`, not async + `variations`
| | Real engine | Our contract v1.1 |
|---|---|---|
| Call | `POST /api/recovery/run` (sync) | `POST /v1/analyses` → poll (async, 15-min) |
| Output unit | `flag` | `variation` |
| Confidence | int 0–100 + `confidence_factors` | `confidence_score` 0–1 + `confidence_band` |
| $ | `estimate_low/likely/high` + `basis_quality` | `estimated_value{amount, currency, valuation_confidence}` |
| AU SoP | **`time_bar_risk`**, baseline `time_bar_days`/`sop_regime`/`notice_clause` | **no field** |

## Mismatch 4 — v1.1 input can't drive the engine ⚠️
`run_recovery` **requires** `contract_text`, `scope_text`, and `state`. The v1.1 `AnalysisRequest` has only `documents[]`, `project_type`, `country` — **no contract text, no scope/BOQ, no state**. As written, **the engine cannot run from a v1.1 request.**

## flag → variation mapping (for an adapter)
- `title`→`title`; `rationale`→`description`; `status`=`detected`
- `confidence`(0–100) → `confidence_score`=/100 → `confidence_band` (.21.3 map)
- `evidence_doc_ids[]` → `evidence[]` (`source_document_id`=id; `type` from input doc; `quote` not emitted)
- `estimate_likely` → `estimated_value.amount`; `basis_quality` → `valuation_confidence` (boq/rate_card→high, inferred→medium, none→low); **`estimate_low/high` range has no v1.1 home**
- **`time_bar_risk`, baseline (notice/time_bar_days/sop_regime)** — **no v1.1 home** (AU-core value — must not be dropped)
- `variation_id` — engine emits none; adapter/product must mint one

## Recommended path — Adapter + **contract v1.2**
Keep the async product architecture; treat the engine as stateless via `run_recovery(persist=False-equivalent)`:
1. **Contract v1.2** — input adds `contract_text`, `scope_text`, `state`; variation output adds `time_bar_risk` + `estimate_low/high` + a top-level `baseline` (notice clause, time_bar_days, sop_regime). Without this the engine is undrivable and AU SoP value is lost.
2. **Thin engine adapter** — an HTTP shim exposing the v1.2 async job surface (`POST /v1/analyses` + poll) that calls `run_recovery(...)` and maps `flags`→`variations`. This is the engine-side counterpart to the `.21` worker.
3. **De-dup product vs engine** — reconcile `.2/.3/.14/.16/.17` against the engine's existing User/Org/Project/triage/dashboard/audit rather than building twice.

**Alternative path — Adopt the engine's interface**: drop the async v1.1 model, build the product around the engine's sync `/api/recovery/run` + `flags` shape. Less reconciliation, but discards the v1.1 contract + `.21` worker already built.
