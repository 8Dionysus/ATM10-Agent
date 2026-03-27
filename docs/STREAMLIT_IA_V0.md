# STREAMLIT_IA_V0

Decision-complete IA specification for `M8.0` (without implementing Streamlit code in this iteration).

## Goals / Non-goals

Goals:

* Lock the structure of Streamlit operator panel v0 as the single source for `M8.1`.
* Define required UI zones: `Stack Health`, `Run Explorer`, `Latest Metrics`, `Safe Actions`.
* Lock data contracts, field mapping, artifact links, and operator flows.
* Remove product and architecture ambiguity for the implementer.

Non-goals:

* Do not write `scripts/streamlit_operator_panel.py`.
* Do not add `streamlit` to `requirements.txt`.
* Do not change `gateway_request_v1` / `gateway_response_v1`.
* Do not add CI smoke for Streamlit (that belongs to `M8.1`).

## Personas & primary tasks

1. Operator (daily runtime control):
* Check that gateway transport is available and smoke summaries are healthy.
* Quickly open the latest run artifacts when degradation happens.
* Trigger a safe smoke action and get a traceable result path.

2. Engineer (regression diagnostics):
* Compare `status/error_code/request_count/failed_requests_count` between the smoke loop and gateway health.
* Jump from the UI to a specific `run.json/response.json` for root cause analysis.

## IA map

Top-level layout (single page, tabs):

* Tab 1: `Stack Health`
* Tab 2: `Run Explorer`
* Tab 3: `Latest Metrics`
* Tab 4: `Safe Actions`

Global controls (header):

* `runs_dir` (text input, default `runs`)
* `gateway_url` (text input, default `http://127.0.0.1:8770`)
* `Refresh` button (manual refresh only)
* `Last refreshed at` (UTC timestamp)

Future entrypoint (`M8.1`):

* `python -m streamlit run scripts/streamlit_operator_panel.py -- --runs-dir runs --gateway-url http://127.0.0.1:8770`

## Screen specs (4 zones)

### Stack Health

Required widgets:

* Service status card (`gateway transport`)
* HTTP endpoint card (`GET /healthz`)
* Quick diagnostics table for the gateway policy snapshot
* Optional `Return / Recovery` block when explicit `operator_context.returning` exists

Inputs:

* `GET /healthz` from the gateway URL
* Additive `GET /v1/operator/snapshot` recovery surface when the gateway operator snapshot is available

Displayed fields:

* `status`
* `service`
* `timestamp_utc`
* `runs_dir`
* `policy.max_request_body_bytes`
* `policy.max_json_depth`
* `policy.max_string_length`
* `policy.max_array_items`
* `policy.max_object_keys`
* `policy.operation_timeout_sec`

Artifact link rules:

* No artifact links are required for the health transport check.
* If the request fails, show a troubleshooting hint for `docs/RUNBOOK.md`.
* If `Return / Recovery` is present, anchor links must come only from explicit `operator_context.returning.latest_event.anchor_refs`.

Refresh policy:

* Manual only (`Refresh` button), no background polling.

### Run Explorer

Required widgets:

* Directory root indicator (`runs_dir`)
* Scenario selector (`gateway-core`, `gateway-automation`, `gateway-http-core`, `gateway-http-automation`, `phase-a`, `retrieve`, `eval`)
* Latest run card
* Artifact links panel

Inputs:

* Filesystem under `runs/...`
* `run.json` and the relevant summary JSON for the selected scenario

Displayed fields:

* `paths.run_dir`
* `paths.run_json`
* `paths.summary_json`
* `status`
* `request_count`
* `failed_requests_count` (if available)
* Per-request rows (`operation`, `status`, `error_code`, `http_status`, `expected_http_status`, `run_json`)

Artifact link rules:

* Build links only from real existing paths.
* If a file is missing, show `missing`.
* Display the path as an absolute/resolve-only label (do not attempt to auto-open through external toolchains).

Refresh policy:

* Manual only (`Refresh` button).

### Latest Metrics

Required widgets:

* Summary matrix table for canonical smoke sources
* Status badge per source (`ok|error|missing`)
* Compact trend snapshot (latest only, no historical charts in v0)
* Optional `G2 operating cycle` snapshot as the primary operator-facing triage summary

Inputs (canonical sources):

* `runs/ci-smoke-phase-a/smoke_summary.json`
* `runs/ci-smoke-retrieve/smoke_summary.json`
* `runs/ci-smoke-eval/smoke_summary.json`
* `runs/ci-smoke-gateway-core/gateway_smoke_summary.json`
* `runs/ci-smoke-gateway-automation/gateway_smoke_summary.json`
* `runs/ci-smoke-gateway-http-core/gateway_http_smoke_summary.json`
* `runs/ci-smoke-gateway-http-automation/gateway_http_smoke_summary.json`

Supporting optional operator sources:

* `runs/nightly-gateway-sla-operating-cycle/operating_cycle_summary.json`
* `runs/nightly-gateway-sla-progress/progress_summary.json`
* `runs/nightly-gateway-sla-remediation/remediation_summary.json`
* `runs/nightly-gateway-sla-integrity/integrity_summary.json`

Displayed fields:

* Core: `status`, `observed.results_count`, `observed.query_count`, `observed.mean_mrr_at_k`
* Gateway local: `status`, `request_count`
* Gateway HTTP: `status`, `request_count`, `failed_requests_count`
* G2 operating cycle: `cycle.source`, `operating_mode`, `used_manual_fallback`, `manual_execution_mode`, `manual_decision_status`, `remaining_for_window`, `remaining_for_streak`, `integrity_status`, `attention_state`, `earliest_go_candidate_at_utc`, `next_action_hint`

Artifact link rules:

* Every row must include a link to the source summary JSON.
* For `G2 operating cycle`, the summary JSON is required; `triage_brief.md` is optional and its absence must not make the UI error.

Refresh policy:

* Manual only (`Refresh` button).

### Safe Actions

Required widgets:

* Action selector:
  * `Gateway HTTP smoke core`
  * `Gateway HTTP smoke automation`
  * `Gateway local smoke core`
  * `Gateway local smoke automation`
* Optional `runs_dir override` input
* Optional recommended/preselected action posture from explicit return evidence
* `Execute safe action` button
* Result panel (`exit_code`, `status`, `summary_json`, `run_dir`)

Inputs:

* Local script entrypoints:
  * `scripts/gateway_v1_http_smoke.py`
  * `scripts/gateway_v1_smoke.py`
* `scripts/run_gateway_sla_operating_cycle.py` is not part of `Safe Actions` in v0; it is read only as a summary source in `Latest Metrics`.

Displayed fields:

* Executed command (string)
* Exit code
* Parsed summary status (`ok|error`)
* Artifact paths
* Optional recommended action label / hint

Artifact link rules:

* Every action must return a link to a summary JSON.
* If the summary is missing, the action counts as failed even when `exit_code=0`.

Refresh policy:

* No auto-refresh after the action; the operator presses `Refresh`.

## Data contracts & field mapping

Summary contract mapping (minimum required set):

1. `smoke_summary.json` (`phase_a_smoke|retrieve_demo|eval_retrieval`):
* `status`
* `observed.mode`
* `observed.*` metrics by mode

2. `gateway_smoke_summary.json`:
* `status`
* `scenario`
* `request_count`
* `requests[].operation`
* `requests[].status`
* `requests[].error_code`
* `requests[].run_json`

3. `gateway_http_smoke_summary.json`:
* `status`
* `scenario`
* `request_count`
* `failed_requests_count`
* `requests[].operation`
* `requests[].status`
* `requests[].http_status`
* `requests[].expected_http_status`
* `requests[].error_code`
* `requests[].run_json`

4. Gateway transport dependency:
* `GET /healthz` for service diagnostics
* `POST /v1/gateway` for future interactive panel actions

## Error/empty/loading states

1. Loading:
* While reading files/health requests, show a `loading` indicator.

2. Empty:
* If a summary file is missing, the source status is `missing`.
* The UI must not crash; show `not available yet` instead of data.

3. Error:
* JSON parse error -> status `error`, text `invalid summary format`.
* HTTP error/timeout on `GET /healthz` -> status `error`, show `gateway unavailable`.
* For `Safe Actions`, any of the following is an error:
  * non-zero exit code
  * summary `status=error`
  * missing summary file

## Operator flows (happy + failure)

Flow A (happy): daily check

1. Operator opens the panel.
2. Presses `Refresh`.
3. Sees `status=ok` in `Stack Health`.
4. Sees `ok` for gateway/core sources in `Latest Metrics` and, if available, a fresh `G2 operating cycle` snapshot.
5. If needed, opens `Run Explorer` and follows the link to `run.json`.

Flow B (failure): gateway HTTP regression

1. In `Latest Metrics`, source `gateway-http-core` shows `error`.
2. Operator opens `Run Explorer` and inspects `gateway_http_smoke_summary.json`.
3. Checks `failed_requests_count` and request rows.
4. Follows `run_json` into the problematic run.
5. Checks `Stack Health` for `GET /healthz` and the policy snapshot.

Flow C (safe action rerun)

1. In `Safe Actions`, choose `Gateway HTTP smoke core`.
2. Press `Execute safe action`.
3. Get `exit_code/status/summary_json`.
4. Press `Refresh` and verify updated status in `Latest Metrics`.

## Safe actions guardrails

* Only safe smoke-trigger commands are allowed.
* `G2 operating cycle` is not added to the action selector while the surface remains smoke-only.
* Any real keyboard/mouse/game-state mutation action is forbidden.
* Every action must be traceable through artifacts in `runs/...`.
* The UI must not hide the launch command; the operator must see the exact command string.
* Any ambiguity is treated as `deny by default`.
* `Return / Recovery` stays inside `Stack Health`; no fifth tab is introduced.
* The panel may preselect an existing smoke action from explicit return evidence, but must not execute it automatically.

## M8.1 handoff checklist

Implementation contract for `scripts/streamlit_operator_panel.py`:

* Support CLI args:
  * `--runs-dir` (default `runs`)
  * `--gateway-url` (default `http://127.0.0.1:8770`)
* Required UI zones: `Stack Health`, `Run Explorer`, `Latest Metrics`, `Safe Actions`.
* Load data only from the canonical sources listed in this document.
* Manual refresh by button as the default policy.

No-crash startup criterion (`M8.1`):

* The UI startup command must complete bootstrap without exception in a headless smoke environment.

Machine-readable summary contract (`M8.1` target):

* Path: `runs/<timestamp>-streamlit-smoke/streamlit_smoke_summary.json`
* Required fields:
  * `schema_version = "streamlit_smoke_summary_v1"`
  * `status = "ok" | "error"`
  * `startup_ok` (bool)
  * `tabs_detected` (list[str])
  * `missing_sources` (list[str])
  * `errors` (list[str])
  * `paths.run_dir`
  * `paths.summary_json`

Exit policy (`M8.1` target):

* `0` only when `status=ok`.
* `2` for any `status=error`.
