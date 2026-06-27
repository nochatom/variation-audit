# Engine ↔ Product API Contract (v1.2)

> Owner task: `variation-audit-z3x.21` · Supersedes [v1.1](engine-product-api-contract-v1.1.md).
> Reconciled against the real engine (`changeorder-recovery`, see [engine-reconciliation.md](engine-reconciliation.md)).
> Market: **Australia only**, all construction trades.

## 0. What changed from v1.1 (and why)
The real engine's `pipeline.run_recovery()` **requires a contract + scope + AU state** and emits **`flags`** with a **time-bar risk** and a contract **baseline** — none of which v1.1 could carry. v1.2 fixes that while keeping the async job model intact:
- **Input** gains `contract_text` (required), `scope_text`, `state`.
- **Output** variation gains `time_bar_risk`, `estimate_low`/`estimate_high`, `confidence_factors`; response gains a top-level `baseline`.
- The engine is invoked as a **stateless function** (`run_recovery`, no persistence); the product owns all persistence. The engine's own DB/endpoints/frontend are **not** used.

## 1. Core Principle
The detection engine is a **black-box, stateless** capability: the product sends a contract + scope + comms, the engine returns detected variations. The product owns auth, orgs, persistence, review, reporting, and notifications. The engine never persists for the product.

## 2. Execution Model — Async Jobs *(.21.2, unchanged)*
Polling-only, **15-min** cap, no cancellation.

### 2.1 Create — `POST /v1/analyses` → `202`
```json
{ "job_id": "string", "status": "queued", "request_id": "uuid-v4",
  "created_at": "ISO8601", "links": { "self": "/v1/analyses/{job_id}" } }
```
### 2.2 Poll — `GET /v1/analyses/{job_id}` → `200`
```json
{
  "job_id": "string", "request_id": "uuid-v4", "project_id": "string",
  "status": "queued | running | succeeded | failed",
  "progress": { "stage": "ingest | baseline | classify | quantify | confidence", "percent": 0.0 },
  "result": { "...Output Schema (§4), present only when status=succeeded..." },
  "result_url": null,
  "error": { "code": "string", "message": "string", "retryable": false, "details": {} },
  "engine_version": "v1", "created_at": "ISO8601", "updated_at": "ISO8601"
}
```
Lifecycle `queued → running → succeeded | failed`; 15-min → `failed`/`ENGINE_TIMEOUT`. Result inline; `result_url` when >1 MB.

## 3. Input Envelope (Product → Engine)
```json
{
  "request_id": "uuid-v4",
  "contract_version": "v1.2",
  "project_id": "string",
  "company_id": "string",
  "project_type": "construction_trade",
  "country": "AU",
  "state": "NSW | VIC | QLD | SA | WA | TAS | ACT | NT | null",   // AU state/territory (SoP regime hint)
  "contract_text": "string (REQUIRED) — the head contract text",
  "scope_text": "string — scope / BOQ text, may be empty",
  "documents": [
    {
      "document_id": "string (optional; engine assigns if absent)",
      "type": "email | rfi | site_instruction | meeting_note | sms | document",
      "timestamp": "ISO8601",
      "source": "string",
      "content": "raw text"
    }
  ],
  "callback_url": null
}
```
- `request_id`, `contract_version`, **`contract_text`** are required.
- `request_id` idempotency + `contract_version` negotiation: unchanged from `.21.4` (7-day dedup, `409 IDEMPOTENCY_KEY_REUSE`, `400 UNSUPPORTED_CONTRACT_VERSION`).
- `state` maps to the engine's `state` hint (drives SoP regime + time-bar). `document.type` maps to the engine `NormalisedDoc.kind`.

## 4. Output Schema (Engine → Product)
```json
{
  "project_id": "string",
  "engine_version": "v1",
  "baseline": {
    "inclusions_count": 0,
    "exclusions_count": 0,
    "notice_clause": "string | null",
    "time_bar_days": 0,
    "sop_regime": "string | null"
  },
  "recoverable_total": 0,
  "time_bar_at_risk": 0,
  "variations": [
    {
      "variation_id": "string",                         // minted by the adapter (engine flags have no id)
      "title": "string",
      "description": "string",                          // engine flag.rationale
      "status": "detected | confirmed | uncertain",
      "confidence_score": 0.0,                           // flag.confidence (0-100) / 100
      "confidence_band": "low | medium | high",          // derived (.21.3)
      "confidence_factors": { },                         // engine deterministic breakdown
      "time_bar_risk": false,                            // AU SoP — entitlement may be time-barred
      "evidence": [
        { "type": "email | rfi | site_instruction | meeting_note | sms | document",
          "source_document_id": "string", "reference": "string | null", "quote": "string | null" }
      ],
      "estimated_value": {
        "amount": 0,                                     // flag.estimate_likely
        "estimate_low": 0,
        "estimate_high": 0,
        "currency": "AUD",
        "basis_quality": "boq | rate_card | inferred | none",
        "valuation_confidence_score": 0.0,
        "confidence": "low | medium | high"
      }
    }
  ]
}
```

### 4.1 Shared `source_type` vocabulary *(.21.1, unchanged)*
`email | rfi | site_instruction | meeting_note | sms | document`, used by input `documents[].type` and output `evidence[].type`.

### 4.2 Confidence *(.21.3, with engine source)*
`confidence_score` = engine `flag.confidence` (0–100) ÷ 100. `confidence_band` derived via the canonical map (low<0.5≤medium<0.8≤high). `confidence_factors` carries the engine's deterministic breakdown for the "why" panel. Valuation confidence: `basis_quality` → `boq`/`rate_card`→high, `inferred`→medium, `none`→low.

## 5. flag → variation mapping (adapter)
| Engine `flag` | v1.2 `variation` |
|---|---|
| `title` | `title` |
| `rationale` | `description` |
| `confidence` (0–100) | `confidence_score` (/100) + `confidence_band` |
| `confidence_factors` | `confidence_factors` |
| `time_bar_risk` | `time_bar_risk` |
| `evidence_doc_ids[]` | `evidence[].source_document_id` (+ `type` looked up from input docs) |
| `estimate_likely` | `estimated_value.amount` |
| `estimate_low` / `estimate_high` | `estimated_value.estimate_low` / `estimate_high` |
| `basis_quality` | `estimated_value.basis_quality` → `valuation_confidence` |
| — | `variation_id` minted by adapter; `status` defaults `detected` |
Engine `baseline` (inclusions/exclusions/notice_clause/time_bar_days/sop_regime) → response `baseline`.

## 6. Engine invocation (adapter internals)
The adapter calls `changeorder-recovery` `pipeline.run_recovery(contract_text, scope_text, state, raw_docs, quantify=True)` — the **stateless** orchestrator (no DB). `raw_docs` are built from `documents[]` (`type`→`kind`, `content`→`text`, `timestamp`→`occurred_at`, `source`→`author`/`source_uri`, `document_id`→`id`). The engine's `structured_call` already uses `claude-opus-4-8`, streaming, adaptive thinking, `effort:high`, json_schema, and refusal handling.

## 7. Error Envelope & Codes *(unchanged from v1.1 §7)*
`INVALID_INPUT` (400; now also missing `contract_text`), `UNSUPPORTED_CONTRACT_VERSION` (400), `IDEMPOTENCY_KEY_REUSE` (409), `ENGINE_TIMEOUT` / `LLM_UNAVAILABLE` / `INTERNAL` (on job). The engine's `stop_reason=refusal` maps to a job `failed` with `LLM_UNAVAILABLE` (retryable).

## 8. Versioning & Boundaries
`contract_version: "v1.2"` (supported set: `["v1.2"]` for MVP). `engine_version` is the engine build. Engine NOT responsible for UI/auth/persistence/workflow/notifications; product NOT responsible for inference/detection/scoring. Single shared `source_type` enum + confidence mapping.

## 9. Future Extensions
Sync `quick-check`; webhook; cancellation; streaming progress; delta analysis; batch; richer baseline (per-item inclusions/exclusions) in the wire schema.

## 10. Provenance
v1.2 = v1.1 (decisions `.21.1`–`.21.4`) + reconciliation deltas (contract/scope/state input; time_bar_risk + estimate range + baseline output; stateless `run_recovery` invocation). See [engine-reconciliation.md](engine-reconciliation.md).
