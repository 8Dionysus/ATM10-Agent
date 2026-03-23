# MANIFEST.md

Current as of: 2026-03-23

## Snapshot

- Project: `atm10-agent`
- Target platform: Windows 11 + PowerShell 7
- Target Python: 3.11+ (validated on 3.12.10)
- Current test status: `python -m pytest` green (see CI and this manifest for the current public snapshot).

## Active capabilities

- Phase A: `scripts/phase_a_smoke.py` (screenshot -> run artifacts).
- Phase B retrieval: `normalize -> retrieve -> eval` + profile layer `baseline|ov_production`.
- KAG: file baseline + Neo4j (`build -> sync -> query -> eval`).
- Hybrid planner: `scripts/hybrid_query_demo.py` + additive `hybrid_query` gateway flow with `baseline_first` default (`retrieval first -> file KAG expansion -> RRF merge`) and additive `combo_a` parity profile (`qdrant + neo4j`), with retrieval-only fallback on KAG degradation.
- Cross-service SLA + benchmark suite: `scripts/cross_service_benchmark_suite.py` + normalized `service_sla_summary_v1` artifacts for `voice_asr`, `voice_tts`, `retrieval`, and `kag`, aggregated into `cross_service_benchmark_suite_v1`, with `baseline_first` default and additive `profile=combo_a` (`voice_runtime_service + tts_runtime_service + qdrant + neo4j`).
- KAG nightly guardrail: `.github/workflows/kag-neo4j-guardrail-nightly.yml`.
- Combo A live parity workflow: `.github/workflows/combo-a-profile-smoke.yml` (`workflow_dispatch` + nightly schedule, external `Qdrant`/`Neo4j`, live operator snapshot capture, combo_a gateway smoke, combo_a cross-service suite, combo_a nightly operating-cycle decision surface, promoted strict `fail_on_hold` only when eligible).
- Trend snapshot: `scripts/kag_guardrail_trend_snapshot.py` (rolling-baseline + severity flags + `critical_policy`).
- Automation: dry-run stack (`automation_dry_run`, `intent_to_automation_plan`, `automation_intent_chain_smoke`, `check_automation_smoke_contract`).
- Automation intents: canonical templates include `open_quest_book`, `check_inventory_tool`, `open_world_map`; the public intent -> plan -> dry-run chain has rollout records for all three under `M6.19`.
- CI core smoke summaries: `scripts/collect_smoke_run_summary.py` (`phase_a_smoke|retrieve_demo|eval_retrieval` -> `smoke_summary.json`).
- Gateway SLA trend: `scripts/gateway_sla_trend_snapshot.py` (`gateway_sla_summary_v1` history -> `gateway_sla_trend_snapshot_v1`).
- Gateway fail_nightly readiness: `scripts/check_gateway_sla_fail_nightly_readiness.py` (`gateway_sla_fail_nightly_readiness_v1`).
- Gateway fail_nightly governance: `scripts/check_gateway_sla_fail_nightly_governance.py` (`gateway_sla_fail_nightly_governance_v1`).
- Gateway fail_nightly progress: `scripts/check_gateway_sla_fail_nightly_progress.py` (`gateway_sla_fail_nightly_progress_v1`).
- Gateway fail_nightly remediation: `scripts/check_gateway_sla_fail_nightly_remediation.py` (`gateway_sla_fail_nightly_remediation_v1`).
- Gateway fail_nightly integrity: `scripts/check_gateway_sla_fail_nightly_integrity.py` (`gateway_sla_fail_nightly_integrity_v1`).
- Gateway manual fallback loop: `scripts/run_gateway_sla_manual_nightly.py` + `scripts/check_gateway_sla_manual_cycle_summary.py` + `scripts/check_gateway_sla_manual_cadence_brief.py`.
- Gateway single-cycle operator helper: `scripts/run_gateway_sla_operating_cycle.py` (`gateway_sla_operating_cycle_v1`, promoted-policy decision surface with `effective_policy/promotion_state/next_review_at_utc`, plus reuse-fresh-latest or manual-fallback execution).
- Gateway SLA readiness nightly: `.github/workflows/gateway-sla-readiness-nightly.yml` with `readiness/governance/progress/transition/remediation/integrity/operating_cycle` summary/artifact wiring and promoted `fail_nightly` strict gate only when the operating cycle marks baseline eligible.
- Gateway operator APIs: `GET /v1/operator/snapshot`, `GET /v1/operator/runs`, `GET /v1/operator/history`, `GET /v1/operator/safe-actions`, `POST /v1/operator/safe-actions/run` from `scripts/gateway_v1_http_service.py`, with additive `supported_profiles`, `operator_context.profiles.combo_a`, startup/governance surfaces, compact `operator_context.triage`, promoted baseline SLA policy posture, additive `combo_a` nightly policy posture, and `combo_a` smoke/suite/operating-cycle sources in run/history views.
- Streamlit operator panel: `scripts/streamlit_operator_panel.py` + `scripts/streamlit_operator_panel_smoke.py`, with gateway-first `Stack Health`, `Run Explorer`, `Latest Metrics`, gateway-mediated smoke-only `Safe Actions`, scenario-first operator blocks for compact operator triage + startup-session + baseline SLA policy posture, and profile-aware baseline vs `combo_a` rows/actions including `Combo A Promotion` in the existing tabs.
- Observer pilot runtime slice: `scripts/pilot_runtime_loop.py` + `scripts/pilot_turn_smoke.py`, with local `F8` push-to-talk, Windows `monitor|region` screen capture, `Whisper GenAI -> OpenVINO VLM -> gateway hybrid_query(profile=combo_a) -> OpenVINO grounded reply -> tts_runtime_service`, plus additive ATM10 evidence artifacts `atm10_session_probe_v1` and `live_hud_state_v1` written next to each `pilot_turn_v1`.
- Observer pilot readiness helper: `scripts/check_pilot_runtime_readiness.py`, publishing `pilot_runtime_readiness_v1` from the latest startup artifact, pilot runtime status, referenced pilot turn, ATM10 session probe, and live HUD artifact, with `ready|attention|blocked` acceptance posture and manual next-step guidance.
- Primary operator startup profile: `scripts/start_operator_product.py` (canonical local launch path for `gateway + Streamlit`, with opt-in managed `voice_runtime_service` / `tts_runtime_service` / `pilot_runtime`, external `Qdrant` / `Neo4j` readiness URLs, `startup_plan.json`, session-state checkpoints, and artifact pointers for the operator surface).
- Operator snapshot and Streamlit pilot surfaces: `scripts/operator_product_snapshot.py` and `scripts/streamlit_operator_panel.py` additively publish `operator_context.pilot_runtime`, `operator_context.last_turn_summary`, `operator_context.pilot_readiness`, and ATM10 session/HUD evidence summaries in the `Pilot runtime` / `Pilot readiness` sections of `Stack Health`.
- Dependency profiles: `requirements-voice.txt`, `requirements-llm.txt`, `requirements-export.txt`, `requirements-audit.txt`.
- Dependency audit: `scripts/dependency_audit.py` + report-only CI step with uploaded `dependency-audit-report` artifact.

## Canonical docs

- Current public status: `MANIFEST.md`
- Public roadmap: `ROADMAP.md`
- Runnable commands: `docs/RUNBOOK.md`
- Doc roles/policy: `docs/SOURCE_OF_TRUTH.md`
- Archived tracks: `docs/ARCHIVED_TRACKS.md`

## Public docs boundary

- Local maintainer working docs are ignored and intentionally not part of the public repo surface.
- Future internal-only notes, session chronology, and PR/release scratch docs belong under ignored `docs/internal/**`.
- Local session notes/templates and PR coordination docs are ignored and do not ship in the public repo tree.

## Data/commit policy (short)

Never commit:

- `models/**`
- `data/**` dumps
- `runs/**`
- `.codex/**/logs/**`
- secrets/tokens
