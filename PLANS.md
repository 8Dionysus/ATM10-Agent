# PLANS.md — atm10-agent

Русский — основной язык. English terms используем там, где это устоявшиеся термины (Phase, Quickstart, smoke test, RAG, VLM, artifacts, run, tests, boundaries).

## Status (as of 2026-02-22)

* M0 + M1 completed.
* `python -m pytest` green (`136 passed`).
* `scripts/phase_a_smoke.py` выполняется и создаёт run artifacts.
* Контракт fixture: `tests/fixtures/rag_docs_sample.jsonl` — строгий JSONL без пустых строк.
* Phase B baseline validated e2e on local ATM10 data + local Qdrant.
* GitHub `origin` настроен, `master` запушен.
* CI workflow `pytest` on push/pull_request добавлен.
* Разделены зависимости runtime/dev: добавлен `requirements-dev.txt` (CI/tests ставят dev requirements).
* В M2 добавлены staged retrieval (`candidate-k + reranker`) и benchmark `eval_retrieval.py`.
* В M2 добавлен runtime switch для qwen3 reranker: `torch|openvino` + device (`AUTO|CPU|GPU|NPU`).
* Для M3 добавлен long-lived voice runtime (`voice_runtime_service` + `voice_runtime_client`).
* По voice SLA check: ASR warm <1s; `Qwen3-TTS` path переведен в archived/deactivated.
* Session snapshots зафиксированы в `docs/SESSION_2026-02-20.md` и `docs/SESSION_2026-02-22.md`.
* ASR export probes (2026-02-22): после прогона в `.venv` с export toolchain
  статус перешёл из `import_error` в `blocked_upstream`; unlock-gate остаётся `ready=false`
  (artifacts: `runs/20260222_142450-qwen3-voice-probe/`, `runs/20260222_142518-qwen3-custom-export/`).
* Для `scripts/export_qwen3_custom_openvino.py` восстановлена script/module CLI-совместимость
  и добавлен regression test на `--help`.
* Добавлен ASR backend benchmark runner `scripts/benchmark_asr_backends.py`;
  baseline-run на 6 локальных WAV (`runs/20260222_152347-asr-backend-bench/`) подтвердил
  сопоставимый avg latency для `qwen_asr` и `whisper_genai` (NPU).
* Для low-latency realtime loop принят startup профиль `whisper_genai + NPU + warmup`
  (`scripts/start_voice_whisper_npu.ps1`); по warm-path benchmark
  `runs/20260222_152914-asr-backend-bench/` `whisper_genai` показал лучший p95 tail latency.
* `qwen3-asr` переведен в archived/recoverable status:
  runtime путь оставлен в коде, но включается только explicit opt-in флагами.
* Добавлен text-core OpenVINO demo entrypoint:
  `scripts/text_core_openvino_demo.py` (prompt -> `response.json` в `runs/<timestamp>-text-core-openvino/`).

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

* [x] `scripts/asr_demo.py` сохранен как archived qwen3-asr demo (explicit opt-in).
* [x] `scripts/tts_demo.py` сохранен как historical reference (archived)
* [x] Optional integration into loop: `src/agent_core/io_voice.py`
* [x] Graceful degradation: если нет audio device — понятная ошибка
* [x] Long-lived runtime for lower steady-state latency: `scripts/voice_runtime_service.py` + `scripts/voice_runtime_client.py` (active backend: `whisper_genai`)
* [x] Add fast-fallback TTS mode for in-game SLA `<=2s` (separate stack, not `Qwen3-TTS`)
  Done: отдельный native Python TTS runtime (`scripts/tts_runtime_service.py`):
  FastAPI router + `XTTS v2` main engine + fallback `Piper`/`Silero` (ru service voice),
  с prewarm/queue/chunking/phrase cache.
* [x] Добавить operational CLI client для TTS runtime:
  `scripts/tts_runtime_client.py` (`health|tts|tts-stream`) + run artifacts.
* [x] Перевести `Qwen3-ASR-0.6B` в archived/recoverable status.
  * Active ASR target: `Whisper v3 Turbo (OpenVINO GenAI)`.
  * `Qwen3-ASR-0.6B` остается в repo как restore path с explicit opt-in.

### M3.1 — OpenVINO model rollout for Qwen3 stack

Цель: унифицировать inference runtime под `OpenVINO` для text/vl/retrieval/voice.

Tasks:

* [x] Поднять text core на готовом OV-репозитории (`Qwen3-8B`, int4/int8 профиль).
  Done: добавлен runnable smoke entrypoint `scripts/text_core_openvino_demo.py`
  с `OpenVINO GenAI` runtime и artifact contract (`run.json`, `response.json`).
* [x] Зафиксировать retrieval на OV-моделях (`Embedding 0.6B`, `Reranker 0.6B`) как production default.
  Done: добавлен profile-layer `baseline|ov_production` (`src/rag/retrieval_profiles.py`),
  profile `ov_production` использует `OpenVINO/Qwen3-Reranker-0.6B-fp16-ov` +
  `reranker_runtime=openvino` + `OpenVINO/Qwen3-Embedding-0.6B-int8-ov` metadata;
  подключено в `scripts/retrieve_demo.py` и `scripts/eval_retrieval.py`.
* [x] Добавить self-conversion pipeline для `Qwen3-VL-4B-Instruct` -> OV IR.
  Done: custom path `scripts/export_qwen3_custom_openvino.py --preset qwen3-vl-4b --execute --model-source ...`,
  artifact: `runs/20260220_150028-qwen3-custom-export/`,
  output: `models/qwen3-vl-4b-instruct-ov-custom`.
* [ ] (Archived track) Добавить self-conversion pipeline для `Qwen3-ASR-0.6B` -> OV IR.
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

* [x] HUD assistance: OCR baseline.
  Done: добавлен runnable entrypoint `scripts/hud_ocr_baseline.py` (Tesseract CLI),
  артефакты `run.json/ocr.json/ocr.txt`, покрытие тестами.
* [x] HUD assistance: mod hook.
  Done: добавлен runnable entrypoint `scripts/hud_mod_hook_baseline.py` (hook JSON ingest),
  артефакты `run.json/hook_raw.json/hook_normalized.json/hud_text.txt`, покрытие тестами.
* [x] Graph/KAG baseline (file-based, no Neo4j).
  Done: `src/kag/baseline.py`, `scripts/kag_build_baseline.py`, `scripts/kag_query_demo.py`,
  артефакты `kag_graph.json` и `kag_query_results.json`, тестовое покрытие добавлено.
* [x] Graph/KAG Neo4j runtime path (approved transition).
  Done: `src/kag/neo4j_backend.py`, `scripts/kag_sync_neo4j.py`, `scripts/kag_query_neo4j.py`,
  тесты на backend/sync/query добавлены.
* [x] Graph/KAG Neo4j e2e validation на локальном инстансе (artifacted run + latency snapshot).
  Done: `runs/20260222_164928-kag-build/`, `runs/20260222_164942-kag-sync-neo4j/`,
  `runs/20260222_165026-kag-query-neo4j/`,
  latency snapshot: `runs/20260222_165100-kag-neo4j-e2e/e2e_latency_snapshot.json`.
* [x] Graph/KAG Neo4j benchmark на фиксированном eval-наборе (quality + latency).
  Done: `scripts/eval_kag_neo4j.py`, fixture `tests/fixtures/kag_neo4j_eval_sample.jsonl`,
  run `runs/20260222_171620-kag-neo4j-eval/`
  (`recall@5=1.0000`, `mrr@5=0.8571`, `hit-rate@5=1.0000`, `latency_p95_ms=70.96`).
* [x] Graph/KAG Neo4j hard-cases benchmark.
  Done: fixture `tests/fixtures/kag_neo4j_eval_hard.jsonl`,
  run `runs/20260222_170006-kag-neo4j-eval/`
  (`recall@5=0.5000`, `mrr@5=0.3750`, `hit-rate@5=0.5000`, `latency_p95_ms=70.50`).
* [x] Graph/KAG Neo4j relevance uplift по hard-cases (target `hit-rate@5 >= 0.75`).
  Done: query uplift (lexical fallback in `query_kag_neo4j`),
  run `runs/20260222_170453-kag-neo4j-eval/`
  (`recall@5=1.0000`, `mrr@5=0.7812`, `hit-rate@5=1.0000`, `latency_p95_ms=133.00`).
* [x] Graph/KAG Neo4j latency tuning после relevance uplift.
  Done: hybrid lexical strategy (`fulltext -> limited scan fallback`) +
  lexical gating (`run lexical only when direct_rows < topk`) +
  skip expansion for single-token queries;
  run `runs/20260222_171240-kag-neo4j-eval/`
  (`recall@5=1.0000`, `mrr@5=0.8438`, `hit-rate@5=1.0000`, `latency_p95_ms=66.14`).
* [x] Graph/KAG Neo4j ranking uplift для `star` (target: улучшить first-hit rank).
  Done: `query_kag_neo4j` single-token lexical alignment bonus + fallback gating,
  run `runs/20260222_213235-kag-neo4j-eval/` (`star.first_hit_rank=1`).
* [x] Automation (hotkeys/mouse) строго локально, default dry-run
  Done: `scripts/automation_dry_run.py` (plan JSON -> normalized dry-run artifacts, no real input events),
  tests: `tests/test_automation_dry_run.py`.
* [x] CI hardening: добавить smoke jobs для runnable scripts помимо `pytest`
  Done: CI workflow запускает `phase_a_smoke` (stub), `retrieve_demo` (fixtures), `eval_retrieval` (fixtures).

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
