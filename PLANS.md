# PLANS.md — atm10-agent

Русский — основной язык. English terms используем там, где это устоявшиеся термины (Phase, Quickstart, smoke test, RAG, VLM, artifacts, run, tests, boundaries).

## Status (as of 2026-02-20)

* M0 + M1 completed.
* `python -m pytest` green (`68 passed`).
* `scripts/phase_a_smoke.py` выполняется и создаёт run artifacts.
* Контракт fixture: `tests/fixtures/rag_docs_sample.jsonl` — строгий JSONL без пустых строк.
* Phase B baseline validated e2e on local ATM10 data + local Qdrant.
* GitHub `origin` настроен, `master` запушен.
* CI workflow `pytest` on push/pull_request добавлен.
* В M2 добавлены staged retrieval (`candidate-k + reranker`) и benchmark `eval_retrieval.py`.
* В M2 добавлен runtime switch для qwen3 reranker: `torch|openvino` + device (`AUTO|CPU|GPU|NPU`).
* Для M3 добавлен long-lived voice runtime (`voice_runtime_service` + `voice_runtime_client`).
* По voice SLA check: ASR warm <1s; `Qwen3-TTS` path переведен в archived/deactivated.
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
* Phase C: voice (active ASR path; TTS archived)

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
* Model policy: core stack фиксирован на `Qwen3`; `Qwen2.5*` не используем как замену.
* Runtime policy: `OpenVINO-first`; если нет готового OV-моделя, делаем self-conversion.

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
* [x] Replace deterministic Phase A VLM stub with real provider integration behind interface boundary.
  Done: `scripts/phase_a_smoke.py` now supports `auto|stub|openai`, with stable stub fallback and
  VLM metadata in `run.json`.

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

### M3 — Phase C: Voice (active path = ASR)

Цель: voice не ломает core, а подключается как модуль.

Tasks:

* [x] `scripts/asr_demo.py` (record short clip -> text)
* [x] `scripts/tts_demo.py` сохранен как historical reference (archived)
* [x] Optional integration into loop: `src/agent_core/io_voice.py`
* [x] Graceful degradation: если нет audio device — понятная ошибка
* [x] Long-lived runtime for lower steady-state latency: `scripts/voice_runtime_service.py` + `scripts/voice_runtime_client.py` (active ASR path)
* [ ] Add fast-fallback TTS mode for in-game SLA `<=2s` (separate stack, not `Qwen3-TTS`)
* [ ] Qwen3 voice target (active):
  * ASR: `Qwen3-ASR-0.6B` (OpenVINO runtime or self-converted IR)

### M3.1 — OpenVINO model rollout for Qwen3 stack

Цель: унифицировать inference runtime под `OpenVINO` для text/vl/retrieval/voice.

Tasks:

* [ ] Поднять text core на готовом OV-репозитории (`Qwen3-8B`, int4/int8 профиль).
* [ ] Зафиксировать retrieval на OV-моделях (`Embedding 0.6B`, `Reranker 0.6B`) как production default.
* [x] Добавить self-conversion pipeline для `Qwen3-VL-4B-Instruct` -> OV IR.
  Done: custom path `scripts/export_qwen3_custom_openvino.py --preset qwen3-vl-4b --execute --model-source ...`,
  artifact: `runs/20260220_150028-qwen3-custom-export/`,
  output: `models/qwen3-vl-4b-instruct-ov-custom`.
* [ ] Добавить self-conversion pipeline для `Qwen3-ASR-0.6B` -> OV IR.
* [x] `Qwen3-TTS` export/benchmark ветка переведена в archived/deactivated status;
  артефакты сохранены как historical reference (`runs/*qwen3-tts*`).
* [x] Добавить единый probe-слой для voice-архитектур (`qwen3_asr` + archived `qwen3_tts*`)
  и matrix-runner для nightly-проверок upstream комбинаций (`scripts/probe_qwen3_voice_support.py`,
  `scripts/qwen3_voice_probe_matrix.py`).
* [x] Добавить smoke tests на import/CLI/no-crash для voice entrypoints (`asr_demo`, `tts_demo`).

DoD:

* Active path: ASR запускается отдельно и (опционально) подключается к агенту
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
