# De-dup: Product vs Engine Overlapping Features (.26)

> Date: 2026-06-27. Decides, per overlapping product task, whether to **build** in
> the product, **reuse** engine code, or **port** engine design — given the chosen
> architecture (stateless engine via the v1.2 adapter; **product owns persistence,
> auth, multi-tenancy, UI**). Source: the cloned `changeorder-recovery` engine.

## Headline finding
The overlap is **shallower than the reconciliation first implied**, for two reasons:
1. **The engine has no auth.** It has bare `User`/`Organisation` *models* (User has `email`, `name`, `role` ∈ `ca|viewer` — **no password/login/session/JWT**) and a `_default_org` single-tenant placeholder. Auth is greenfield.
2. The engine's `Project`/`VariationFlag`/`AuditEvent`/triage/dashboard are bound to the engine's **own lightweight DB** (string IDs, single-tenant), which our architecture **bypasses** (product owns persistence). So they can't be reused as runtime — only their **design** ports.

⇒ **No product task is dropped.** The real win is avoiding reinvention of three concrete assets (`parsing`, the dashboard payload, the frontend scaffold) and porting triage/audit semantics + the "data moat" idea.

## Per-task verdict
| Task | Engine has | Verdict | Action |
|------|-----------|---------|--------|
| **`.2` Auth & org** | Models only, **no auth code** | **BUILD (greenfield)** | Build product auth + multi-tenant orgs on the v1.2 Postgres schema. Nothing to reuse. The engine's `role` (`ca|viewer`) informs the product role set (vs our `admin|member`). |
| **`.3` Project + upload** | `parsing.extract_text` (PDF/text), `parsing.parse_comms_csv`; ingestion endpoints | **HYBRID — REUSE parsing** | Product owns Project CRUD + S3 storage (already in schema). **Reuse `backend/app/parsing.py`** for document/CSV extraction instead of rebuilding it. |
| **`.14` Commercial review/triage** | `/api/flags/{id}/triage` (accept/edit/reject), `FlagStatus`, `_audit`, the "CA decision = labelled outcome / data moat" concept | **BUILD — PORT design** | Product implements triage over **its own** `variations.review_status` + `audit_log` (engine DB is bypassed). Port the accept/edit/reject + audit semantics, and carry the **data-moat** idea (CA outcomes are the defensible asset) into the product. |
| **`.16` Dashboard & UI** | `project_summary` payload, `list_flags` (ordered by confidence), **Next.js 14 + Tailwind** `frontend/` scaffold | **HYBRID — REUSE scaffold + payload shape** | Build the dashboard over the **product** DB, but **reuse the engine `frontend/` scaffold** (same stack as the product's chosen frontend) and the `recovery-summary` payload shape (`flagged_total`, `recoverable_total`, `flag_count`, `time_bar_at_risk` — all now on the product side via the v1.2 job rollups). |
| **`.17` Audit trail** | `AuditEvent` model + `_audit()` helper | **BUILD — PORT pattern** | Product already has the `audit_log` table; port the pattern that **every triage decision emits an audit event**. |
| **`.18` Notifications/jobs** | — (engine is synchronous) | **BUILD** | No engine overlap; product's worker + queue (already built in `.21`) owns this. |

## Net effect on the backlog
- **Keep & build:** `.2`, `.14`, `.17` (engine offers design only, no reusable runtime).
- **Hybrid (reuse concrete engine code):** `.3` (reuse `parsing.py`), `.16` (reuse `frontend/` scaffold + payload shape).
- **Already covered elsewhere:** `.18` by the `.21` worker.
- The engine's standalone product mode (its own auth-less DB, triage, dashboard, frontend) is **not** wired into the product runtime — it remains the engine's own thing; we consume the engine only through the v1.2 adapter (`run_recovery`).

## Follow-ups worth tracking
- Decide the product **role model** (`admin|member` vs the engine's `ca|viewer`) during `.2`.
- When starting `.3`, vendor or import `parsing.py` (PDF via the engine's `_pdf_text`).
- When starting `.16`, fork the engine `frontend/` as the product UI starting point.
