# Engine ↔ Product API Contract (v1.1)

> Owner task: `variation-audit-z3x.21` (Integrate existing detection engine).
> Supersedes [v1](engine-product-api-contract-v1.md). Consolidates the four ratified decisions (`.21.1`–`.21.4`, accepted 2026-06-27) into one authoritative spec.
> Market scope: **Australia only**, all construction trades. Engine reused from `changeorder-recovery`; product layer built on top, Beads-orchestrated.

## 1. Core Principle
The AI engine is a **black-box service**. The product layer sends structured inputs and receives structured outputs; it never modifies engine inference logic. The engine never handles UI, auth, project management, workflow, or notifications.

---

## 2. Execution Model — Async Jobs  *(.21.2)*
The engine pipeline (ingest → baseline → classify → quantify → confidence over many documents) is long-running, so all analysis is **asynchronous and job-based**. MVP is **polling-only** (no webhook), **15-min** job timeout, **no cancellation**.

### 2.1 Create a job
```
POST /v1/analyses   ->   202 Accepted
```
Body = the Input Envelope (§3). Response:
```json
{
  "job_id": "string",
  "status": "queued",
  "request_id": "uuid-v4",
  "created_at": "ISO8601",
  "links": { "self": "/v1/analyses/{job_id}" }
}
```

### 2.2 Poll a job
```
GET /v1/analyses/{job_id}   ->   200 OK
```
```json
{
  "job_id": "string",
  "request_id": "uuid-v4",
  "project_id": "string",
  "status": "queued | running | succeeded | failed",
  "progress": { "stage": "ingest | baseline | classify | quantify | confidence", "percent": 0.0 },
  "result": { "...Output Schema (§4), present only when status=succeeded..." },
  "error": { "code": "string", "message": "string", "retryable": false, "details": {} },
  "engine_version": "v1",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

### 2.3 Status lifecycle (MVP)
```
queued ──► running ──► succeeded
               │
               └─────► failed   (terminal; retryable flag set; incl. 15-min ENGINE_TIMEOUT)
```
Terminal states never transition. No `canceled` state in MVP. A retryable failure is re-run by submitting a **new** job (subject to idempotency, §3.1).

### 2.4 Result delivery
Returned inline in the poll payload on `succeeded`. If the serialized result exceeds 1 MB, the engine returns `result_url` to a stored artifact instead of inline `result`.

### 2.5 Client guidance / SLA
- `POST`→`202` ack < 1s (enqueue only).
- Poll with backoff: start 2s, cap 15s.
- Soft per-job timeout: **15 min** → `failed` / `ENGINE_TIMEOUT` (`retryable=true`).

---

## 3. Input Envelope (Product → Engine)  *(.21.4)*
```json
{
  "request_id": "uuid-v4",
  "contract_version": "v1.1",
  "project_id": "string",
  "company_id": "string",
  "project_type": "construction_trade",
  "country": "AU",
  "documents": [
    {
      "document_id": "string (optional; engine assigns if absent)",
      "type": "email | rfi | site_instruction | meeting_note | sms | document",
      "timestamp": "ISO8601",
      "source": "string (email thread / file / system)",
      "content": "raw text"
    }
  ],
  "callback_url": null
}
```
`request_id` and `contract_version` are **required**, echoed on every response and error.

### 3.1 request_id — idempotency & tracing
- Client-generated **UUID v4**, unique per logical submission; it is the **idempotency key**.
- **Dedup window: 7 days.** A repeat `POST` with a seen `request_id` returns the *existing* job (`200`, not a new `202`).
- **Conflict guard:** same `request_id` + different body → `409` (`IDEMPOTENCY_KEY_REUSE`).
- Acts as the **correlation ID** across product UI → `jobs` table → engine logs → result.

### 3.2 contract_version — schema negotiation
- Names the request/response schema the product speaks (now `"v1.1"`).
- Validated synchronously at `POST`; unsupported → `400` (`UNSUPPORTED_CONTRACT_VERSION`, `details.supported`).
- Independent from `engine_version` (engine build/model-pipeline version, for result provenance).

---

## 4. Output Schema (Engine → Product)  *(.21.1, .21.3)*
```json
{
  "project_id": "string",
  "engine_version": "v1",
  "variations": [
    {
      "variation_id": "string",
      "title": "string",
      "description": "string",
      "status": "detected | confirmed | uncertain",
      "confidence_score": 0.0,
      "confidence_band": "low | medium | high",
      "evidence": [
        {
          "type": "email | rfi | site_instruction | meeting_note | sms | document",
          "source_document_id": "string",
          "reference": "string (human-readable locator)",
          "quote": "string excerpt"
        }
      ],
      "estimated_value": {
        "amount": 0,
        "currency": "AUD",
        "valuation_confidence_score": 0.0,
        "confidence": "low | medium | high"
      }
    }
  ]
}
```

### 4.1 Shared `source_type` vocabulary  *(.21.1)*
One closed enum used by **both** `documents[].type` (input) and `evidence[].type` (output):

| value | meaning |
|-------|---------|
| `email` | email message or thread |
| `rfi` | request for information + its response |
| `site_instruction` | architect / engineer / superintendent instruction |
| `meeting_note` | meeting minutes or notes |
| `sms` | SMS / text message |
| `document` | generic document (PDF, DOCX, image, other) — catch-all |

Deprecated v1 names removed: `instruction`→`site_instruction`, `note`→`meeting_note`. Unknown inputs map to `document`. Every `evidence[]` item carries `source_document_id` tracing it to the originating input document.

### 4.2 Confidence system — two orthogonal axes  *(.21.3)*
| Axis | Field | Type | Meaning |
|------|-------|------|---------|
| Detection | `confidence_score` | float 0.0–1.0 | Sureness this *is* a legitimate unclaimed variation |
| Valuation | `estimated_value.confidence` | low/med/high | Sureness of the dollar estimate |

The axes are independent. Canonical **score → band** mapping (single source of truth; UI must not re-implement):

| band | range |
|------|-------|
| `low` | 0.00 – 0.49 |
| `medium` | 0.50 – 0.79 |
| `high` | 0.80 – 1.00 |

- `confidence_band` is engine-derived from `confidence_score` via the table above.
- When `valuation_confidence_score` is present, `estimated_value.confidence` is derived from it via the **same** mapping.
- `status` (`detected | confirmed | uncertain`) is **workflow state, orthogonal to confidence**: `detected` is the engine default, `uncertain` flags items needing human attention, `confirmed` is set only by a human in the commercial review workflow (`.14`). Confidence informs prioritisation; it never sets `status`.

---

## 5. Engine Processing Responsibilities
- Parse unstructured construction communication.
- Detect potential variation events.
- Link evidence across multiple documents (with `source_document_id`).
- Assign `confidence_score` (+ derived `confidence_band`) per variation.
- Estimate commercial impact (`estimated_value`) — may be omitted/low-confidence when unquantifiable.

---

## 6. Boundaries
**Engine is NOT responsible for:** UI rendering · authentication · project management · workflow orchestration · notifications.
**Product layer is NOT responsible for:** AI inference logic · variation detection rules · scoring algorithms.

---

## 7. Error Envelope & Codes
```json
{ "error": { "code": "string", "message": "human readable", "retryable": true, "details": {} } }
```
Validation failures are caught synchronously at `POST` (`4xx`, no job created); processing failures appear on the job as `status=failed`.

| code | HTTP | when |
|------|------|------|
| `INVALID_INPUT` | 400 | missing/malformed fields (incl. `request_id`, `contract_version`) |
| `UNSUPPORTED_CONTRACT_VERSION` | 400 | `contract_version` not in supported set |
| `IDEMPOTENCY_KEY_REUSE` | 409 | same `request_id`, different body |
| `ENGINE_TIMEOUT` | — (on job) | 15-min processing cap exceeded (`retryable`) |
| `LLM_UNAVAILABLE` | — (on job) | upstream model errors exhausted internal retries (`retryable`) |
| `INTERNAL` | — (on job) | unexpected engine failure |

Internal retries: transient LLM/API errors (429/5xx) are retried inside the worker with backoff; only exhausted transients surface as `failed`. Clients must not auto-resubmit on timeout — they poll.

---

## 8. Versioning Rules
- Every output includes `engine_version` (currently `"v1"`).
- Every request includes `contract_version` (currently `"v1.1"`).
- The `source_type` enum and the confidence thresholds (0.49 / 0.79) are part of `contract_version`; changing either is a contract change so historical results stay interpretable.
- Engine and product share the enum + mapping from a **single definition** (generated/imported), never duplicated literals.

---

## 9. Future Extensions (post-MVP)
- Synchronous `POST /v1/quick-check` single-document preview.
- `callback_url` webhook (signed, retried) on terminal state.
- Job cancellation (`DELETE`) + `canceled` state.
- Streaming progress (SSE/WebSocket) superseding polling.
- Incremental / delta analysis (re-run only new documents).
- Multi-project batch submission.

---

## 10. Provenance
Consolidated from v1 + decisions `.21.1` (evidence vocabulary), `.21.2` (execution model), `.21.3` (confidence system), `.21.4` (request_id/contract_version). Individual decision docs in [docs/decisions/](decisions/).
