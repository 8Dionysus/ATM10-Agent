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

Опционально: тот же `qwen3` через OpenVINO runtime (рекомендуется на Intel iGPU/NPU):

```powershell
python scripts/retrieve_demo.py --in data/ftbquests_norm --query "steel tools" --topk 5 --candidate-k 10 --reranker qwen3 --reranker-runtime openvino --reranker-device GPU --reranker-model "Qwen/Qwen3-Reranker-0.6B" --reranker-max-length 512
```

Быстрый wrapper (автоматически подтягивает `VsDevCmd` + UTF-8 env):

```powershell
.\scripts\run_qwen3_openvino.ps1 -Mode retrieve -Query "steel tools" -InputPath "data/ftbquests_norm/quests.jsonl" -Device GPU -TopK 5 -CandidateK 10 -RerankerMaxLength 512
```

Примечание: `--reranker qwen3` требует дополнительных зависимостей (`transformers`, `torch`) и загрузки модели; по умолчанию baseline использует `--reranker none`.
Для OpenVINO-ускорения qwen3 добавь `--reranker-runtime openvino` и выбери `--reranker-device` (`AUTO|CPU|GPU|NPU`).
Если получаешь ошибку про `cl.exe`, установи Visual Studio Build Tools (C++ workload) и запусти команду из Developer PowerShell.
Для стабильного запуска на Windows также рекомендуем UTF-8 окружение:
`$env:PYTHONUTF8=\"1\"; $env:PYTHONIOENCODING=\"utf-8\"`.

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

Опционально: eval с OpenVINO runtime:

```powershell
python scripts/eval_retrieval.py --docs tests/fixtures/retrieval_docs_sample.jsonl --eval tests/fixtures/retrieval_eval_sample.jsonl --topk 3 --candidate-k 10 --reranker qwen3 --reranker-runtime openvino --reranker-device GPU --reranker-model "Qwen/Qwen3-Reranker-0.6B" --reranker-max-length 512
```

Тот же eval через wrapper:

```powershell
.\scripts\run_qwen3_openvino.ps1 -Mode eval -EvalDocsPath "tests/fixtures/retrieval_docs_sample.jsonl" -EvalCasesPath "tests/fixtures/retrieval_eval_sample.jsonl" -Device GPU -TopK 3 -CandidateK 10 -RerankerMaxLength 512
```

### M2: Calibration на реальном ATM10 corpus (`chapters/*`)

Пример локального grid-eval (baseline `reranker=none`):

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/eval_retrieval.py --backend in_memory --docs data/ftbquests_norm/quests.jsonl --eval runs/20260220_m2_baseline/eval_cases_atm10_chapters.jsonl --topk 1 --candidate-k 5 --reranker none
python scripts/eval_retrieval.py --backend in_memory --docs data/ftbquests_norm/quests.jsonl --eval runs/20260220_m2_baseline/eval_cases_atm10_chapters.jsonl --topk 3 --candidate-k 50 --reranker none
python scripts/eval_retrieval.py --backend in_memory --docs data/ftbquests_norm/quests.jsonl --eval runs/20260220_m2_baseline/eval_cases_atm10_chapters.jsonl --topk 5 --candidate-k 50 --reranker none
```

Зафиксированный результат калибровки (2026-02-20, `runs/20260220_m2_calibration_none/`):

* Production defaults: `topk=5`, `candidate_k=50`, `reranker=none`.
* На этом наборе `topk>=3` даёт одинаковые метрики (`recall_at_k=1.0`, `mrr_at_k=0.9333`, `hit_rate_at_k=1.0`) до quality-tuning первого этапа.
* `topk=1` уступает по `recall/hit-rate` (`0.9`).

После quality-tuning `chapters/*` (field-weighted first-stage scoring + stopword filtering):

```powershell
python scripts/eval_retrieval.py --backend in_memory --docs data/ftbquests_norm/quests.jsonl --eval runs/20260220_m2_baseline/eval_cases_atm10_chapters.jsonl --topk 5 --candidate-k 50 --reranker none
```

Результат (2026-02-20, `runs/20260220_132946/`):

* `recall_at_k=1.0000`
* `mrr_at_k=1.0000`
* `hit_rate_at_k=1.0000`

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
