# PLANS.md — atm10-agent

Русский — основной язык. English terms используем там, где это устоявшиеся термины (Phase, Quickstart, smoke test, RAG, VLM, artifacts, run, tests, boundaries).

## Source Of Truth

Каноничная карта документов: `docs/SOURCE_OF_TRUTH.md`.

Роли документов:

* `TODO.md` — пошаговое исполнение (Now/Next/Blocked, WIP-limit).
* `PLANS.md` — цели проекта, milestones, DoD, риски.
* `docs/SESSION_*.md` — подробная история экспериментов и artifacts.
* `docs/ARCHIVED_TRACKS.md` — archived/recoverable направления.

## North Star

Сделать local “game companion” для ATM10:

* Phase A: vision loop (screenshot -> VLM interface -> structured output + artifacts)
* Phase B: memory (RAG / retrieval / KAG)
* Phase C: voice (active ASR path; TTS archived)
* Automation: только safe assistive path, default dry-run

## Constraints

* OS: Windows 11 + PowerShell 7 (first-class).
* Dev loop: small, reviewable diffs + reproducible commands + tests/smoke.
* Paths: `pathlib`, без hardcoded machine-specific путей.
* Data hygiene: не коммитим модели/дампы/артефакты/секреты.
* Model policy: core stack = `Qwen3`; без замены на `Qwen2.5*`.
* Runtime policy: `OpenVINO-first`.
* WIP limit (execution): максимум 3 активные задачи одновременно.

## Milestone Map

### Completed

* M0: Instance discovery & repo hygiene.
* M1: Phase A vision loop baseline.
* M2: Phase B retrieval baseline + benchmark + profile defaults.
* M2.1: LF/CRLF policy.
* M3: Voice runtime operational path (active ASR + archived policy).
* M3.1: OpenVINO rollout (text-core + retrieval profile).
* M4: HUD assistance baselines (OCR + mod-hook).
* M5: KAG baseline + Neo4j path + benchmark ladder.
* M6.0: Automation safe scaffold (dry-run only).

### Active Goals

#### G1 — M6.1 Automation Safe Loop (next step)

Goal:

* Связать intent/planning слой с `automation_dry_run` без перехода к real input events.

Definition of Done:

* Есть runnable path: `intent -> action-plan JSON -> dry-run validation/execution plan`.
* Есть минимум 1 regression test на контракт action-plan.
* Артефакты пишутся в `runs/<timestamp>-automation-dry-run/`.

Open tasks:

* Поддерживать актуальным policy-чеклист `M6.19` в `docs/RUNBOOK.md` при каждом новом `intent_type` (fixture + smoke + contract-check + summary + artifacts + test).

#### G2 — KAG Quality/Latency Guardrail

Goal:

* Держать стабильный quality/latency baseline по sample+hard eval-наборам.

Definition of Done:

* Есть canonical benchmark profile (включая warmup policy) в runbook.
* Любая правка ранжирования проверяется на sample/hard без regressions по agreed thresholds.

Open tasks:

* Продолжать мониторинг nightly истории и при необходимости пересматривать severity thresholds (`warn`/`critical`) относительно обновленного baseline (`latency_warn=5.0`, `latency_critical=15.0`).
* Переоценивать readiness для перехода `critical_policy=fail_nightly` (с текущего baseline `signal_only`) после накопления стабильной истории nightly без noisy false positives.

#### G3 — CI Smoke Expansion

Goal:

* Расширить CI smoke на новые runnable entrypoints без роста flaky-риска.

Definition of Done:

* Добавлены 1–2 новых smoke-сценария, которые стабильны на CI.
* Runbook и decisions синхронизированы.

Open tasks:

* Поддерживать единый helper-конвенции для runbook links (`scripts/build_runbook_link.py`) во всех новых CI summaries.
* Добавлять machine-readable smoke summaries для каждого нового smoke entrypoint по умолчанию (core smoke через `scripts/collect_smoke_run_summary.py`, automation через `check_automation_smoke_contract --summary-json`).

## Archived Tracks

Все archived/recoverable направления вынесены в:

* `docs/ARCHIVED_TRACKS.md`

Текущее ключевое archived направление:

* `Qwen3-ASR-0.6B` self-conversion pipeline (upstream blocker).

## Risks & Mitigations

* Risk: застрять в infra/model-деталях вместо product loop.
  Mitigation: milestone gates + DoD + короткий execution-cycle в `TODO.md`.

* Risk: разрастание документации и дубли.
  Mitigation: строгая роль документов через `docs/SOURCE_OF_TRUTH.md`.

* Risk: scope creep (voice + KAG + automation одновременно).
  Mitigation: WIP-limit=3 и явный список `Now`/`Blocked`.
