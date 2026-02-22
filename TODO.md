# TODO.md — atm10-agent

Русский — основной язык. English terms — только как устоявшиеся термины (Quickstart, Phase, smoke test, RAG, VLM, artifacts, run, tests, boundaries).

Правило выполнения: small, reviewable diffs + runnable commands + минимум 1 test на заметное изменение поведения.

## Status (as of 2026-02-22)

* M0 и M1 завершены.
* Текущий baseline: `python -m pytest` проходит (`136 passed`).
* `scripts/phase_a_smoke.py` выполняется и пишет artifacts в `runs/<timestamp>/`.
* Phase B baseline (normalize -> ingest -> retrieve) validated на локальном ATM10 + Qdrant.

---

## Done (recent)

### Repo hygiene

* [x] `.gitignore` добавлен и обновлён.
* [x] `requirements.txt` добавлен.
* [x] `tests/` harness на `pytest` добавлен.
* [x] Добавлен session snapshot `docs/SESSION_2026-02-20.md` с ключевыми артефактами/метриками.
* [x] Добавлен session snapshot `docs/SESSION_2026-02-22.md` (актуализирован baseline и ASR export gap).
* [x] Исправлена CLI-совместимость `scripts/export_qwen3_custom_openvino.py`:
  скрипт теперь запускается и как `python scripts/...`, и как `python -m scripts...`;
  добавлен smoke-test `--help`.

### Instance discovery

* [x] `scripts/discover_instance.py` реализован.
* [x] Поддержаны env vars `MINECRAFT_DIR`, `ATM10_DIR` + fallback.
* [x] Добавлены marker checks и artifact `instance_paths.json`.
* [x] Тест на expected structure добавлен.

### Phase A (vision loop)

* [x] `scripts/phase_a_smoke.py` реализован.
* [x] VLM interface + deterministic stub добавлены.
* [x] Тесты на run folder/`run.json`/`response.json` и минимальные keys добавлены.

### Phase B (partial)

* [x] Doc contract JSONL зафиксирован.
* [x] FTB Quests normalizer реализован.
* [x] Fixture/test на нормализацию и структуру JSONL добавлены.
* [x] `scripts/retrieve_demo.py` реализован (in-memory retrieval, top-k + citations).
* [x] Retrieval tests через in-memory stub добавлены.
* [x] `scripts/ingest_qdrant.py` реализован (optional backend, REST API).
* [x] Добавлена опциональная qdrant-backed retrieval ветка (`--backend qdrant`) + unit tests без Docker.
* [x] Добавлен SNBT fallback ingestion для ATM10 квестов.
* [x] Добавлено default исключение noise-веток (`lang/**`, `reward_tables/**`) при нормализации.
* [x] Ingest в Qdrant стал идемпотентным при `collection already exists` (HTTP 409).
* [x] Добавлен двухэтапный retrieval (`candidate-k` + optional reranker `none|qwen3`).
* [x] Добавлен benchmark `scripts/eval_retrieval.py` (Recall@k / MRR@k / hit-rate).
* [x] Добавлены тесты на rerank ordering/fallback и benchmark artifacts.
* [x] Добавлен OpenVINO runtime для `qwen3` reranker (`--reranker-runtime openvino`, `--reranker-device AUTO|CPU|GPU|NPU`) для ускорения на Intel GPU/NPU.

---

## Next (актуальные шаги)

### Sprint focus (approved)

* [x] Focus #1: донастроить relevance в `chapters/*` (quality tuning по benchmark на реальных ATM10 данных).
  Реализовано: first-stage scoring учитывает field-weights (`title/text/tags`) + stopword filtering.
  Результат на `runs/20260220_m2_baseline/eval_cases_atm10_chapters.jsonl`:
  Recall@5=1.0000, MRR@5=1.0000, hit-rate@5=1.0000 (`runs/20260220_132946/`).
* [x] Focus #3: LF/CRLF политика зафиксирована и применена через `.gitattributes`.

### Project/repo operations

* [x] Добавить `origin` и сделать push в GitHub.
* [x] Добавить GitHub Actions: `pytest` on push.
* [x] Добавить CI smoke jobs для runnable scripts (`phase_a_smoke`, `retrieve_demo`, `eval_retrieval`).
* [x] Зафиксировать LF/CRLF политику через `.gitattributes` и проверить, что нет неожиданного массового diff.

### Dependencies/tooling

* [x] Решить, нужен ли `requirements-dev.txt` (разделить runtime/dev).
  Принято: `requirements.txt` = runtime, `requirements-dev.txt` = runtime + `pytest` для тестов/CI.

### Qwen3 model stack (fixed)

* [x] Зафиксировать стек: `Qwen3-8B`, `Qwen3-VL-4B-Instruct`, `Qwen3-Embedding-0.6B`,
  `Qwen3-Reranker-0.6B`; `Qwen3-ASR-0.6B` переведен в archived status.
* [x] Зафиксировать политику: `OpenVINO-first`; где нет готового OV-репозитория — self-conversion.
* [x] Зафиксировать ограничение: без замены на `Qwen2.5*`.
* [x] Добавить единый entrypoint для self-conversion с dry-run артефактами:
  `scripts/export_qwen3_openvino.py` (`--preset qwen3-vl-4b|qwen3-asr-0.6b`).
* [x] Подготовить и проверить self-conversion для `Qwen3-VL-4B-Instruct` -> OpenVINO IR.
  Done: через custom pipeline `scripts/export_qwen3_custom_openvino.py`
  с `--model-source` (artifact: `runs/20260220_150028-qwen3-custom-export/`,
  output: `models/qwen3-vl-4b-instruct-ov-custom`).
* [x] Перевести `Qwen3-ASR-0.6B` в archived/recoverable status.
  Текущий блокер (2026-02-20): `transformers` не распознаёт `qwen3_asr`
  в export flow (artifact: `runs/20260220_141602-qwen3-export/`).
  Progress: в `scripts/export_qwen3_custom_openvino.py` добавлен execute-path для
  `qwen3-asr-0.6b` + unified support probe/status (`supported|blocked_upstream|import_error|runtime_error`)
  в `export_plan.json`; нужен валидированный успешный run на целевом окружении.
  Nightly-check (artifact: `runs/20260220_190319-qwen3-exp-venv-probe/`) пока не снял блокер.
  Update (2026-02-22): после прогона в `.venv` с export toolchain probe даёт `blocked_upstream`
  (модель `qwen3_asr` не распознана в `transformers.AutoConfig`), поэтому unlock-gate остаётся
  `ready=false` (artifacts: `runs/20260222_142450-qwen3-voice-probe/`, `runs/20260222_142518-qwen3-custom-export/`).
  Operational policy: path сохранен в коде и включается только explicit opt-in флагами
  (`--allow-archived-qwen-asr`, `--include-archived-qwen-asr` в соответствующих скриптах).
* [x] `Qwen3-TTS` ветка переведена в archived/deactivated status.
  Исторические артефакты и результаты бенчмарков сохранены в `runs/*qwen3-tts*`,
  но `Qwen3-TTS` исключен из active roadmap и production планирования.
* [x] Добавить единый voice probe + nightly matrix-runner для upstream-check:
  `scripts/probe_qwen3_voice_support.py`, `scripts/qwen3_voice_probe_matrix.py`.

### Phase B completion

* [x] Реализовать двухэтапный retrieval: first-stage top candidates + second-stage rerank.
* [x] Добавить специализированный reranker из семейства `Qwen3-Reranker` (старт: `Qwen3-Reranker-0.6B`).
* [x] Добавить CLI-параметры (`--reranker`, `--candidate-k`) в retrieval demo.
* [x] Сохранить fallback `--reranker none`, чтобы baseline работал без модели.
* [x] Добавить tests на rerank ordering и fallback.
* [x] Добавить benchmark (`eval_retrieval.py`) для metric-driven выбора defaults.
* [x] Выбрать production defaults (`topk`, `candidate_k`, `reranker`) по eval на реальном ATM10 корпусе.
  Зафиксировано по grid-eval (`runs/20260220_m2_calibration_none/`):
  `topk=5`, `candidate_k=50`, `reranker=none`.
* [x] Зафиксировать OV production profile для retrieval без ломки baseline.
  Реализовано: `src/rag/retrieval_profiles.py` (`baseline|ov_production`);
  `scripts/retrieve_demo.py` и `scripts/eval_retrieval.py` принимают `--profile`
  и поддерживают ручные overrides поверх profile.
* [x] Улучшить SNBT signal extraction внутри `chapters/*` для повышения recall перед rerank.
  Реализовано: extraction поддерживает как quoted, так и unquoted SNBT значения
  (`id/type/dimension/structure/filename/...`), добавлен pytest на unquoted кейс.

### VLM integration

* [x] Добавить real provider через текущий интерфейс (`openai` via Responses API) без ломки Phase A loop.
  Реализовано: `scripts/phase_a_smoke.py` поддерживает `--vlm-provider auto|stub|openai`,
  сохраняет `vlm` metadata в `run.json`, и fallback-ит в `deterministic_stub_v1` при ошибках
  (если не включен `--strict-vlm`).

### Phase C (optional)

* [x] `scripts/asr_demo.py` + graceful no-device error (переведен в archived qwen3-asr path с explicit opt-in).
* [x] Добавлен альтернативный ASR demo path: `scripts/asr_demo_whisper_genai.py`
  (`OpenVINO GenAI + Whisper v3 Turbo`, включая `--device NPU` и timestamps artifacts).
* [x] `scripts/voice_runtime_service.py` поддерживает переключаемый ASR backend:
  `qwen_asr|whisper_genai` (для `whisper_genai` добавлены `--asr-device` и `--asr-task`).
  Update: `whisper_genai` = default active backend; `qwen_asr` = archived backend с explicit opt-in.
* [x] Добавлен startup warmup для ASR в `voice_runtime_service`
  (`--asr-warmup-request`, `--asr-warmup-audio`, `--asr-warmup-language`).
* [x] Добавлен helper start script `scripts/start_voice_whisper_npu.ps1`
  для low-latency profile (`whisper_genai + NPU + warmup`).
* [x] Добавлен benchmark runner `scripts/benchmark_asr_backends.py`
  (сводка load/latency per backend + per-sample results artifacts).
* [x] `scripts/tts_demo.py` оставлен как historical reference (archived).
* [x] Runtime layer `src/agent_core/io_voice.py` (active ASR: `WhisperGenAIASRClient`; `QwenASRClient` archived/recoverable).
* [x] Tests: CLI help + no-crash import checks.
* [x] Long-lived runtime path: `scripts/voice_runtime_service.py` + `scripts/voice_runtime_client.py` (active ASR path).
* [x] In-game SLA `<=2s`: добавить отдельный fast-fallback TTS path (не `Qwen3-TTS`).
  Реализовано: отдельный `scripts/tts_runtime_service.py` (FastAPI router) с
  `XTTS v2` как main engine и fallback `Piper` + `Silero` (ru service voice),
  включая prewarm/queue/chunking/phrase cache.
* [x] Добавить отдельный CLI client для нового TTS runtime (`health|tts|tts-stream`)
  с run artifacts в `runs/<timestamp>-tts-client/`.

### Text core (OpenVINO)

* [x] Добавить runnable text-core demo для OV-профиля `Qwen3-8B` без ломки baseline.
  Реализовано: `scripts/text_core_openvino_demo.py` (`--model-dir`, `--prompt`, `--device`),
  артефакты: `runs/<timestamp>-text-core-openvino/{run.json,response.json}`.
* [x] Добавить smoke-tests для text-core demo (`success path`, `missing runtime`, `CLI --help`).

### HUD assistance

* [x] Добавить OCR baseline entrypoint для HUD скриншота без новых Python deps.
  Реализовано: `scripts/hud_ocr_baseline.py` (Tesseract CLI wrapper),
  артефакты: `runs/<timestamp>-hud-ocr/{run.json,ocr.json,ocr.txt}`.
* [x] Добавить smoke-tests для HUD OCR baseline (`success path`, `missing runtime`, `CLI --help`).
* [x] Добавить mod hook path для HUD.
  Реализовано: `scripts/hud_mod_hook_baseline.py` (JSON hook ingest -> normalized artifacts),
  артефакты: `runs/<timestamp>-hud-hook/{run.json,hook_raw.json,hook_normalized.json,hud_text.txt}`.
* [x] Добавить smoke-tests для HUD mod-hook baseline (`success path`, `invalid payload`, `CLI --help`).

### KAG baseline

* [x] Добавить file-based KAG baseline без Neo4j.
  Реализовано: `src/kag/baseline.py` + entrypoints
  `scripts/kag_build_baseline.py` (`docs -> kag_graph.json`) и
  `scripts/kag_query_demo.py` (`kag_graph.json + query -> top-k citations`).
* [x] Добавить smoke-tests для KAG baseline (`build/query success`, `CLI --help`).
* [x] Добавить Neo4j-backed KAG entrypoints (sync/query) без новых Python deps.
  Реализовано: `src/kag/neo4j_backend.py`,
  `scripts/kag_sync_neo4j.py` (`kag_graph.json` -> Neo4j),
  `scripts/kag_query_neo4j.py` (Neo4j -> top-k citations),
  тесты: `tests/test_kag_neo4j_backend.py`, `tests/test_kag_sync_neo4j.py`, `tests/test_kag_query_neo4j.py`.
* [x] Выполнить e2e прогон на локальном Neo4j и зафиксировать run artifacts/latency.
  Выполнено (2026-02-22):
  `runs/20260222_164928-kag-build/`,
  `runs/20260222_164942-kag-sync-neo4j/`,
  `runs/20260222_165026-kag-query-neo4j/`,
  latency snapshot:
  `runs/20260222_165100-kag-neo4j-e2e/e2e_latency_snapshot.json`.
* [x] Добавить benchmark для KAG Neo4j (quality + latency) на фиксированном наборе query-cases.
  Реализовано: `scripts/eval_kag_neo4j.py`,
  fixture: `tests/fixtures/kag_neo4j_eval_sample.jsonl`,
  тесты: `tests/test_eval_kag_neo4j.py`.
  Baseline run (2026-02-22):
  `runs/20260222_171620-kag-neo4j-eval/`
  (`recall@5=1.0000`, `mrr@5=0.8571`, `hit-rate@5=1.0000`, `latency_p95_ms=70.96`).
* [x] Добавить hard-cases benchmark набор для KAG Neo4j.
  Реализовано: `tests/fixtures/kag_neo4j_eval_hard.jsonl`.
  Run: `runs/20260222_170006-kag-neo4j-eval/`
  (`recall@5=0.5000`, `mrr@5=0.3750`, `hit-rate@5=0.5000`, `latency_p95_ms=70.50`).
* [x] Поднять hard-cases качество KAG Neo4j до `hit-rate@5 >= 0.75`.
  Выполнено: `runs/20260222_170453-kag-neo4j-eval/`
  (`recall@5=1.0000`, `mrr@5=0.7812`, `hit-rate@5=1.0000`, `latency_p95_ms=133.00`).
* [x] Снизить tail latency hard-cases (`latency_p95_ms`) без потери `hit-rate@5`.
  Выполнено: `runs/20260222_171240-kag-neo4j-eval/`
  (`recall@5=1.0000`, `mrr@5=0.8438`, `hit-rate@5=1.0000`, `latency_p95_ms=66.14`).
* [x] Поднять качество ранга для `star` (`first_hit_rank` сейчас `4` в hard-run).
  Выполнено: `runs/20260222_213235-kag-neo4j-eval/`
  (`star.first_hit_rank=1`, `mrr@5=0.9375`, `hit-rate@5=1.0000`, `latency_p95_ms=96.84`).
* [x] Добавить automation scaffold строго в dry-run режиме (без keyboard/mouse side effects).
  Реализовано: `scripts/automation_dry_run.py` (`--plan-json` -> normalized plan artifacts).
  Артефакты: `runs/<timestamp>-automation-dry-run/{run.json,actions_normalized.json,execution_plan.json}`.
  Тесты: `tests/test_automation_dry_run.py` (`success`, `invalid payload`, `CLI --help`).

---

## Maintenance

* [ ] Любое существенное архитектурное решение фиксировать в `docs/DECISIONS.md` (1–3 bullets).
* [ ] При изменении команд/setup обновлять `docs/RUNBOOK.md`.
* [ ] Never commit: `models/`, `data/` dumps, `runs/`, `.codex/**/logs/`, секреты/токены.
