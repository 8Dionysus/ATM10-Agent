# TODO.md — atm10-agent

Русский — основной язык. English terms — только как устоявшиеся термины (Quickstart, Phase, smoke test, RAG, VLM, artifacts, run, tests, boundaries).

Правило выполнения: small, reviewable diffs + runnable commands + минимум 1 test на заметное изменение поведения.

## Status (as of 2026-02-20)

* M0 и M1 завершены.
* Текущий baseline: `python -m pytest` проходит (`68 passed`).
* `scripts/phase_a_smoke.py` выполняется и пишет artifacts в `runs/<timestamp>/`.
* Phase B baseline (normalize -> ingest -> retrieve) validated на локальном ATM10 + Qdrant.

---

## Done (recent)

### Repo hygiene

* [x] `.gitignore` добавлен и обновлён.
* [x] `requirements.txt` добавлен.
* [x] `tests/` harness на `pytest` добавлен.
* [x] Добавлен session snapshot `docs/SESSION_2026-02-20.md` с ключевыми артефактами/метриками.

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
* [x] Зафиксировать LF/CRLF политику через `.gitattributes` и проверить, что нет неожиданного массового diff.

### Dependencies/tooling

* [ ] Решить, нужен ли `requirements-dev.txt` (разделить runtime/dev).

### Qwen3 model stack (fixed)

* [x] Зафиксировать стек: `Qwen3-8B`, `Qwen3-VL-4B-Instruct`, `Qwen3-Embedding-0.6B`,
  `Qwen3-Reranker-0.6B`, `Qwen3-ASR-0.6B`.
* [x] Зафиксировать политику: `OpenVINO-first`; где нет готового OV-репозитория — self-conversion.
* [x] Зафиксировать ограничение: без замены на `Qwen2.5*`.
* [x] Добавить единый entrypoint для self-conversion с dry-run артефактами:
  `scripts/export_qwen3_openvino.py` (`--preset qwen3-vl-4b|qwen3-asr-0.6b`).
* [x] Подготовить и проверить self-conversion для `Qwen3-VL-4B-Instruct` -> OpenVINO IR.
  Done: через custom pipeline `scripts/export_qwen3_custom_openvino.py`
  с `--model-source` (artifact: `runs/20260220_150028-qwen3-custom-export/`,
  output: `models/qwen3-vl-4b-instruct-ov-custom`).
* [ ] Подготовить и проверить self-conversion для `Qwen3-ASR-0.6B` -> OpenVINO IR.
  Текущий блокер (2026-02-20): `transformers` не распознаёт `qwen3_asr`
  в export flow (artifact: `runs/20260220_141602-qwen3-export/`).
  Progress: в `scripts/export_qwen3_custom_openvino.py` добавлен execute-path для
  `qwen3-asr-0.6b` + unified support probe/status (`supported|blocked_upstream|import_error|runtime_error`)
  в `export_plan.json`; нужен валидированный успешный run на целевом окружении.
  Nightly-check (artifact: `runs/20260220_190319-qwen3-exp-venv-probe/`) пока не снял блокер.
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
* [x] Улучшить SNBT signal extraction внутри `chapters/*` для повышения recall перед rerank.
  Реализовано: extraction поддерживает как quoted, так и unquoted SNBT значения
  (`id/type/dimension/structure/filename/...`), добавлен pytest на unquoted кейс.

### VLM integration

* [x] Добавить real provider через текущий интерфейс (`openai` via Responses API) без ломки Phase A loop.
  Реализовано: `scripts/phase_a_smoke.py` поддерживает `--vlm-provider auto|stub|openai`,
  сохраняет `vlm` metadata в `run.json`, и fallback-ит в `deterministic_stub_v1` при ошибках
  (если не включен `--strict-vlm`).

### Phase C (optional)

* [x] `scripts/asr_demo.py` + graceful no-device error.
* [x] `scripts/tts_demo.py` оставлен как historical reference (archived).
* [x] Runtime layer `src/agent_core/io_voice.py` (active: `QwenASRClient` + audio IO; TTS path archived).
* [x] Tests: CLI help + no-crash import checks.
* [x] Long-lived runtime path: `scripts/voice_runtime_service.py` + `scripts/voice_runtime_client.py` (active ASR path).
* [ ] In-game SLA `<=2s`: добавить отдельный fast-fallback TTS path (не `Qwen3-TTS`).

---

## Maintenance

* [ ] Любое существенное архитектурное решение фиксировать в `docs/DECISIONS.md` (1–3 bullets).
* [ ] При изменении команд/setup обновлять `docs/RUNBOOK.md`.
* [ ] Never commit: `models/`, `data/` dumps, `runs/`, `.codex/**/logs/`, секреты/токены.
