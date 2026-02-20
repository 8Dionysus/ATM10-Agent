# MANIFEST.md

Актуально на: 2026-02-20

## Снимок проекта

* Проект: `atm10-agent`
* Target platform: Windows 11 + PowerShell 7
* Target Python: 3.11+ (проверено на 3.12.10)
* Текущий статус tests: `12 passed` (`python -m pytest`)
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
  * Qdrant ingest + retrieval demo
  * top-k выдача с citations (`id`, `source`, `path`)
* Qdrant ingest идемпотентен, если collection уже существует (HTTP 409).

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
  * `normalize_ftbquests.py`
  * `ingest_qdrant.py`
  * `retrieve_demo.py`
* `tests/`
  * `test_discover_instance.py`
  * `test_phase_a_smoke.py`
  * `test_rag_doc_contract.py`
  * `test_ftbquests_ingest.py`
  * `test_retrieval_demo.py`
  * `test_qdrant_integration.py`

## Runtime artifacts

* Все runtime artifacts пишутся в `runs/<timestamp>/`.
* Типовые artifacts:
  * discovery: `instance_paths.json`
  * normalization: `ftbquests_paths.json`, `ingest_errors.jsonl`
  * phase A: `screenshot.png`, `run.json`, `response.json`
  * qdrant ingest: `run.json`, `ingest_summary.json`
  * retrieval: `run.json`, `retrieval_results.json`

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

## Политика данных и коммитов

Не коммитим:

* `models/**`
* `data/**` dumps
* `runs/**`
* `.codex/**/logs/**`
* secrets/tokens

## Текущий known gap

* Можно улучшить retrieval relevance внутри `chapters/*` через lightweight rerank и richer SNBT signal extraction.

## Ключевые документы

* `README.md`: high-level overview
* `PLANS.md`: milestones и прогресс
* `TODO.md`: actionable backlog
* `docs/RUNBOOK.md`: runnable commands
* `docs/DECISIONS.md`: architecture decisions log
