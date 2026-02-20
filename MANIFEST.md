# MANIFEST.md

Актуально на: 2026-02-20

## Снимок проекта

* Проект: `atm10-agent`
* Target platform: Windows 11 + PowerShell 7
* Target Python: 3.11+ (проверено на 3.12.10)
* Текущий статус tests: `25 passed` (`python -m pytest`)
* Статус по фазам:
  * Phase A baseline: done
  * Phase B baseline: done (`normalize -> ingest -> retrieve`)
  * Phase C: not started

## Что работает сейчас

* Discovery путей Minecraft/ATM10 через env vars + fallback.
* Phase A smoke-runner пишет artifacts:
  * `screenshot.png`
  * `run.json`
  * `response.json`
* Phase B normalization:
  * поддержка FTB Quests файлов `.json` и `.snbt`
  * default-фильтрация шумных веток `lang/**` и `reward_tables/**`
  * output в `data/ftbquests_norm/quests.jsonl`
* Phase B retrieval:
  * in-memory retrieval demo
  * staged retrieval (`candidate-k` + optional `Qwen3-Reranker-0.6B`)
  * runtime switch для reranker: `torch|openvino` + device `AUTO|CPU|GPU|NPU`
  * Qdrant ingest + retrieval demo
  * top-k выдача с citations (`id`, `source`, `path`)
  * retrieval benchmark (`scripts/eval_retrieval.py`) с метриками Recall@k / MRR@k / hit-rate
  * first-stage ranking: field-weighted scoring (`title/text/tags`) + stopword filtering
* Qdrant ingest идемпотентен, если collection уже существует (HTTP 409).
* SNBT extraction для `chapters/*` поддерживает quoted + unquoted ключи
  (`id/type/dimension/structure/filename/...`).
* По real ATM10 eval (`runs/20260220_m2_baseline/eval_cases_atm10_chapters.jsonl`) после tuning:
  `Recall@5=1.0000`, `MRR@5=1.0000`, `hit-rate@5=1.0000` (`runs/20260220_132946/`).
* Production defaults retrieval по калибровке: `topk=5`, `candidate_k=50`, `reranker=none`.
* EOL policy зафиксирована в `.gitattributes` (LF для source/docs/config, CRLF для `*.ps1/*.bat/*.cmd`).

## Структура репозитория

* `src/agent_core/`
  * `vlm.py`: VLM interface contract
  * `vlm_stub.py`: deterministic stub provider
* `src/rag/`
  * `doc_contract.py`: JSONL contract + validation
  * `ftbquests_ingest.py`: discovery и normalization квестов
  * `retrieval.py`: in-memory retrieval + Qdrant REST integration
* `scripts/`
  * `discover_instance.py`
  * `phase_a_smoke.py`
  * `openvino_diag.py`
  * `normalize_ftbquests.py`
  * `ingest_qdrant.py`
  * `retrieve_demo.py`
  * `eval_retrieval.py`
  * `run_qwen3_openvino.ps1`
* `tests/`
  * `test_discover_instance.py`
  * `test_phase_a_smoke.py`
  * `test_openvino_diag.py`
  * `test_rag_doc_contract.py`
  * `test_ftbquests_ingest.py`
  * `test_retrieval_demo.py`
  * `test_qdrant_integration.py`
  * `test_eval_retrieval.py`

## Runtime artifacts

* Все runtime artifacts пишутся в `runs/<timestamp>/`.
* Типовые artifacts:
  * discovery: `instance_paths.json`
  * normalization: `ftbquests_paths.json`, `ingest_errors.jsonl`
  * phase A: `screenshot.png`, `run.json`, `response.json`
  * openvino diag: `run.json`, `openvino_diag_all_devices.json`
  * qdrant ingest: `run.json`, `ingest_summary.json`
  * retrieval: `run.json`, `retrieval_results.json`
  * retrieval eval: `run.json`, `eval_results.json`

## Основные команды

* Активация venv:
  * `cd D:\atm10-agent`
  * `.\.venv\Scripts\Activate.ps1`
* Запуск tests:
  * `python -m pytest`
* Нормализация квестов:
  * `python scripts/normalize_ftbquests.py`
* Ingest в Qdrant:
  * `python scripts/ingest_qdrant.py --in data/ftbquests_norm --collection atm10`
* Retrieval из Qdrant:
  * `python scripts/retrieve_demo.py --backend qdrant --collection atm10 --query "mekanism" --topk 5`
* Retrieval eval benchmark:
  * `python scripts/eval_retrieval.py --docs tests/fixtures/retrieval_docs_sample.jsonl --eval tests/fixtures/retrieval_eval_sample.jsonl --topk 3 --candidate-k 50 --reranker none`

## Политика данных и коммитов

Не коммитим:

* `models/**`
* `data/**` dumps
* `runs/**`
* `.codex/**/logs/**`
* secrets/tokens

## Текущий known gap

* Заменить `deterministic_stub_v1` на real VLM provider через текущий интерфейс без поломки Phase A loop.
* Решить политику `requirements-dev.txt` (разделение runtime/dev зависимостей).

## Ключевые документы

* `README.md`: high-level overview
* `PLANS.md`: milestones и прогресс
* `TODO.md`: actionable backlog
* `docs/RUNBOOK.md`: runnable commands
* `docs/DECISIONS.md`: architecture decisions log
* `docs/SESSION_2026-02-20.md`: session snapshot (ключевые результаты и метрики)
