# PLANS.md — atm10-agent

Русский — основной язык. English terms используем там, где это устоявшиеся термины (Phase, Quickstart, smoke test, RAG, VLM, artifacts, run, tests, boundaries).

## Known baseline (already true)

* Repo scaffold (folders/files) создан в `D:\atm10-agent`.
* Codex sandbox готов; MCP `openaiDeveloperDocs` подключён.
* TLauncher Minecraft directory (установлено): `C:\Users\Admin\AppData\Roaming\.minecraft`
* ATM10 instance folder (установлено):
  `C:\Users\Admin\AppData\Roaming\.minecraft\versions\All the Mods 10 - ATM10 All the Mods 10-5.2`

Важно: эти пути нельзя хардкодить в коде. Они должны попадать через env vars / config и/или discovery script.

---

## 1) North Star (зачем проект)

Сделать local “game companion” агента для ATM10:

* Phase A: vision loop (screenshot → VLM interface → structured output + artifacts)
* Phase B: memory (RAG поверх квестов/гайдов/рецептов)
* Phase C: voice (ASR + TTS как опция)

---

## 2) Non-goals (пока нет)

* Multiplayer exploit / automation for servers.
* Полная автоматизация gameplay (макросы/бот) — только assistive workflows и строго по boundaries.
* “Сразу всё”: сначала vertical slice, затем расширение.

---

## 3) Constraints (важные ограничения)

* OS: Windows 11 + PowerShell 7 (first-class).
* Dev loop: small, reviewable diffs; reproducible commands; обязательные tests/smoke.
* Paths: только `pathlib`, никаких хардкодов.
* Data hygiene: модели/дампы/артефакты не коммитим.

---

# Milestones (с критериями Done)

## M0 — Instance discovery & repo hygiene (короткая итерация)

Цель: получить достоверные пути к данным ATM10 (configs/saves/logs/quests) и обеспечить чистую dev-базу.

Tasks:

* [x] Add `.gitignore` (минимум: `models/`, `data/`, `runs/`, `.codex/logs/`, `__pycache__/`, `.venv/`, `*.pyc`)
* [x] Add `requirements.txt` (минимальный набор для Phase A + pytest)
* [x] Add `tests/` harness (pytest) + 1 smoke test на создание run artifacts
* [x] Add discovery script `scripts/discover_instance.py`:

  * вход: env vars (если заданы) `MINECRAFT_DIR`, `ATM10_DIR`
  * fallback: known defaults (Roaming\.minecraft; versions\ATM10 folder)
  * verify markers: `mods/`, `config/`, `saves/`, `logs/` (что найдётся)
  * output: `runs/<timestamp>/instance_paths.json` + console summary
* [x] Update docs later: команды и переменные окружения описать в `docs/RUNBOOK.md` (когда файл будет готов)

DoD:

* `python scripts/discover_instance.py` создаёт `instance_paths.json` и показывает найденные пути
* `python -m pytest` проходит на чистом окружении после установки requirements

---

## M1 — Phase A: Vision loop (vertical slice)

Цель: живой цикл “восприятие → ответ → артефакты”, без зависимости от моделей.

Tasks (core):

* [x] Implement `scripts/phase_a_smoke.py`:

  * создаёт `runs/<timestamp>/`
  * делает screenshot (monitor/window) → `screenshot.png`
  * пишет `run.json` (metadata: timestamp, mode, screen source, paths)
  * вызывает VLM через interface (stubbed provider) → пишет `response.json`
* [x] Implement VLM interface:

  * `src/agent_core/vlm.py` (protocol/ABC)
  * `src/agent_core/vlm_stub.py` (детерминированный stub)
* [x] Implement artifacts layout:

  * `runs/<timestamp>/screenshot.png`
  * `runs/<timestamp>/run.json`
  * `runs/<timestamp>/response.json`
  * `runs/<timestamp>/logs.txt` (optional)
* [x] Add tests:

  * test creates run folder + `run.json` and `response.json`
  * test validates minimal schema keys exist

DoD:

* `python scripts/phase_a_smoke.py` делает артефакты и завершается без ошибок
* `python -m pytest` проходит
* VLM можно заменить, не трогая capture/logging

---

## M2 — Phase B: Memory (RAG) — minimal useful

Цель: retrieval-backed ответы по локальным источникам (quests/guides/recipes).

Tasks:

* [x] Define normalized doc contract (JSONL): `id`, `source`, `title`, `text`, `tags`, `created_at`
* [x] Locate FTB Quests files via discovery:

  * кандидаты: `<GAME_DIR>\config\ftbquests\quests\` и/или instance-specific config folder
  * записывать найденные пути в artifacts + логировать, если не найдено
* [x] Implement parser/normalizer:

  * вход: найденный `ftbquests` folder
  * выход: `data/ftbquests_norm/quests.jsonl`
  * errors: `runs/<timestamp>/ingest_errors.jsonl`
* [ ] Bring up vector store:

  * option A: Qdrant in Docker (local)
  * option B: in-memory stub (for tests)
* [ ] Implement ingest + retrieve demos:

  * `scripts/ingest_qdrant.py --in data/ftbquests_norm --collection atm10`
  * `scripts/retrieve_demo.py --query "..." --topk 5`

DoD:

* По запросу возвращаются top-k chunks + citations (id/source/path)
* Есть test dataset и tests на нормализацию (минимум)

---

## M3 — Phase C: Voice (ASR + TTS) как опциональный слой

Цель: voice не ломает core, а подключается как модуль.

Tasks:

* [ ] `scripts/asr_demo.py` (record short clip → text)
* [ ] `scripts/tts_demo.py --text "..."` → audio artifact
* [ ] Optional integration into loop: `src/agent_core/io_voice.py`
* [ ] Graceful degradation: если нет audio device — понятная ошибка

DoD:

* ASR/TTS запускаются отдельно и (опционально) подключаются к агенту
* Phase A/B работает без voice

---

# Backlog (Later / Optional)

## L1 — HUD assistance (Jade / Probe)

* [ ] Extract block/entity name:

  * вариант 1: OCR over screenshot (noisy)
  * вариант 2: mod/plugin hook (точнее, сложнее)

## L2 — Graph (KAG) via Neo4j

* [ ] Делать только если Phase B уже даёт measurable value

## L3 — Automation (“hands”) осторожно

* [ ] Hotkeys/mouse automation строго локально и по boundaries
* [ ] Default: dry-run mode

## L4 — CI (optional)

* [ ] GitHub Actions: run pytest on push (без Docker dependency)

---

# Risks & mitigations

* Risk: застрять на моделях/инференсе вместо product loop
  Mitigation: Phase A stubbed provider + interface

* Risk: путаница с gameDir у TLauncher/instances
  Mitigation: discovery script + verification by folder markers

* Risk: нестабильные форматы quests
  Mitigation: JSONL normalization + error logs + tiny samples in tests

* Risk: scope creep (RAG+KAG+voice+automation сразу)
  Mitigation: milestone gates + DoD, “no new infra without Ask first”

---

# Task templates (for Codex)

## Implementation task template

* Goal:
* Context (paths, inputs, outputs):
* Constraints (no heavy deps, Windows-first, no breaking changes):
* DoD (commands + expected artifacts/tests):
