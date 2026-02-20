# TODO.md — atm10-agent

Русский — основной язык. English terms — только как термины (Quickstart, Phase, smoke test, RAG, VLM, artifacts, run, tests, boundaries).

Правило выполнения: **small, reviewable diffs** + всегда runnable commands + минимум 1 test на каждую заметную фичу.

---

## P0 — Next (самое ближайшее)

### Repo hygiene

* [x] Добавить `.gitignore` (минимум: `models/`, `data/`, `runs/`, `.codex/logs/`, `__pycache__/`, `.venv/`, `*.pyc`)
* [x] Добавить `requirements.txt` (минимальный набор для Phase A + pytest)
* [x] Добавить `tests/` harness (pytest) + 1 smoke test на создание run artifacts

### Instance discovery (TLauncher / ATM10)

* [x] Сделать `scripts/discover_instance.py`

  * [x] Поддержка env vars: `MINECRAFT_DIR`, `ATM10_DIR`
  * [x] Fallback: искать `.minecraft` в `%APPDATA%` и папку ATM10 в `versions/`
  * [x] Verify markers: `config/`, `mods/`, `logs/`, `saves/` (что найдётся)
  * [x] Писать `runs/<timestamp>/instance_paths.json` + печатать summary в console
* [x] Tests: минимум 1 pytest на “discovery returns expected structure” (через temp dirs и fake markers)

---

## P1 — Phase A (Vision loop vertical slice)

### Smoke runner

* [x] Реализовать `scripts/phase_a_smoke.py`

  * [x] Создаёт `runs/<timestamp>/`
  * [x] Делает screenshot (monitor/window) → `screenshot.png`
  * [x] Пишет `run.json` (timestamp, mode, screen source, paths)
  * [x] Вызывает VLM через interface (stub) → `response.json`
* [x] Реализовать VLM interface

  * [x] `src/agent_core/vlm.py` (protocol/ABC)
  * [x] `src/agent_core/vlm_stub.py` (deterministic stub output)
* [x] Tests

  * [x] Проверка создания `runs/<timestamp>/`
  * [x] Проверка, что `run.json` и `response.json` имеют минимальные keys

---

## P2 — Phase B (Memory / RAG minimal useful)

### Normalized docs contract

* [x] Зафиксировать формат JSONL (doc contract): `id`, `source`, `title`, `text`, `tags`, `created_at`
* [x] Добавить tiny test dataset в `tests/fixtures/` (минимальный, без личных данных)

### FTB Quests ingestion

* [x] Найти FTB Quests folder через discovery (кандидаты: `config/ftbquests/quests/` и instance-specific path)
* [x] Реализовать парсер/нормализатор → `data/ftbquests_norm/quests.jsonl`

  * [x] Логировать ошибки парсинга в `runs/<timestamp>/ingest_errors.jsonl`
* [x] Tests: парсинг маленького sample (fixture) + проверка структуры JSONL

### Vector store

* [ ] Добавить инструкции для локального Qdrant (Docker) в `docs/RUNBOOK.md` (когда файл будет готов)
* [ ] Реализовать `scripts/ingest_qdrant.py --in ... --collection atm10`
* [ ] Реализовать `scripts/retrieve_demo.py --query "..." --topk 5`
* [ ] Tests: retrieval через in-memory stub (чтобы tests не зависели от Docker)

---

## P3 — Phase C (Voice, optional layer)

### ASR demo

* [ ] `scripts/asr_demo.py` (record short clip → text)
* [ ] Graceful errors: нет audio device → понятный exit + message
* [ ] Tests: `--help` + “no crash import”

### TTS demo

* [ ] `scripts/tts_demo.py --text "..."` → audio artifact в `runs/<timestamp>/`
* [ ] Tests: `--help` + “no crash import”

### Optional integration

* [ ] `src/agent_core/io_voice.py` (не ломает Phase A/B)

---

## P4 — Optional / Later

### HUD assistance (block/entity name)

* [ ] OCR over screenshot (baseline, noisy)
* [ ] Альтернатива: mod/plugin hook (точнее, сложнее)

### Graph / KAG (только если Phase B уже приносит value)

* [ ] Схема графа: items/recipes/quest chains
* [ ] Neo4j integration (после измеримой пользы)

### Automation (“hands”) осторожно

* [ ] Hotkeys/mouse automation только локально
* [ ] Default: dry-run mode
* [ ] Ask first перед любыми действиями, которые меняют состояние игры

### CI

* [ ] GitHub Actions: `pytest` on push (без Docker dependency)
* [ ] Basic lint (optional): ruff/black (только по явному решению)

---

## Maintenance

* [ ] Любое существенное решение фиксировать в `docs/DECISIONS.md` (1–3 bullets, когда файл будет готов)
* [ ] Не коммитить: `models/`, `data/` (дампы), `runs/`, `.codex/logs/`, секреты/токены
