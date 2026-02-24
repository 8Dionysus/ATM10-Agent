# PLANS.md — atm10-agent

Русский — основной язык. English terms используем только как устоявшиеся термины (Phase, smoke, RAG, KAG, artifacts, DoD, guardrail, gateway).

## Source Of Truth

Каноничная карта документов: `docs/SOURCE_OF_TRUTH.md`.

Роли документов:

* `TODO.md` — пошаговое исполнение (Now/Next/Blocked, WIP-limit).
* `PLANS.md` — цели, milestones, Definition of Done, риски.
* `docs/SESSION_*.md` — подробная хронология запусков и artifacts.
* `docs/ARCHIVED_TRACKS.md` — archived/recoverable направления.

## Strategic Baseline (as of 2026-02-24)

Выбран стратегический baseline:

* Production baseline: **Combo A**.
* Frontend path: **Streamlit** (operator web panel) + CLI fallback.
* Backend path: FastAPI gateway + workers + Qdrant + Neo4j + file artifacts (`runs/...`).
* Runtime policy: `OpenVINO-first` с fallback `CPU/GPU/NPU`.
* Model policy: pragmatic hybrid by task:
  * text/retrieval/rerank: Qwen3 stack,
  * ASR active path: Whisper GenAI,
  * archived paths остаются recoverable через explicit opt-in.

## North Star

Сделать local-first game companion для ATM10 с production-ready операторским контуром:

* Phase A: vision loop (screenshot -> VLM interface -> structured output + artifacts).
* Phase B: memory (retrieval + KAG + citations + guardrails).
* Phase C: voice (active ASR path + resilient TTS service/fallback).
* Phase D: operator control plane (Streamlit) поверх unified local API.
* Automation: safe assistive path, default dry-run, без real input events по умолчанию.

## Constraints

* OS/Runtime: Windows 11 + PowerShell 7 (first-class).
* Dev style: small, reviewable diffs + reproducible commands + tests/smoke.
* Paths/files: `pathlib`, без hardcoded machine-specific путей.
* Data hygiene: не коммитим модели/дампы/артефакты/секреты.
* Architecture hygiene: важные policy/архитектурные решения фиксируем в `docs/DECISIONS.md`.
* Runtime policy: `OpenVINO-first`.
* WIP limit (execution): максимум 3 активные задачи одновременно.

## Milestone Map

### Completed

* M0: Instance discovery + repo hygiene.
* M1: Phase A vision loop baseline.
* M2: Retrieval baseline + benchmark + profile defaults.
* M3: Voice runtime operational path (active ASR + archived policy).
* M3.1: OpenVINO rollout (text-core + retrieval profile).
* M4: HUD baselines (OCR + mod-hook ingest).
* M5: KAG baseline + Neo4j path + nightly guardrail + trend/severity policy.
* M6.0: Automation safe scaffold (dry-run only) + CI contract checks.
* M6.1-M6.19: Intent-chain contract hardening (trace/intent correlation, strict CI checks, rollout checklist).

### Active Goals

#### G1 — M7 Combo A Service Foundation

Goal:

* Перевести текущий script-per-task baseline в unified local gateway без потери reproducibility.

Definition of Done:

* Есть FastAPI gateway как единая точка входа для health, retrieval, KAG query и automation dry-run orchestration.
* Есть стабильный artifact contract для gateway-run (request/response + status + links на child artifacts).
* Есть минимум 2 smoke-проверки gateway-path в CI (без внешних нестабильных зависимостей).

Open tasks:

* Зафиксировать минимальный API-контракт v1 (endpoint list + request/response schema + error contract).
* Добавить lightweight gateway smoke path с machine-readable summary.
* Зафиксировать в runbook единый локальный startup sequence для Combo A.

#### G2 — M8 Streamlit Operator Panel (Combo A UI)

Goal:

* Дать операторский web UI для ежедневного управления локальным стеком и быстрой диагностики.

Definition of Done:

* Есть runnable Streamlit app с минимум 4 рабочими зонами:
  * stack health,
  * run explorer (`runs/<timestamp>/...`),
  * latest metrics (smoke/guardrail snapshots),
  * safe action triggers (smoke/dry-run only).
* UI работает на Windows 11 локально и не требует cloud/deploy инфраструктуры.
* UI-действия оставляют traceable artifacts/log entries.

Open tasks:

* Утвердить minimal IA для v0 (страницы/вкладки + data sources).
* Реализовать read-only observability first, затем safe action buttons.
* Добавить smoke-check на запуск Streamlit entrypoint без crash.

#### G3 — M6.1 Automation Safe Loop (ongoing)

Goal:

* Поддерживать безопасный intent -> plan -> dry-run loop как обязательный слой для automation.

Definition of Done:

* Для каждого нового `intent_type` выполняется policy `M6.19` (fixture + smoke + strict contract-check + summary/artifact wiring + regression test).
* Контракт `automation_plan_v1` остается backward-compatible и traceable.

Open tasks:

* Применять `M6.19` checklist при каждом расширении intent templates.

#### G4 — KAG Quality/Latency Guardrail

Goal:

* Держать стабильный quality/latency baseline на sample+hard наборах без silent regressions.

Definition of Done:

* Nightly trend snapshot стабильно отражает rolling-baseline статус (`mrr`, `latency_p95`, severity).
* Изменения retrieval/KAG проходят sample/hard профили без нарушения agreed thresholds.

Open tasks:

* Переоценивать readiness для перехода `critical_policy=fail_nightly` (baseline сейчас `signal_only`).
* Периодически перекалибровывать latency severity thresholds по актуальной шумовой базе.

#### G5 — CI Smoke Expansion & Contract Uniformity

Goal:

* Расширять coverage новых runnable entrypoints без роста flaky-риска.

Definition of Done:

* Для каждого нового smoke entrypoint есть machine-readable summary и стабильный CI шаг.
* Runbook и Decisions синхронизированы с фактическими CI контрактами.

Open tasks:

* Сохранять единый summary-contract подход для core smoke и automation smoke.
* Поддерживать единый runbook-link helper (`scripts/build_runbook_link.py`) в CI summaries.

## Roadmap Horizons

### 0-30 days

* Зафиксировать API contract v1 для Combo A gateway.
* Поднять v0 Streamlit operator panel (health + run explorer + latest metrics + safe smoke triggers).
* Закрыть интеграционный smoke контур для gateway + Streamlit entrypoint.

### 30-60 days

* Внедрить default hybrid query planner (`retrieval first + KAG expansion/citations`).
* Формализовать SLA на уровне API/summary contracts (voice, retrieval, KAG).
* Добавить cross-service benchmark suite для Combo A.

### 60-90 days

* Подготовить pilot overlay/hotkey UX поверх стабилизированного API.
* Оценить переход части automation из dry-run в supervised mode (только после security gates).
* Пересмотреть archived R&D paths по критериям re-open из `docs/ARCHIVED_TRACKS.md`.

## Archived Tracks

Все archived/recoverable направления ведем в:

* `docs/ARCHIVED_TRACKS.md`

Ключевые archived направления:

* `Qwen3-ASR-0.6B` self-conversion pipeline (blocked upstream).
* `Qwen3-TTS` operational path (deactivated по latency/SLA).

## Risks & Mitigations

* Risk: scope creep (одновременный рост voice + KAG + gateway + UI).
  Mitigation: WIP-limit=3 + milestone gates + явный Now/Next/Blocked в `TODO.md`.

* Risk: drift между policy в документах и фактическим runtime.
  Mitigation: синхронизация `PLANS` + `RUNBOOK` + `DECISIONS` на каждом milestone update.

* Risk: security gaps в локальных сервисах при расширении API/UI.
  Mitigation: sandboxed paths, sanitized errors, request limits, dry-run by default.

* Risk: disk/RAM pressure от model zoo.
  Mitigation: OpenVINO pre-converted models, INT4/INT8 приоритет, контролируемый cache lifecycle.
