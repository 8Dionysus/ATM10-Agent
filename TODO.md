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

## Status Snapshot (as of 2026-02-22)

* M0/M1/M2/M3 базово закрыты.
* `python -m pytest` green (см. последний session snapshot и CI).
* Active ASR path: `whisper_genai`; `qwen_asr` — archived/recoverable opt-in.
* KAG Neo4j path валидирован (`build -> sync -> query -> eval`, hard-cases uplift + latency tuning).

## WIP Policy

* Максимум активных задач одновременно: **3**.
* Новую задачу берем только после закрытия/перевода текущей в `Blocked`.

## Now (WIP <= 3)

* [ ] M6.2: определить следующий practical шаг после `automation_dry_run` (без реальных input events).
* [ ] CI hygiene: решить, какие новые runnable scripts добавить в smoke-jobs (по 1–2 ключевых сценария).
* [ ] KAG quality guardrail: зафиксировать canonical benchmark profile для regression-check (sample + hard, warmup policy).

## Next

* [ ] Подготовить короткий weekly review шаблон для `docs/SESSION_*.md` (1 экран: что улучшили/что блокирует/что дальше).
* [ ] Упростить README status-блок до ссылок на каноничные документы (без дублирования длинных списков).

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

## Always Rules (No Checkboxes)

* Любое существенное архитектурное решение фиксируем в `docs/DECISIONS.md`.
* При изменении команд/setup обновляем `docs/RUNBOOK.md`.
* Детальные run artifacts и длинные хронологии держим в `docs/SESSION_*.md`, а не в `TODO.md`.
* Never commit: `models/`, `data/` dumps, `runs/`, `.codex/**/logs/`, секреты/токены.
