# TODO.md — atm10-agent

Русский — основной язык. English terms — только как устоявшиеся термины (Quickstart, Phase, smoke test, RAG, VLM, artifacts, run, tests, boundaries).

Правило выполнения: small, reviewable diffs + runnable commands + минимум 1 test на заметное изменение поведения.

## Source Of Truth

Каноничная карта документов: `docs/SOURCE_OF_TRUTH.md`.

Кратко:

* `TODO.md` — пошаговый execution-план (что делаем сейчас и следующим шагом).
* `PLANS.md` — цели, milestones, DoD и ограничения (почему и куда идем).
* `docs/SESSION_*.md` — подробная хронология run artifacts и экспериментов.
* `docs/DECISIONS.md` — архитектурные решения (1–3 bullets на change).
* `docs/RUNBOOK.md` — runnable команды и операционные профили.
* `docs/ARCHIVED_TRACKS.md` — archived/recoverable направления.

## Status Snapshot (as of 2026-03-03)

* M0/M1/M2/M3 базово закрыты.
* `python -m pytest` green (см. последний session snapshot и CI).
* Active ASR path: `whisper_genai`; `qwen_asr` — archived/recoverable opt-in.
* KAG Neo4j path валидирован (`build -> sync -> query -> eval`, hard-cases uplift + latency tuning).

## Session Focus (2026-03-03)

* Закрыть git/docs housekeeping после rollout `open_world_map` и синхронизировать source-of-truth ссылки на актуальную сессию.
* Продолжить `G2` follow-up по nightly readiness accumulation (`window=14`, governance streak gate).
* Держать `G5` follow-up: расширять machine-readable summaries для новых smoke entrypoints по умолчанию.

## WIP Policy

* Максимум активных задач одновременно: **3**.
* Новую задачу берем только после закрытия/перевода текущей в `Blocked`.

## Now (WIP <= 3)

* [ ] G2 follow-up: накопить минимум 14 валидных nightly readiness snapshots и пройти governance-гейт (`>=3` ready подряд) для go/no-go решения по switch в `critical_policy=fail_nightly`; прогресс и remaining-gap отслеживать через `runs/nightly-gateway-sla-progress/progress_summary.json`.

## Next

* [ ] G3 follow-up (next intent template): при добавлении следующего нового `intent_type` применить checklist `M6.19` (fixture + smoke + strict contract-check + summary/artifacts + e2e test).
* [ ] G5 follow-up: расширять machine-readable summaries для новых smoke entrypoints по умолчанию.

## Blocked

* [ ] Archived track: self-conversion pipeline для `Qwen3-ASR-0.6B` -> OV IR.
  Статус: `blocked_upstream` (`transformers/optimum` не распознает `qwen3_asr`).
  Детали и критерии re-open: `docs/ARCHIVED_TRACKS.md`.

## Done This Week

* [x] M8.post: во вкладке `Latest Metrics` добавлен historical view с filters (`source/status/limit`) по timestamp run snapshots из `runs/ci-smoke-*` (без внешней БД).
* [x] M8.post: в Streamlit `Safe Actions` добавлен traceable audit trail (`Last safe action`, `Recent safe actions`, JSONL лог `runs/.../ui-safe-actions/safe_actions_audit.jsonl`).
* [x] M8.post: добавлен compact mobile layout policy (`breakpoint=768`) + regression smoke baseline (`viewport 390x844`, machine-readable `mobile_layout_contract_ok`).
* [x] G1 follow-up: добавлен `gateway_sla_trend_snapshot_v1` (rolling baseline + breach drift) + CI summary/artifacts wiring поверх `gateway_sla_summary_v1`.
* [x] G1.1 follow-up: введен hardening policy-layer для gateway HTTP errors (`retention=14d`, rotation `1MB x 5`, redaction `gateway_error_redaction_v1`) без изменения публичного gateway API контракта.
* [x] G2 follow-up: добавлен readiness checker `gateway_sla_fail_nightly_readiness_v1` + nightly workflow с cache-history и summary/artifacts (staged report, без hard-gate).
* [x] G2.1 follow-up: добавлен governance checker `gateway_sla_fail_nightly_governance_v1` + nightly go/no-go summary/artifacts (promotion rule `3` ready подряд, switch surface `nightly_only`).
* [x] G2.2 follow-up: добавлен progress checker `gateway_sla_fail_nightly_progress_v1` + nightly decision-progress summary/artifacts (remaining window/streak, governance/readiness validity counters).
* [x] G2.manual follow-up: в `master` добавлен UTC preflight helper `scripts/check_gateway_sla_manual_preflight.py` (`gateway_sla_manual_preflight_v1`) для проверки calendar-day guardrail перед ручным `workflow_dispatch`.
* [x] G2.manual follow-up: добавлен unified cycle-summary helper `scripts/check_gateway_sla_manual_cycle_summary.py` (`gateway_sla_manual_cycle_summary_v1`) для operator-loop (`preflight + readiness/governance/progress/transition`) в одном machine-readable файле.
* [x] G2.post follow-up: в Streamlit `Latest Metrics` добавлен optional progress visibility блок (`readiness/governance/progress`) + smoke contract split `required_missing_sources|optional_missing_sources` без изменения `signal_only` policy.
* [x] KAG Neo4j: поднят rank для `star` до `first_hit_rank=1`.
* [x] KAG Neo4j: latency retuning после relevance uplift.
* [x] KAG Neo4j: добавлен `--warmup-runs` в eval + A/B compare script.
* [x] Retrieval: добавлен profile-layer `baseline|ov_production`.
* [x] Voice runtime: default `whisper_genai`, archived `qwen_asr` через explicit opt-in.
* [x] Добавлены runnable baselines: text-core OpenVINO, HUD OCR, HUD mod-hook.
* [x] Добавлены KAG entrypoints: file baseline + Neo4j sync/query.
* [x] Добавлен automation scaffold строго в dry-run (`scripts/automation_dry_run.py`).
* [x] M6.2: зафиксирован `automation_plan_v1` контракт + canonical demo scenarios (fixtures).
* [x] M6.3: добавлен adapter `automation_intent_v1 -> automation_plan_v1` (`scripts/intent_to_automation_plan.py`) + regression tests.
* [x] M6.4: добавлен unified smoke entrypoint `scripts/automation_intent_chain_smoke.py` + e2e regression tests.
* [x] M6.5: CI smoke расширен automation fixture-сценариями (`automation_dry_run`, `automation_intent_chain_smoke`).
* [x] CI hygiene: для smoke-jobs зафиксированы 2 новых lightweight сценария без внешних runtime зависимостей.
* [x] KAG quality guardrail: зафиксирован canonical profile (`sample|hard`) + runnable threshold-check (`scripts/check_kag_neo4j_guardrail.py`).
* [x] M6.6: формализованы CI acceptance thresholds для automation smoke через `scripts/check_automation_smoke_contract.py` и workflow checks.
* [x] M5.3: добавлен nightly workflow `.github/workflows/kag-neo4j-guardrail-nightly.yml` (`build -> sync -> eval(sample+hard) -> guardrail-check`).
* [x] M6.7: automation smoke checks пишут machine-readable summaries (`--summary-json`) + CI report/artifact upload в `pytest` workflow.
* [x] M5.4: добавлен `scripts/kag_guardrail_trend_snapshot.py` + tests для сравнения latest sample/hard guardrail метрик.
* [x] M6.8: зафиксирован troubleshooting playbook по падениям automation smoke contract checks в `docs/RUNBOOK.md`.
* [x] M5.5: trend snapshot встроен в nightly workflow (`GITHUB_STEP_SUMMARY` + artifact upload `runs/nightly-kag-trend`).
* [x] M6.9: в CI summary automation smoke добавлен quick-link на runbook troubleshooting (`M6.8`).
* [x] M5.6: в `kag_guardrail_trend_snapshot` добавлен rolling-baseline comparison (N previous runs) + nightly summary поля.
* [x] M6.10: quick-link на runbook troubleshooting добавлен и в nightly guardrail summary.
* [x] M5.7: в trend snapshot добавлены regression-флаги (`mrr`/`latency_p95`) для latest vs rolling-baseline.
* [x] M5.8: добавлены severity-правила (`warn`/`critical`) для regression-флагов (`mrr`/`latency_p95`) и пороги дельт.
* [x] M5.9: severity (`warn`/`critical`) выведен в nightly trend summary и `trend_snapshot.json`.
* [x] M6.11: формат quick-links унифицирован между `pytest` и nightly guardrail summaries.
* [x] M6.12: добавлен единый helper/конвенция для build runbook links в workflow summaries.
* [x] M6.13: в `automation_plan_v1` добавлен optional `planning` metadata envelope (`intent_id/trace_id/adapter*`) для интеграции с верхним planning-слоем.
* [x] M6.14: CI smoke расширен вторым intent-chain fixture-сценарием (`check_inventory_tool`) с отдельным contract-check и summary row.
* [x] M6.15: `check_automation_smoke_contract --summary-json` теперь пробрасывает `planning.trace_id/intent_id` в `observed` (dry_run + intent_chain).
* [x] M6.16: в CI step summary (`pytest` smoke) добавлены колонки `trace_id/intent_id` из contract summary + canonical fixtures получили trace metadata.
* [x] M6.17: в intent-chain CI contract-check включен `--require-trace-id` (canonical fixtures), отсутствие trace id теперь fail-fast.
* [x] M6.18: в intent-chain CI contract-check включен `--require-intent-id` (canonical fixtures), отсутствие intent id теперь fail-fast.
* [x] M6.19: в `docs/RUNBOOK.md` зафиксирован policy-чеклист rollout новых `intent_type` (fixture + smoke + strict contract-check + summary/artifacts + test).
* [x] G3 follow-up: выполнен rollout нового `intent_type=open_world_map` по checklist `M6.19` (fixture + smoke + strict contract-check + summary/artifacts + e2e test).
* [x] G3: для core CI smoke (`phase_a_smoke`, `retrieve_demo`, `eval_retrieval`) добавлен единый machine-readable summary контракт через `scripts/collect_smoke_run_summary.py` + artifact upload в `pytest` workflow.
* [x] G2: зафиксирован policy для `critical` trend severity — baseline `signal_only` (nightly signal без fail), с explicit opt-in `fail_nightly` через `--critical-policy`.
* [x] G2: по локальной истории `kag-neo4j-eval` откалиброваны latency severity thresholds в trend snapshot (`warn=5.0 ms`, `critical=15.0 ms`) для снижения noisy regression-сигналов.
* [x] M7.0: добавлен `scripts/gateway_v1_local.py` c `gateway_request_v1/gateway_response_v1` контрактом и artifact wiring (`request.json`, `run.json`, `response.json`, `child_runs/`).
* [x] M7.0: добавлен `scripts/gateway_v1_smoke.py` (`core`, `automation`) + machine-readable `gateway_smoke_summary.json`.
* [x] M7.0: CI smoke расширен gateway scenarios (`runs/ci-smoke-gateway-core`, `runs/ci-smoke-gateway-automation`) и summary table.
* [x] M7.1: добавлен `scripts/gateway_v1_http_service.py` (`GET /healthz`, `POST /v1/gateway`) как thin-wrapper над `run_gateway_request`.
* [x] M7.1: добавлен `scripts/gateway_v1_http_smoke.py` (`core`, `automation`) + machine-readable `gateway_http_smoke_summary.json`.
* [x] M7.1: CI smoke расширен HTTP scenarios (`runs/ci-smoke-gateway-http-core`, `runs/ci-smoke-gateway-http-automation`) и summary section.
* [x] M7.2: в `gateway_v1_http_service` добавлены runtime limits (`request size`, `json depth/string/array/object`) и timeout policy (`operation_timeout -> HTTP 504`).
* [x] M7.2: internal error path санитизирован (`internal_error_sanitized` клиенту, traceback в `gateway_http_errors.jsonl` локально).
* [x] M7.2: добавлен contract parity matrix test `CLI vs HTTP` по 4 операциям + расширены HTTP hardening tests/smoke summary fields.
* [x] M8.0: добавлен decision-complete IA spec `docs/STREAMLIT_IA_V0.md` (4 зоны, data contracts, flows, safe guardrails).
* [x] M8.0: добавлен doc-contract regression test `tests/test_streamlit_ia_doc.py` для защиты IA от drift.
* [x] M8.1: реализован `scripts/streamlit_operator_panel.py` (4 зоны по IA) с canonical sources, health/read-model loaders и whitelisted safe actions.
* [x] M8.1: добавлен `scripts/streamlit_operator_panel_smoke.py` (`streamlit_smoke_summary_v1`, exit policy `0|2`, no-crash startup gate).
* [x] M8.1: CI smoke расширен streamlit шагом + summary section + artifact upload (`runs/ci-smoke-streamlit/streamlit_smoke_summary.json`).
* [x] M7.post: gateway smoke summaries расширены observability метриками (`latency_*`, `error_buckets`, timestamps/duration, failed counters).
* [x] M7.post: добавлен SLA checker `scripts/check_gateway_sla.py` + `gateway_sla_summary_v1` (`profile`, `policy`, `breaches`, `exit_code`).
* [x] M7.post: CI smoke расширен SLA step (`signal_only`) + summary section + artifact upload (`runs/ci-smoke-gateway-sla/gateway_sla_summary.json`).
* [x] Добавлен weekly review шаблон: `docs/SESSION_WEEKLY_TEMPLATE.md`.
* [x] Упрощен `README.md`: status-блок переведен в формат ссылок на каноничные документы.
* [x] Обновлен `MANIFEST.md` до короткого snapshot-формата (дата, capabilities, canonical links).

## Always Rules (No Checkboxes)

* Любое существенное архитектурное решение фиксируем в `docs/DECISIONS.md`.
* При изменении команд/setup обновляем `docs/RUNBOOK.md`.
* Детальные run artifacts и длинные хронологии держим в `docs/SESSION_*.md`, а не в `TODO.md`.
* Never commit: `models/`, `data/` dumps, `runs/`, `.codex/**/logs/`, секреты/токены.
