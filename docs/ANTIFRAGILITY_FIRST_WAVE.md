# ANTIFRAGILITY FIRST WAVE

## Goal

Make the existing degraded hybrid-query posture legible as source-owned antifragility instead of leaving it as an implicit operator virtue.

## First-wave family

Wave 1 names one bounded family:

- retrieval still succeeds
- the KAG stage fails or returns no useful expansion
- the run stays `status=ok`
- the degraded state is emitted as one source-owned receipt instead of being inferred later by another layer

## What is live now

The live first-wave emission point is only `scripts/hybrid_query_demo.py::run_hybrid_query`, surfaced through `scripts/gateway_v1_local.py` when:

- `planner_status == "retrieval_only_fallback"`
- `degraded == true`

That run emits `stressor_receipt.json` plus additive pointers in `run.json` and `hybrid_query_results.json`.

## Public contract surfaces

- `schemas/stressor_receipt_v1.json`
- `schemas/adaptation_delta_v1.json`
- `examples/stressor_receipt.retrieval_only_fallback.example.json`
- `examples/adaptation_delta.retrieval_only_fallback.example.json`

The schemas are intentionally broader than the first live trigger. They can describe future degraded families, but wave 1 only emits the retrieval-only fallback receipt.

## Ownership posture

`ATM10-Agent` owns the source event for wave 1.

- `run_hybrid_query` is the only live emitter.
- `gateway_v1_local` may surface receipt pointers, but it does not mint a second event.
- `pilot_runtime_loop` stays consumer-only for degraded flags and operator context.
- downstream eval, stats, and doctrine layers can read the receipt, but they do not become the source of truth for it.

## Companion delta posture

`adaptation_delta_v1` is present as a reviewed-change companion contract, not as an auto-emitted runtime object.

Use it only when a real change cites earlier stressor receipts and explains:

- what surface changed
- why that change was chosen
- how the expected improvement will be checked

## Guardrails

- do not replace the existing run artifacts
- do not auto-repair or widen automation authority
- do not treat degraded evidence as permission to mutate
- do not let eval or stats layers overwrite source ownership
- do not silently widen wave 1 to `kag_only_fallback` or `grounding_unavailable` without an explicit follow-up campaign

## Operator reading

For wave 1, a healthy degraded run should let an operator point to:

- `run.json`
- `hybrid_query_results.json`
- `stressor_receipt.json`

The receipt says what stressor happened, what fallback stayed bounded, what evidence supports it, and that mutation remained blocked.
