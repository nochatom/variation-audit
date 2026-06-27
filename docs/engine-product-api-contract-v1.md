# Engine ↔ Product API Contract (v1)

> ⚠️ **SUPERSEDED by [v1.1](engine-product-api-contract-v1.1.md)** (2026-06-27), which inlines decisions `.21.1`–`.21.4`. Kept for history; build against v1.1.

> Owner task: `variation-audit-z3x.21` (Integrate existing detection engine).
> Status: v1 draft. Engine reused from `changeorder-recovery`; product layer built on top (Beads-orchestrated).

## 1. Core Principle
The AI engine (from changeorder-recovery) is treated as a black-box service.
The Beads product layer does NOT modify internal logic — it only sends structured inputs and receives structured outputs.

---

## 2. Input Schema (Product → Engine)

All requests sent to the engine must follow this structure:

```json
{
  "project_id": "string",
  "company_id": "string",
  "project_type": "construction_trade",
  "country": "AU",
  "documents": [
    {
      "type": "email | rfi | site_instruction | meeting_note | sms | document",
      "timestamp": "ISO8601",
      "source": "string (email thread / file / system)",
      "content": "raw text"
    }
  ]
}
```

---

## 3. Engine Processing Responsibilities

The engine must:
- Parse unstructured construction communication
- Detect potential variation events
- Link evidence across multiple documents
- Assign confidence score per variation
- Estimate commercial impact (optional stage)

---

## 4. Output Schema (Engine → Product)

```json
{
  "project_id": "string",
  "variations": [
    {
      "variation_id": "string",
      "title": "string",
      "description": "string",
      "status": "detected | confirmed | uncertain",
      "confidence_score": 0.0,
      "evidence": [
        {
          "type": "email | rfi | instruction | note",
          "reference": "string",
          "quote": "string excerpt"
        }
      ],
      "estimated_value": {
        "amount": 0,
        "currency": "AUD",
        "confidence": "low | medium | high"
      }
    }
  ],
  "engine_version": "v1"
}
```

> `confidence_score` is a float in the range 0.0–1.0.

---

## 5. Boundaries

Engine is NOT responsible for:
- UI rendering
- user authentication
- project management
- workflow orchestration
- notifications

Product layer is NOT responsible for:
- AI inference logic
- variation detection rules
- scoring algorithms

---

## 6. Versioning Rule

All outputs must include:

```json
"engine_version": "v1"
```

---

## 7. Future Extensions

- streaming mode (real-time ingestion)
- incremental updates (delta analysis)
- multi-project batching

---

## 8. Decision Log (v1 refinements — all accepted 2026-06-27)

These ratified decisions amend v1 and should be folded into a consolidated **v1.1**:

| Task | Decision | Doc |
|------|----------|-----|
| `.21.2` | **Async job model** — `POST /v1/analyses`→`202 job_id`; poll `GET`; polling-only; 15-min `ENGINE_TIMEOUT`; no cancellation. | [21.2](decisions/21.2-execution-model.md) |
| `.21.4` | **`request_id`** (UUIDv4 idempotency key, 7-day dedup) + **`contract_version`** envelope; distinct from `engine_version`. | [21.4](decisions/21.4-request-id-and-contract-version.md) |
| `.21.1` | **One `source_type` enum** for input docs + output evidence (`email\|rfi\|site_instruction\|meeting_note\|sms\|document`); `source_document_id` traceability. | [21.1](decisions/21.1-evidence-type-vocabulary.md) |
| `.21.3` | **Two confidence axes** (detection `confidence_score` vs valuation); canonical band map (low<0.5≤med<0.8≤high); engine-derived `confidence_band`; `status` orthogonal. | [21.3](decisions/21.3-confidence-system.md) |
