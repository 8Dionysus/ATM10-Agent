# RECURRENCE_OPERATOR_RECOVERY

Operator-facing recurrence landing for `ATM10-Agent`.

## Core distinction

* `recurrence` is the standing recovery law for the operator product when the current surface loses footing.
* `return` is the concrete operator-visible recovery move published by this repo.

## What this repo owns

`ATM10-Agent` does not own runtime-policy meaning for the wider federation. In this repository, recovery means:

* launcher and pilot publish bounded return evidence
* snapshot lifts that evidence into `operator_context.returning`
* gateway keeps the same operator endpoints and adds recommendation posture only
* Streamlit keeps the same 4-tab IA and renders recovery inside existing tabs

## Public recovery surfaces

Tracked recovery contracts for this wave:

* `schemas/gateway_operator_return_event.schema.json`
* `schemas/gateway_operator_return_summary.schema.json`
* `schemas/operator_return_reason_catalog.schema.json`
* `examples/gateway_operator_return_event.example.json`
* `examples/gateway_operator_return_summary.example.json`
* `examples/operator_return_reason_catalog.example.json`

The operative artifact names stay `return_*` because they describe the concrete recovery move, not the doctrine itself.

## Emitters and carrier surfaces

Startup emitter:

* `scripts/start_operator_product.py`
* writes `last_return_event`
* writes `return_loop_state`
* writes `return/latest_return_event.json`
* appends `return/return_events.jsonl`

Pilot emitter:

* `scripts/pilot_runtime_loop.py`
* emits only for recurring, anchorable, operator-visible recovery conditions
* does not emit for every degraded turn
* uses `safe_stop_after = 2` for the same emitted `reason_code`

Operator carrier surfaces:

* `scripts/operator_product_snapshot.py` publishes `operator_context.returning`
* `GET /v1/operator/snapshot` returns that surface additively
* `GET /v1/operator/safe-actions` returns recommendation/preselect hints additively
* `scripts/streamlit_operator_panel.py` renders `Return / Recovery` inside `Stack Health`

## Guardrails

This wave does not:

* add a new operator endpoint
* add a fifth Streamlit tab
* auto-run safe actions
* add new mutating safe actions
* replace compact operator triage

`operator_context.triage` remains the compact overview. `operator_context.returning` is a dedicated sibling surface for explicit recovery evidence.

## Safe action posture

Recovery may recommend only already-existing smoke-only actions:

* `gateway_local_core`
* `gateway_http_core`
* `gateway_http_combo_a`
* `cross_service_suite_smoke`
* `cross_service_suite_combo_a_smoke`
* `gateway_sla_operating_cycle_smoke`
* `combo_a_operating_cycle_smoke`

Recommendation is additive and reviewable. Execution still requires explicit operator confirmation.

## Anchor posture

Canonical anchor families for this wave:

* startup artifacts: `run.json`, `startup_plan.json`, `last_checkpoint`
* snapshot artifacts: latest gateway operator snapshot
* pilot artifacts: `pilot_runtime_status_latest.json`, latest `pilot_turn.json`
* smoke evidence: canonical gateway, cross-service, and operating-cycle summaries
* audit: `ui-safe-actions/safe_actions_audit.jsonl`

Recovery summaries must point to explicit machine-readable anchors. They do not invent anchors from absent files.
