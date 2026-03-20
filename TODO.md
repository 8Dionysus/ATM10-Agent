# TODO.md — atm10-agent

English is the primary language. Only established technical terms remain in English form where appropriate (Quickstart, Phase, smoke test, RAG, VLM, artifacts, run, tests, boundaries).

Execution rule: small, reviewable diffs + runnable commands + at least 1 test for any noticeable behavior change.

## Source Of Truth

Canonical document map: `docs/SOURCE_OF_TRUTH.md`.

In short:

* `TODO.md` — step-by-step execution plan (what we do now and next).
* `PLANS.md` — goals, milestones, DoD, and constraints (why and where we are going).
* `docs/SESSION_*.md` — detailed chronology of run artifacts and experiments.
* `docs/DECISIONS.md` — architecture decisions (1-3 bullets per change).
* `docs/RUNBOOK.md` — runnable commands and operational profiles.
* `docs/ARCHIVED_TRACKS.md` — archived/recoverable directions.

## Status Snapshot (as of 2026-03-13)

* M0/M1/M2/M3 are baseline-complete.
* `python -m pytest` green (see `docs/SESSION_2026-03-13.md` and CI for the current snapshot).
* Active ASR path: `whisper_genai`; `qwen_asr` is archived/recoverable opt-in.
* KAG Neo4j path validated (`build -> sync -> query -> eval`, hard-case uplift + latency tuning).
* `G2` nightly strict path is active:
  * `.github/workflows/gateway-sla-readiness-nightly.yml` publishes `readiness/governance/progress/transition/remediation/integrity`;
  * `pytest.yml` remains in `signal_only` (`nightly_only` enforcement surface).
* Streamlit `Latest Metrics` shows `G2 operating cycle` as the primary operator-facing triage snapshot, while published `fail_nightly progress`, `remediation`, and `integrity` remain supporting surfaces without changing nightly policy.
* Latest local `G2` fallback cycle (`2026-03-12T21:53:16Z`, local session `2026-03-13`):
  * `manual_nightly.execution_mode=accounted`, `decision_status=allow_accounted_dispatch`
  * `readiness.window_observed=3`, `progress.remaining_for_window=11`, `progress.remaining_for_streak=3`
  * `cadence.attention_state=ready_for_accounted_run`, `earliest_go_candidate_at_utc=2026-03-22T21:53:16.661488+00:00`
* Latest single-cycle `G2` operator pass (`2026-03-12T22:10:02Z`, same UTC day):
  * `operating_cycle.source=manual`, `operating_mode=reuse_fresh_latest`, `used_manual_fallback=false`
  * required latest summaries were already fresh, so no new accounted run was spent
  * `next_action_hint=continue_g2_backlog`
* Latest local `G2` remediation snapshot:
  * `readiness_status=not_ready`, `governance.decision_status=hold`, `progress.decision_status=hold`;
  * `progress.remaining_for_window=11`, `progress.remaining_for_streak=3`;
  * `candidate_items=3` (`regression_investigation`, `window_accumulation`, `ready_streak_stabilization`).
* Latest local `G2` integrity snapshot:
  * `integrity_status=clean`
  * `telemetry_ok=true`, `dual_write_ok=true`, `anti_double_count_ok=true`, `utc_guardrail_status=ok`
  * `invalid_counts`: `governance=0`, `progress_readiness=0`, `progress_governance=0`, `transition_aggregated=0`

## Session Focus (2026-03-13)

* Treat `G2` as a monitoring/remediation track after the switch, using workflow-published `remediation_summary.json` as the primary triage source and `scripts/run_gateway_sla_operating_cycle.py` as the preferred local single-cycle entrypoint.
* Use the fresh local fallback cycle (`manual_nightly -> cycle_summary -> cadence_brief`) as the current local source-of-truth after the accounted run from `2026-03-12T21:53:16Z`; the current operator-helper pass confirms the latest snapshot is already fresh and does not require a new fallback.
* Use `runs/nightly-gateway-sla-integrity/integrity_summary.json` as the machine-readable daily verdict for telemetry/UTC guardrail checks; do not open a telemetry repair track while `integrity_status=clean`.
* Continue the G2 accumulation path without changing WIP focus: `remaining_for_window=11`, `remaining_for_streak=3`, `allow_switch=false`.
* Keep human-facing docs synchronized with `docs/SESSION_2026-03-13.md`.
* Keep Streamlit `Safe Actions` as a smoke-only surface; `scripts/run_gateway_sla_operating_cycle.py` remains a CLI/local helper, not a UI action.

## WIP Policy

* Maximum active tasks at the same time: **3**.
* Take a new task only after closing or moving the current one to `Blocked`.

## Now (WIP <= 3)

* [ ] `G2 strict nightly monitoring` (primary, only active track): daily check the latest summaries (`readiness/governance/progress/transition/cadence`) and reason-codes after enabling the permanent `fail_nightly` gate; the local single-cycle entrypoint is now `scripts/run_gateway_sla_operating_cycle.py`, and direct manual fallback is needed only if the helper confirms stale/missing required sources.
* [ ] `G2 remediation loop`: when nightly fails, take workflow-published `runs/nightly-gateway-sla-remediation/remediation_summary.json` as the source-of-truth, use it together with `runs/nightly-gateway-sla-operating-cycle/operating_cycle_summary.json` in Streamlit `Latest Metrics`, and expand `candidate_items` into 3-5 `G2`-only items in `TODO/session`; current local backlog remains `regression_investigation`, `window_accumulation`, `ready_streak_stabilization`.
* [ ] `G2 telemetry integrity`: confirm `integrity_summary.json -> decision.integrity_status=clean` and `invalid_counts=0` for any deviations (`invalid_or_mismatched_count`, UTC guardrail, dual-write, anti-double-count).

## Next

* [ ] Filesystem housekeeping outside the current interface: remove orphan directory `D:/atm10-agent-hotfix-g23` as a normal folder (Git no longer treats it as a worktree; the current blocker was only policy on destructive delete from this environment).
* [ ] Optional recovery follow-up for `release/wave6-security-hardening`: use `runs/20260312_232852-release-wave6-recovery-triage/`, start only from a fresh branch off `master`; first candidate is `codex/release-wave6-ops-contracts`, do not use the release branch itself as the base.
* [ ] After strict nightly stabilizes, return to `G3 follow-up` (next intent template): when adding the next new `intent_type`, apply checklist `M6.19` (fixture + smoke + strict contract-check + summary/artifacts + e2e test).
* [ ] After strict nightly stabilizes, return to `G5 follow-up`: extend machine-readable summaries for new smoke entrypoints by default.

## Blocked

* [ ] Archived track: self-conversion pipeline for `Qwen3-ASR-0.6B` -> OV IR.
  Status: `blocked_upstream` (`transformers/optimum` does not recognize `qwen3_asr`).
  Details and re-open criteria: `docs/ARCHIVED_TRACKS.md`.

## Done This Week

* [x] Git/GitHub tail cleanup: stale PR `#5` closed, stale `sync/docs` and hotfix branch-heads removed, open PR backlog cleaned down to zero; `release/wave6-security-hardening` preserved as a quarantined reference.
* [x] `release/wave6` selective recovery triage: quarantine verdict added to PR `#3` and runtime artifacts collected in `runs/20260312_232852-release-wave6-recovery-triage/` with breakdown `recover_now|recover_later|drop`.
* [x] `G2 daily triage loop`: refreshed stale local `readiness/governance/progress/transition` through the local manual fallback cycle (`execution_mode=accounted`), regenerated remediation/integrity/cadence snapshots, and synced docs to `docs/SESSION_2026-03-13.md`.
* [x] `G2 single-cycle helper`: added `scripts/run_gateway_sla_operating_cycle.py` + tests/runbook wiring; the live pass reused a fresh manual-backed latest snapshot without a new accounted run.
* [x] `G2.post4 Streamlit operating cycle visibility`: added a read-only block in `Latest Metrics` for `runs/nightly-gateway-sla-operating-cycle/operating_cycle_summary.json`; smoke contract extended with a new optional source without changing smoke-only `Safe Actions`.
* [x] `G2 switch override`: enabled stable nightly strict gate (`--critical-policy fail_nightly`) on explicit operator request without requiring `allow_switch`; transition summary preserved as a telemetry layer.
* [x] `G2 Conservative Gate`: locked Phase 0 baseline (`pytest=383`, `remaining_for_window=12`, `remaining_for_streak=3`, `allow_switch=false`) and execution policy `G2-only until go/no-go` in `TODO/RUNBOOK/DECISIONS/SESSION`.
* [x] `G2.4 remediation snapshot`: added read-only helper `check_gateway_sla_fail_nightly_remediation.py` with contract `gateway_sla_fail_nightly_remediation_v1`, candidate backlog buckets, and pytest coverage for green/hold/invalid/manual-guardrail scenarios.
* [x] `G2.5 nightly remediation integration`: wired remediation snapshot into `.github/workflows/gateway-sla-readiness-nightly.yml` as a `report_only` diagnostic layer with summary/artifact wiring and `always()` publication of G2 diagnostics on red nightly.
* [x] `G2.post2 Streamlit remediation visibility`: added the published remediation snapshot (`runs/nightly-gateway-sla-remediation/remediation_summary.json`) to `Latest Metrics` with a candidate backlog table and tolerant optional-source smoke semantics.
* [x] `G2.post3 integrity snapshot`: added read-only helper `check_gateway_sla_fail_nightly_integrity.py`, nightly summary/artifact wiring `runs/nightly-gateway-sla-integrity`, and a Streamlit `Latest Metrics` block for telemetry/dual-write/UTC guardrail verdict.
* [x] `Docs sync`: added session snapshots `docs/SESSION_2026-03-08.md` and `docs/SESSION_2026-03-12.md`; aligned `README.md`, `MANIFEST.md`, `TODO.md` with the current G2 snapshot.
* [x] M8.post: added historical view with filters (`source/status/limit`) in `Latest Metrics` for timestamped run snapshots from `runs/ci-smoke-*` (no external DB).
* [x] M8.post: added traceable audit trail to Streamlit `Safe Actions` (`Last safe action`, `Recent safe actions`, JSONL log `runs/.../ui-safe-actions/safe_actions_audit.jsonl`).
* [x] M8.post: added compact mobile layout policy (`breakpoint=768`) + regression smoke baseline (`viewport 390x844`, machine-readable `mobile_layout_contract_ok`).
* [x] G1 follow-up: added `gateway_sla_trend_snapshot_v1` (rolling baseline + breach drift) + CI summary/artifacts wiring on top of `gateway_sla_summary_v1`.
* [x] G1.1 follow-up: introduced a hardening policy layer for gateway HTTP errors (`retention=14d`, rotation `1MB x 5`, redaction `gateway_error_redaction_v1`) without changing the public gateway API contract.
* [x] G2 follow-up: added readiness checker `gateway_sla_fail_nightly_readiness_v1` + nightly workflow with cache-history and summary/artifacts (staged report, no hard gate).
* [x] G2.1 follow-up: added governance checker `gateway_sla_fail_nightly_governance_v1` + nightly go/no-go summary/artifacts (promotion rule `3` ready in a row, switch surface `nightly_only`).
* [x] G2.2 follow-up: added progress checker `gateway_sla_fail_nightly_progress_v1` + nightly decision-progress summary/artifacts (remaining window/streak, governance/readiness validity counters).
* [x] G2.manual follow-up: added UTC preflight helper `scripts/check_gateway_sla_manual_preflight.py` (`gateway_sla_manual_preflight_v1`) to `master` for checking calendar-day guardrail before manual `workflow_dispatch`.
* [x] G2.manual follow-up: added unified cycle-summary helper `scripts/check_gateway_sla_manual_cycle_summary.py` (`gateway_sla_manual_cycle_summary_v1`) for the operator loop (`preflight + readiness/governance/progress/transition`) in one machine-readable file.
* [x] G2.manual follow-up: added local manual nightly wrapper `scripts/run_gateway_sla_manual_nightly.py` (`gateway_sla_manual_nightly_runner_v1`) with local artifact UTC guardrail (`1 accounted run/day`), recovery path without progression credit, and fail-fast chain policy.
* [x] G2.manual follow-up: added local cadence brief helper `scripts/check_gateway_sla_manual_cadence_brief.py` (`gateway_sla_manual_cadence_brief_v1`) with `attention_state` and UTC forecast (`window/streak ETA`) for the daily operator loop without policy changes.
* [x] G2.post follow-up: added optional progress visibility block (`readiness/governance/progress`) to Streamlit `Latest Metrics` + smoke contract split `required_missing_sources|optional_missing_sources` without changing `signal_only` policy.
* [x] KAG Neo4j: raised rank for `star` to `first_hit_rank=1`.
* [x] KAG Neo4j: latency retuning after relevance uplift.
* [x] KAG Neo4j: added `--warmup-runs` to eval + A/B compare script.
* [x] Retrieval: added profile layer `baseline|ov_production`.
* [x] Voice runtime: default `whisper_genai`, archived `qwen_asr` via explicit opt-in.
* [x] Added runnable baselines: text-core OpenVINO, HUD OCR, HUD mod-hook.
* [x] Added KAG entrypoints: file baseline + Neo4j sync/query.
* [x] Added automation scaffold strictly in dry-run (`scripts/automation_dry_run.py`).
* [x] M6.2: locked `automation_plan_v1` contract + canonical demo scenarios (fixtures).
* [x] M6.3: added adapter `automation_intent_v1 -> automation_plan_v1` (`scripts/intent_to_automation_plan.py`) + regression tests.
* [x] M6.4: added unified smoke entrypoint `scripts/automation_intent_chain_smoke.py` + e2e regression tests.
* [x] M6.5: CI smoke extended with automation fixture scenarios (`automation_dry_run`, `automation_intent_chain_smoke`).
* [x] CI hygiene: locked 2 new lightweight scenarios for smoke-jobs without external runtime dependencies.
* [x] KAG quality guardrail: locked canonical profile (`sample|hard`) + runnable threshold-check (`scripts/check_kag_neo4j_guardrail.py`).
* [x] M6.6: formalized CI acceptance thresholds for automation smoke via `scripts/check_automation_smoke_contract.py` and workflow checks.
* [x] M5.3: added nightly workflow `.github/workflows/kag-neo4j-guardrail-nightly.yml` (`build -> sync -> eval(sample+hard) -> guardrail-check`).
* [x] M6.7: automation smoke checks now write machine-readable summaries (`--summary-json`) + CI report/artifact upload in the `pytest` workflow.
* [x] M5.4: added `scripts/kag_guardrail_trend_snapshot.py` + tests for comparing latest sample/hard guardrail metrics.
* [x] M6.8: locked troubleshooting playbook for automation smoke contract failures in `docs/RUNBOOK.md`.
* [x] M5.5: trend snapshot wired into nightly workflow (`GITHUB_STEP_SUMMARY` + artifact upload `runs/nightly-kag-trend`).
* [x] M6.9: added quick-link to runbook troubleshooting in the CI summary for automation smoke.
* [x] M5.6: added rolling-baseline comparison (N previous runs) + nightly summary fields to `kag_guardrail_trend_snapshot`.
* [x] M6.10: added the same quick-link to runbook troubleshooting in the nightly guardrail summary.
* [x] M5.7: added regression flags (`mrr`/`latency_p95`) for latest vs rolling-baseline to the trend snapshot.
* [x] M5.8: added severity rules (`warn`/`critical`) for regression flags (`mrr`/`latency_p95`) and delta thresholds.
* [x] M5.9: surfaced severity (`warn`/`critical`) in nightly trend summary and `trend_snapshot.json`.
* [x] M6.11: standardized quick-links format between `pytest` and nightly guardrail summaries.
* [x] M6.12: added unified helper/convention for building runbook links in workflow summaries.
* [x] M6.13: added optional `planning` metadata envelope (`intent_id/trace_id/adapter*`) to `automation_plan_v1` for integration with the upper planning layer.
* [x] M6.14: extended CI smoke with a second intent-chain fixture scenario (`check_inventory_tool`) with a separate contract-check and summary row.
* [x] M6.15: `check_automation_smoke_contract --summary-json` now propagates `planning.trace_id/intent_id` into `observed` (dry_run + intent_chain).
* [x] M6.16: added `trace_id/intent_id` columns from the contract summary to the CI step summary (`pytest` smoke) + canonical fixtures received trace metadata.
* [x] M6.17: enabled `--require-trace-id` in the intent-chain CI contract-check (canonical fixtures); missing trace id is now fail-fast.
* [x] M6.18: enabled `--require-intent-id` in the intent-chain CI contract-check (canonical fixtures); missing intent id is now fail-fast.
* [x] M6.19: locked rollout checklist for new `intent_type` in `docs/RUNBOOK.md` (fixture + smoke + strict contract-check + summary/artifacts + test).
* [x] G3 follow-up: completed rollout of new `intent_type=open_world_map` by checklist `M6.19` (fixture + smoke + strict contract-check + summary/artifacts + e2e test).
* [x] G3: added a unified machine-readable summary contract for core CI smoke (`phase_a_smoke`, `retrieve_demo`, `eval_retrieval`) through `scripts/collect_smoke_run_summary.py` + artifact upload in the `pytest` workflow.
* [x] G2: locked policy for `critical` trend severity — baseline `signal_only` (nightly signal without fail), with explicit opt-in `fail_nightly` through `--critical-policy`.
* [x] G2: calibrated latency severity thresholds in the trend snapshot against local `kag-neo4j-eval` history (`warn=5.0 ms`, `critical=15.0 ms`) to reduce noisy regression signals.
* [x] M7.0: added `scripts/gateway_v1_local.py` with `gateway_request_v1/gateway_response_v1` contract and artifact wiring (`request.json`, `run.json`, `response.json`, `child_runs/`).
* [x] M7.0: added `scripts/gateway_v1_smoke.py` (`core`, `automation`) + machine-readable `gateway_smoke_summary.json`.
* [x] M7.0: extended CI smoke with gateway scenarios (`runs/ci-smoke-gateway-core`, `runs/ci-smoke-gateway-automation`) and summary table.
* [x] M7.1: added `scripts/gateway_v1_http_service.py` (`GET /healthz`, `POST /v1/gateway`) as a thin-wrapper over `run_gateway_request`.
* [x] M7.1: added `scripts/gateway_v1_http_smoke.py` (`core`, `automation`) + machine-readable `gateway_http_smoke_summary.json`.
* [x] M7.1: extended CI smoke with HTTP scenarios (`runs/ci-smoke-gateway-http-core`, `runs/ci-smoke-gateway-http-automation`) and summary section.
* [x] M7.2: added runtime limits (`request size`, `json depth/string/array/object`) and timeout policy (`operation_timeout -> HTTP 504`) to `gateway_v1_http_service`.
* [x] M7.2: sanitized internal error path (`internal_error_sanitized` to client, traceback to `gateway_http_errors.jsonl` locally).
* [x] M7.2: added contract parity matrix test `CLI vs HTTP` across 4 operations + extended HTTP hardening tests/smoke summary fields.
* [x] M8.0: added decision-complete IA spec `docs/STREAMLIT_IA_V0.md` (4 zones, data contracts, flows, safe guardrails).
* [x] M8.0: added doc-contract regression test `tests/test_streamlit_ia_doc.py` to protect IA against drift.
* [x] M8.1: implemented `scripts/streamlit_operator_panel.py` (4 zones per IA) with canonical sources, health/read-model loaders, and whitelisted safe actions.
* [x] M8.1: added `scripts/streamlit_operator_panel_smoke.py` (`streamlit_smoke_summary_v1`, exit policy `0|2`, no-crash startup gate).
* [x] M8.1: extended CI smoke with a Streamlit step + summary section + artifact upload (`runs/ci-smoke-streamlit/streamlit_smoke_summary.json`).
* [x] M7.post: extended gateway smoke summaries with observability metrics (`latency_*`, `error_buckets`, timestamps/duration, failed counters).
* [x] M7.post: added SLA checker `scripts/check_gateway_sla.py` + `gateway_sla_summary_v1` (`profile`, `policy`, `breaches`, `exit_code`).
* [x] M7.post: extended CI smoke with an SLA step (`signal_only`) + summary section + artifact upload (`runs/ci-smoke-gateway-sla/gateway_sla_summary.json`).
* [x] Added weekly review template: `docs/SESSION_WEEKLY_TEMPLATE.md`.
* [x] Simplified `README.md`: status block moved to a canonical-doc-links format.
* [x] Updated `MANIFEST.md` to a short snapshot format (date, capabilities, canonical links).

## Always Rules (No Checkboxes)

* Any substantial architecture decision is recorded in `docs/DECISIONS.md`.
* When commands/setup change, update `docs/RUNBOOK.md`.
* Keep detailed run artifacts and long chronologies in `docs/SESSION_*.md`, not in `TODO.md`.
* Never commit: `models/`, `data/` dumps, `runs/`, `.codex/**/logs/`, secrets/tokens.
