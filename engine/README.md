# Detection Engine (reused from `changeorder-recovery`)

This tree is the **stateless detection engine** — kept separate from the product
layer (`../backend/`). Per the architecture decision, the product owns all
persistence and calls the engine over the [Engine↔Product API contract v1.1](../docs/engine-product-api-contract-v1.1.md).

> **Status / provenance.** The production engine lives in the private
> `nochatom/changeorder-recovery` repo (`backend/app/ai`: ingest → baseline →
> classify → quantify → confidence). That repo is **not present in this
> workspace**, so the code here is a faithful **reference implementation** of the
> stages, written against the same contract and ready to port into the real
> engine. When the engine repo is available, `app/ai/normalization/` maps onto
> its **ingest + baseline** stages.

## Pipeline stages → backlog tasks
| Stage | Task | Status |
|-------|------|--------|
| ingest + baseline (parse & normalize) | `.9` | this module |
| classify (variation detection) | `.10` | todo |
| evidence linking | `.11` | todo |
| confidence | `.12` | todo |
| quantify (recoverable value) | `.13` | todo |

## `app/ai/normalization/` (.9 — AI document parsing & normalization)
Turns raw, unstructured AU construction communications into a canonical
`NormalizedDocument` (parties, references, dates, scope items) that the
detection stage consumes.

- `schema.py` — `NormalizedDocument` and the normalized internal types.
- `parser.py` — `parse_document(...)`: Claude (`claude-opus-4-8`, adaptive
  thinking, structured outputs) → `NormalizedDocument`. The Anthropic client is
  injected so it's testable without a key.
- `dates.py` — deterministic **day-first (AU)** date → ISO-8601 normalization.

The `NormalizedDocument` is **engine-internal**, distinct from the v1.1 wire
schema the product exchanges with the engine.

## Test
```bash
python -m pytest      # no live LLM; a fake client returns canned structured JSON
```
