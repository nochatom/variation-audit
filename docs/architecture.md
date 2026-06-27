# Architecture & System Design (MVP)

> Task: `variation-audit-z3x.1` · Status: **accepted** (2026-06-27, founder-approved). Decisions locked in §9.
> Scope: **Australia only**, all construction trades. Hybrid build — reuse the `changeorder-recovery` AI engine, build a new Beads-orchestrated product layer on top. Interface = [Engine↔Product API Contract v1.1](engine-product-api-contract-v1.1.md).

## 1. Goals & Constraints
- Help AU contractors find **unclaimed variations** in completed/in-progress projects from messy comms (email, RFI, site instructions, meeting notes, SMS, documents).
- **Reuse** the validated detection engine; do not rebuild inference.
- Long-running analysis → **async job model** (15-min cap, polling-only) per contract v1.1.
- Solo, non-industry founder → favour **operational simplicity** over premature scale.
- **Data residency: AU** (Sydney region) — sensitive project comms.
- Human-in-the-loop: nothing is auto-submitted; the commercial team confirms variations.

## 2. Architecture Style
**Modular monolith (product) + separate engine service.** Two deployables, talking over the v1.1 HTTP contract:

1. **Product service** — modular monolith (FastAPI): auth, orgs, projects, ingestion intake, review workflow, reporting, dashboard, **and the background worker** that drives the engine.
2. **Engine service** — the reused `changeorder-recovery` codebase, exposed behind the v1.1 contract as a black box.

Rationale: one founder, one product codebase to reason about; the engine is already a distinct codebase with its own DB and model logic, so keeping it as an internal service preserves the clean reuse boundary without microservice sprawl.

## 3. Components
```
┌─────────────┐    HTTPS     ┌──────────────────────────────┐
│  Web App    │ ───────────► │      Product Service (API)    │
│ Next.js 14  │ ◄─────────── │  FastAPI · SQLAlchemy         │
│ + Tailwind  │   JSON       │  auth · orgs · projects ·     │
└─────────────┘              │  ingestion · review · reports │
                             └───────┬───────────────┬───────┘
                                     │ enqueue        │ SQL
                             ┌───────▼───────┐ ┌──────▼───────┐
                             │  Job Worker   │ │  Postgres    │  product DB
                             │ (same code,   │ │  (multi-     │
                             │  worker mode) │ │   tenant)    │
                             └───┬───────────┘ └──────────────┘
                                 │ v1.1 contract (POST + poll)
                                 ▼
                         ┌───────────────┐    ┌──────────────┐
                         │ Engine Service│───►│ Anthropic    │ claude-opus-4-8
                         │ (reused C-O-R)│    │ structured   │
                         │ FastAPI       │    │ outputs      │
                         └───┬───────────┘    └──────────────┘
                             │
                     ┌───────▼────────┐   (engine is STATELESS —
                     │ Object Storage │    no engine DB; product
                     │ S3 (ap-se-2)   │    owns all persistence)
                     │ docs+artifacts │
                     └────────────────┘
```

## 4. Tech Stack
| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | **Next.js 14 + Tailwind** | reuse from prior project |
| Product API | **FastAPI + SQLAlchemy (Python 3.12)** | same ecosystem as engine; one language |
| Engine | **reused `changeorder-recovery`** | FastAPI; `app/ai` pipeline; `claude-opus-4-8`, adaptive thinking, JSON-schema structured outputs |
| Product DB | **PostgreSQL** | multi-tenant, concurrent jobs, row-level scoping (SQLite was dev-only) |
| Job queue | **Postgres-backed queue** (`SELECT … FOR UPDATE SKIP LOCKED`) for MVP | upgrade to Redis/RQ or Celery only if scale demands |
| Object storage | **S3-compatible, Sydney `ap-southeast-2`** | uploaded docs + >1 MB result artifacts |
| Auth | session/JWT + org multi-tenancy | see §7 |
| Deploy | Docker containers, AU region | CI/CD = `.20` |

## 5. Data Model (Product DB)
- **organizations** (`company_id`, name, …) — tenant root.
- **users** (`id`, email, …) and **memberships** (`user_id`, `company_id`, `role` ∈ admin|member) — RBAC.
- **projects** (`id`, `company_id`, name, `project_type=construction_trade`, `country=AU`, status in_progress|completed).
- **documents** (`document_id`, `project_id`, `source_type` ∈ v1.1 enum, `timestamp`, `source`, `storage_key`, …) — uploaded evidence; content in object storage.
- **analysis_jobs** (`job_id`, `request_id` UNIQUE, `project_id`, `status`, `progress_stage`, `engine_job_id`, `result_ref`, `error_code`, timestamps) — mirrors the engine job; `request_id` enforces idempotency (contract §3.1).
- **variations** (`variation_id`, `job_id`, `project_id`, title, description, `confidence_score`, `confidence_band`, engine `status`, **`review_status`** ∈ pending|confirmed|rejected) — engine output + product review state.
- **evidence** (`id`, `variation_id`, `source_type`, `source_document_id`→documents, `reference`, `quote`).
- **value_estimates** (`variation_id`, `amount`, `currency=AUD`, `valuation_confidence_score`, `confidence`).
- **review_actions / audit_log** (`id`, actor, entity, action, before/after, ts) — immutable trail (`.17`).
- **notifications** (`id`, user, type, payload, read_at) (`.18`).

Engine output is **copied into** product tables on job success so the commercial review workflow can mutate `review_status` without touching the engine.

## 6. Core Flow (analysis)
1. User creates a project, uploads docs → stored in object storage; `documents` rows created.
2. User triggers analysis → Product API creates `analysis_jobs` row (`status=queued`, fresh `request_id`); returns immediately.
3. **Worker** picks up the queued job → builds the v1.1 Input Envelope → `POST /v1/analyses` to the engine → stores `engine_job_id` → **polls** engine `GET` with backoff (2s→15s), respecting the **15-min** cap.
4. On engine `succeeded` → ingest result into `variations`/`evidence`/`value_estimates`, set product job `succeeded`, derive `confidence_band` already supplied, fire notification. On `failed`/timeout → record `error_code`, notify; retry = new job (new `request_id`).
5. Commercial team reviews variations (confirm/reject) → `review_status` + audit log.
6. Report generation builds PDF/web from `confirmed` variations.

> Note: two async layers exist — the engine's own job model and the product worker that consumes it. The product worker is simply the engine's **client** per the contract; it owns the user-facing job row and notifications.

## 7. Security & Multi-Tenancy (`.19`)
- Every product table (except global) carries `company_id`; **all queries scoped by org**; enforce at the data-access layer.
- RBAC: admin (manage org/members/projects) vs member (work within assigned projects).
- Object-storage keys namespaced per org; signed, time-limited URLs for access.
- Secrets in a managed secret store (not `.env` in repo — note prior leak; rotate keys).
- AU data residency end-to-end; least-privilege service credentials between product↔engine.

## 8. Mapping to Backlog
| Component | Tasks |
|-----------|-------|
| Auth / org / RBAC | `.2`, `.19` |
| Projects + upload | `.3` |
| Ingestion (email/RFI/site/meeting/SMS/doc) | `.4`–`.8` |
| Engine integration + worker (v1.1 client) | `.21`, `.9`–`.13` (adapt) |
| Job queue + notifications | `.18` (impls async/15-min model) |
| Review workflow | `.14` |
| Reports | `.15` |
| Dashboard / UI | `.16` |
| Audit trail + evidence viewer | `.17` |
| Testing + deploy | `.20` |

## 9. Resolved Architecture Decisions (2026-06-27, founder-approved)
1. **Stateless engine.** The engine keeps **no DB of its own**; the **product owns all persistence**. The engine receives the full Input Envelope per request and returns results — no server-side project state. Cleanest reuse boundary.
2. **Inline result delivery** per contract v1.1: results returned in the poll payload on `succeeded`, with `result_url` fallback only when >1 MB. No shared result store between engine and product.
3. **Hosting: AWS, `ap-southeast-2` (Sydney).** Drives object storage, Postgres, and deploy (`.18`/`.20`). Satisfies AU data residency.
4. **Separate worker process, same image.** The job worker runs as its own process/container (not in-process with the API) but is built from the same codebase/image. Scales independently of the API.

> Consequence of (1): any prior engine-side schema in `changeorder-recovery` is bypassed; the engine is invoked as a pure function of its request. Persistence lives entirely in the product Postgres (§5).
