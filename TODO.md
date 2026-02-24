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

## Status Snapshot (as of 2026-02-24)

* M0/M1/M2/M3 базово закрыты.
* `python -m pytest` green (см. последний session snapshot и CI).
* Active ASR path: `whisper_genai`; `qwen_asr` — archived/recoverable opt-in.
* KAG Neo4j path валидирован (`build -> sync -> query -> eval`, hard-cases uplift + latency tuning).

## Session Focus (2026-02-24)

* Зафиксировать execution-приоритет `M7`: unified local gateway (Combo A service foundation).
* Запустить `M8` planning для Streamlit operator panel v0 (health, runs explorer, latest metrics, safe smoke triggers).
* Синхронизировать source-of-truth документы под курс `Combo A + Streamlit` без привязки к перемещаемым audit-файлам.

## WIP Policy

* Максимум активных задач одновременно: **3**.
* Новую задачу берем только после закрытия/перевода текущей в `Blocked`.

## Now (WIP <= 3)

* [ ] M7.0: зафиксировать минимальный API contract v1 для gateway (`health`, `retrieval`, `kag_query`, `automation_dry_run`) и error contract.
* [ ] M8.0: определить IA для Streamlit panel v0 (вкладки/экраны + источники данных + links на artifacts).
* [ ] M8.1: подготовить smoke-gate для Streamlit entrypoint (no-crash запуск + machine-readable summary).

## Next

* [ ] G1 follow-up: при следующем новом `intent_type` применить checklist `M6.19` (fixture + smoke + strict contract-check + summary/artifacts + e2e test).
* [ ] G2 follow-up: переоценить readiness для `critical_policy=fail_nightly` после накопления стабильной nightly истории.
* [ ] G5 follow-up: расширять machine-readable summaries для новых smoke entrypoints по умолчанию.

## Blocked

* [ ] Archived track: self-conversion pipeline для `Qwen3-ASR-0.6B` -> OV IR.
  Статус: `blocked_upstream` (`transformers/optimum` не распознает `qwen3_asr`).
  Детали и критерии re-open: `docs/ARCHIVED_TRACKS.md`.

## Done This Week

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
* [x] G3: для core CI smoke (`phase_a_smoke`, `retrieve_demo`, `eval_retrieval`) добавлен единый machine-readable summary контракт через `scripts/collect_smoke_run_summary.py` + artifact upload в `pytest` workflow.
* [x] G2: зафиксирован policy для `critical` trend severity — baseline `signal_only` (nightly signal без fail), с explicit opt-in `fail_nightly` через `--critical-policy`.
* [x] G2: по локальной истории `kag-neo4j-eval` откалиброваны latency severity thresholds в trend snapshot (`warn=5.0 ms`, `critical=15.0 ms`) для снижения noisy regression-сигналов.
* [x] Добавлен weekly review шаблон: `docs/SESSION_WEEKLY_TEMPLATE.md`.
* [x] Упрощен `README.md`: status-блок переведен в формат ссылок на каноничные документы.
* [x] Обновлен `MANIFEST.md` до короткого snapshot-формата (дата, capabilities, canonical links).

## Always Rules (No Checkboxes)

* Любое существенное архитектурное решение фиксируем в `docs/DECISIONS.md`.
* При изменении команд/setup обновляем `docs/RUNBOOK.md`.
* Детальные run artifacts и длинные хронологии держим в `docs/SESSION_*.md`, а не в `TODO.md`.
* Never commit: `models/`, `data/` dumps, `runs/`, `.codex/**/logs/`, секреты/токены.
