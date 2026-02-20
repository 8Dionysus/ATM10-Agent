# TODO.md — atm10-agent

Русский — основной язык. English terms — только как устоявшиеся термины (Quickstart, Phase, smoke test, RAG, VLM, artifacts, run, tests, boundaries).

Правило выполнения: small, reviewable diffs + runnable commands + минимум 1 test на заметное изменение поведения.

## Status (as of 2026-02-20)

* M0 и M1 завершены.
* Текущий baseline: `python -m pytest` проходит (`13 passed`).
* `scripts/phase_a_smoke.py` выполняется и пишет artifacts в `runs/<timestamp>/`.
* Phase B baseline (normalize -> ingest -> retrieve) validated на локальном ATM10 + Qdrant.

---

## Done (recent)

### Repo hygiene

* [x] `.gitignore` добавлен и обновлён.
* [x] `requirements.txt` добавлен.
* [x] `tests/` harness на `pytest` добавлен.

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

---

## Next (актуальные шаги)

### Sprint focus (approved)

* [ ] Focus #1: повысить релевантность retrieval внутри `chapters/*` через stage-2 reranker.
* [ ] Focus #3: зафиксировать и применить LF/CRLF политику через `.gitattributes`.

### Project/repo operations

* [x] Добавить `origin` и сделать push в GitHub.
* [x] Добавить GitHub Actions: `pytest` on push.
* [ ] Зафиксировать LF/CRLF политику через `.gitattributes` и проверить, что нет неожиданного массового diff.

### Dependencies/tooling

* [ ] Решить, нужен ли `requirements-dev.txt` (разделить runtime/dev).

### Phase B completion

* [ ] Реализовать двухэтапный retrieval: first-stage top candidates + second-stage rerank.
* [ ] Добавить специализированный reranker из семейства `Qwen3-Reranker` (старт: `Qwen3-Reranker-0.6B`).
* [ ] Добавить CLI-параметры (`--reranker`, `--candidate-k`) в retrieval demo.
* [ ] Сохранить fallback `--reranker none`, чтобы baseline работал без модели.
* [ ] Добавить tests на rerank ordering и fallback.
* [ ] Улучшить SNBT signal extraction внутри `chapters/*` для повышения recall перед rerank.

### VLM integration

* [ ] Заменить `deterministic_stub_v1` на real provider через текущий интерфейс (без ломки Phase A loop).

### Phase C (optional)

* [ ] `scripts/asr_demo.py` + graceful no-device error.
* [ ] `scripts/tts_demo.py --text "..."` + artifact output.
* [ ] Tests: CLI help + no-crash import checks.

---

## Maintenance

* [ ] Любое существенное архитектурное решение фиксировать в `docs/DECISIONS.md` (1–3 bullets).
* [ ] При изменении команд/setup обновлять `docs/RUNBOOK.md`.
* [ ] Never commit: `models/`, `data/` dumps, `runs/`, `.codex/**/logs/`, секреты/токены.
