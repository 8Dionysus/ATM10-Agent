# PLANS.md — atm10-agent

Русский — основной язык. English terms используем там, где это устоявшиеся термины (Phase, Quickstart, smoke test, RAG, VLM, artifacts, run, tests, boundaries).

## Status (as of 2026-02-20)

* M0 + M1 completed.
* `python -m pytest` green (`25 passed`).
* `scripts/phase_a_smoke.py` выполняется и создаёт run artifacts.
* Контракт fixture: `tests/fixtures/rag_docs_sample.jsonl` — строгий JSONL без пустых строк.
* Phase B baseline validated e2e on local ATM10 data + local Qdrant.
* GitHub `origin` настроен, `master` запушен.
* CI workflow `pytest` on push/pull_request добавлен.
* В M2 добавлены staged retrieval (`candidate-k + reranker`) и benchmark `eval_retrieval.py`.
* В M2 добавлен runtime switch для qwen3 reranker: `torch|openvino` + device (`AUTO|CPU|GPU|NPU`).
* Session snapshot зафиксирован в `docs/SESSION_2026-02-20.md`.

---

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

* Phase A: vision loop (screenshot -> VLM interface -> structured output + artifacts)
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

## Completed Milestones

### M0 — Instance discovery & repo hygiene (Completed 2026-02-20)

Done:

* `.gitignore`, `requirements.txt`, `tests/` harness добавлены.
* Реализован `scripts/discover_instance.py` с env vars + fallback + marker checks.
* Скрипт пишет `runs/<timestamp>/instance_paths.json` и summary в console.
* `python -m pytest` проходит после установки dependencies.

### M1 — Phase A: Vision loop (Completed 2026-02-20)

Done:

* Реализован `scripts/phase_a_smoke.py`.
* Добавлен VLM interface (`src/agent_core/vlm.py`) и deterministic stub (`src/agent_core/vlm_stub.py`).
* Артефакты: `runs/<timestamp>/screenshot.png`, `run.json`, `response.json`.
* Тесты на создание run artifacts и минимальную схему проходят.

---

## Active Milestones

### M2 — Phase B: Memory (RAG) — minimal useful

Цель: retrieval-backed ответы по локальным источникам (quests/guides/recipes).

Tasks:

* [x] Define normalized doc contract (JSONL): `id`, `source`, `title`, `text`, `tags`, `created_at`
* [x] Locate FTB Quests files via discovery
* [x] Implement parser/normalizer (`data/ftbquests_norm/quests.jsonl` + ingest errors)
* [x] Add `.snbt` fallback ingestion for ATM10 quest files
* [x] Reduce retrieval noise via default exclusions (`lang/**`, `reward_tables/**`)
* [x] Bring up retrieval baseline via in-memory stub (for tests and local demo)
* [x] Add Qdrant Docker option (`scripts/ingest_qdrant.py --in data/ftbquests_norm --collection atm10`)
* [x] Implement retrieve demo (`scripts/retrieve_demo.py --query "..." --topk 5`)
* [x] Validate e2e with real local Qdrant against ATM10 normalized data

DoD:

* По запросу возвращаются top-k chunks + citations (id/source/path)
* Есть test dataset и tests на retrieval (in-memory + qdrant unit stubs)

Current gap:

* [x] Improve retrieval relevance inside `chapters/*` (better SNBT signal extraction + richer chapter signals)
  Done: SNBT ingestion now extracts both quoted and unquoted key-value signals
  (`id/type/dimension/structure/filename/...`) with test coverage.
* [x] Calibrate first-stage ranking for `chapters/*` queries (field-weighted scoring + stopword filtering).
  Done: in-memory first-stage теперь приоритизирует `title`-signal над sparse mentions в длинном SNBT text;
  benchmark на `runs/20260220_m2_baseline/eval_cases_atm10_chapters.jsonl` дал
  Recall@5=1.0000, MRR@5=1.0000, hit-rate@5=1.0000 (`runs/20260220_132946/`).
* [x] Calibrate `topk/candidate_k/reranker` defaults on real ATM10 corpus via benchmark metrics
  (`runs/20260220_m2_calibration_none/`): production defaults confirmed as
  `topk=5`, `candidate_k=50`, `reranker=none`.

Approved direction (2026-02-20):

* [x] Для улучшения качества retrieval выбран двухэтапный pipeline: first-stage candidate retrieval + second-stage reranking.
* [x] Для second-stage принят специализированный reranker из семейства `Qwen3-Reranker`; первый rollout: `Qwen3-Reranker-0.6B`.
* [x] Добавить CLI-параметры (`--reranker`, `--candidate-k`) и fallback `--reranker none`.
* [x] Добавить tests на rerank ordering и fallback behavior.
* [x] Добавить benchmark script (`scripts/eval_retrieval.py`) для Recall@k / MRR@k / hit-rate.

### M2.1 — Repo hygiene: LF/CRLF policy (approved focus)

Цель: убрать шумные line-ending warnings и стабилизировать diffs на Windows.

Tasks:

* [x] Добавить `.gitattributes` с явной политикой EOL для source/docs/config.
* [x] Зафиксировать Windows-ориентированные исключения (`*.ps1`, `*.bat`, `*.cmd`) с `crlf`.
* [x] Проверить, что после политики нет неожиданных массовых изменений в tracked-файлах.
* [x] Зафиксировать решение в `docs/DECISIONS.md`.

DoD:

* При типичных командах git нет повторяющегося шума про LF/CRLF для основных файлов проекта.
* Политика EOL воспроизводима для новых contributors на Windows.

### M3 — Phase C: Voice (ASR + TTS) как опциональный слой

Цель: voice не ломает core, а подключается как модуль.

Tasks:

* [ ] `scripts/asr_demo.py` (record short clip -> text)
* [ ] `scripts/tts_demo.py --text "..."` -> audio artifact
* [ ] Optional integration into loop: `src/agent_core/io_voice.py`
* [ ] Graceful degradation: если нет audio device — понятная ошибка

DoD:

* ASR/TTS запускаются отдельно и (опционально) подключаются к агенту
* Phase A/B работает без voice

---

## Backlog (Later / Optional)

* [ ] HUD assistance (OCR baseline / mod hook)
* [ ] Graph/KAG via Neo4j (только после measurable value в Phase B)
* [ ] Automation (hotkeys/mouse) строго локально, default dry-run
* [ ] CI hardening: добавить smoke jobs для runnable scripts помимо `pytest`

---

## Risks & mitigations

* Risk: застрять на моделях/инференсе вместо product loop
  Mitigation: stubbed provider + interface boundaries

* Risk: путаница с gameDir у TLauncher/instances
  Mitigation: discovery script + verification by folder markers

* Risk: нестабильные форматы quests
  Mitigation: JSONL normalization + error logs + tiny fixtures

* Risk: scope creep (RAG + KAG + voice + automation сразу)
  Mitigation: milestone gates + DoD + Ask first
