# Engine ↔ Product API Contract (v1)

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
