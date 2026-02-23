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

## Status Snapshot (as of 2026-02-23)

* M0/M1/M2/M3 базово закрыты.
* `python -m pytest` green (см. последний session snapshot и CI).
* Active ASR path: `whisper_genai`; `qwen_asr` — archived/recoverable opt-in.
* KAG Neo4j path валидирован (`build -> sync -> query -> eval`, hard-cases uplift + latency tuning).

## Session Focus (2026-02-23)

* Закрыть `M5.4`: trend snapshot по nightly KAG guardrail.
* Закрыть `M6.8`: troubleshooting playbook для automation smoke contract failures.
* Закрыть `M5.5`: встроить trend snapshot в nightly summary/report path.

## WIP Policy

* Максимум активных задач одновременно: **3**.
* Новую задачу берем только после закрытия/перевода текущей в `Blocked`.

## Now (WIP <= 3)

* [ ] M5.8: добавить severity-правила для regression-флагов (`warn`/`critical`) по mrr/p95 дельтам.
* [ ] M6.11: унифицировать формат quick-links в CI summaries (`pytest` + nightly guardrail).

## Next

* [ ] M5.9: вывести severity (`warn`/`critical`) в nightly trend summary и `trend_snapshot.json`.
* [ ] M6.12: добавить единый helper/конвенцию для build runbook links в workflow summaries.

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
* [x] Добавлен weekly review шаблон: `docs/SESSION_WEEKLY_TEMPLATE.md`.
* [x] Упрощен `README.md`: status-блок переведен в формат ссылок на каноничные документы.
* [x] Обновлен `MANIFEST.md` до короткого snapshot-формата (дата, capabilities, canonical links).

## Always Rules (No Checkboxes)

* Любое существенное архитектурное решение фиксируем в `docs/DECISIONS.md`.
* При изменении команд/setup обновляем `docs/RUNBOOK.md`.
* Детальные run artifacts и длинные хронологии держим в `docs/SESSION_*.md`, а не в `TODO.md`.
* Never commit: `models/`, `data/` dumps, `runs/`, `.codex/**/logs/`, секреты/токены.
