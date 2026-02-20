# RUNBOOK

## M0: Instance discovery

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/discover_instance.py
```

Ожидаемый результат:

* Создается `runs/<timestamp>/instance_paths.json`.
* В консоль печатается summary по найденным путям и marker-папкам.

## Tests

```powershell
python -m pytest
```

## OpenVINO: setup + diagnostics

Установка в venv:

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Быстрая проверка версии и устройств:

```powershell
python -c "import openvino as ov; core=ov.Core(); print('openvino=', ov.__version__); print('devices=', core.available_devices)"
```

Полная диагностика с artifact в `runs/<timestamp>/`:

```powershell
python scripts/openvino_diag.py
```

Ожидаемый результат:

* В консоли есть путь к `run_dir` и `diag_json`.
* В `runs/<timestamp>-openvino/` создан `openvino_diag_all_devices.json`.
* Для `CPU` (и доступных `GPU/NPU`) поля `compile_ok=true` и `infer_ok=true`.

## M1: Phase A smoke

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/phase_a_smoke.py
```

Ожидаемый результат:

* Создается `runs/<timestamp>/`.
* Внутри есть `screenshot.png`, `run.json`, `response.json`.

## M2: FTB Quests normalization

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/normalize_ftbquests.py
```

Опционально можно передать путь напрямую:

```powershell
python scripts/normalize_ftbquests.py --quests-dir "C:\path\to\config\ftbquests\quests"
```

Ожидаемый результат:

* Создается `data/ftbquests_norm/quests.jsonl`.
* В `runs/<timestamp>/` создаются `ftbquests_paths.json` и `ingest_errors.jsonl`.
* Поддерживаются `.json` и `.snbt` файлы FTB Quests; unsupported форматы логируются в `ingest_errors.jsonl`.
* По умолчанию шумные ветки `lang/**` и `reward_tables/**` исключаются из индекса (считаются как `skipped_filtered` в summary).

Пример текущего ATM10 baseline (2026-02-20):

* `docs_written=65`
* `errors_logged=1` (`README.md` как unsupported extension)
* `skipped_filtered=641`

## M2: Retrieval demo (in-memory)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/retrieve_demo.py --in data/ftbquests_norm --query "steel tools" --topk 5
```

Ожидаемый результат:

* Создается `runs/<timestamp>/`.
* Внутри есть `run.json` и `retrieval_results.json`.
* В консоли печатаются `top-k` результатов с citations (`id/source/path`).

Опционально: двухэтапный retrieval с rerank-кандидатами:

```powershell
python scripts/retrieve_demo.py --in data/ftbquests_norm --query "steel tools" --topk 5 --candidate-k 50 --reranker none
```

Опционально: специализированный rerank через `Qwen3-Reranker`:

```powershell
python scripts/retrieve_demo.py --in data/ftbquests_norm --query "steel tools" --topk 5 --candidate-k 50 --reranker qwen3 --reranker-model "Qwen/Qwen3-Reranker-0.6B"
```

Примечание: `--reranker qwen3` требует дополнительных зависимостей (`transformers`, `torch`) и загрузки модели; по умолчанию baseline использует `--reranker none`.

Установка optional deps для `qwen3`:

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python -m pip install "transformers>=4.51.0" "torch>=2.4.0"
```

Практика запуска:

* Первый `qwen3` run заметно медленнее из-за download/model load.
* Повторные runs быстрее (warm cache).

## M2: Retrieval eval benchmark (Recall@k / MRR@k)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/eval_retrieval.py --docs tests/fixtures/retrieval_docs_sample.jsonl --eval tests/fixtures/retrieval_eval_sample.jsonl --topk 3 --candidate-k 50 --reranker none
```

Ожидаемый результат:

* Создается `runs/<timestamp>/`.
* Внутри есть `run.json` и `eval_results.json`.
* В консоли печатаются агрегированные метрики (`recall_at_k`, `mrr_at_k`, `hit_rate_at_k`).

Опционально можно сравнить с rerank:

```powershell
python scripts/eval_retrieval.py --docs tests/fixtures/retrieval_docs_sample.jsonl --eval tests/fixtures/retrieval_eval_sample.jsonl --topk 3 --candidate-k 50 --reranker qwen3 --reranker-model "Qwen/Qwen3-Reranker-0.6B"
```

## M2: Qdrant ingest (optional backend)

Поднять локальный Qdrant (пример):

```powershell
docker run --name atm10-qdrant -p 6333:6333 qdrant/qdrant
```

Ingest:

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/ingest_qdrant.py --in data/ftbquests_norm --collection atm10
```

Ожидаемый результат:

* Создается `runs/<timestamp>/`.
* Внутри есть `run.json` и `ingest_summary.json`.
* В summary видны `collection_created`, `docs_ingested` и `upsert_calls`.
* Если коллекция уже существует, ingest не падает и продолжает upsert.

Пример текущего ATM10 baseline (2026-02-20):

* `docs_ingested=65`
* `upsert_calls=1`

## M2: Retrieval demo (qdrant backend)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/retrieve_demo.py --backend qdrant --collection atm10 --query "steel tools" --topk 5
```

Ожидаемый результат:

* Создается `runs/<timestamp>/`.
* Внутри есть `run.json` и `retrieval_results.json`.
* В консоли печатаются `top-k` результатов с citations (`id/source/path`).

## M2: End-to-end baseline (ATM10 local)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/normalize_ftbquests.py
python scripts/ingest_qdrant.py --in data/ftbquests_norm --collection atm10
python scripts/retrieve_demo.py --backend qdrant --collection atm10 --query "mekanism" --topk 5
```
