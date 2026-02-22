# MANIFEST.md

Актуально на: 2026-02-22

## Снимок проекта

* Проект: `atm10-agent`
* Target platform: Windows 11 + PowerShell 7
* Target Python: 3.11+ (проверено на 3.12.10)
* Текущий статус tests: `99 passed` (`python -m pytest`)
* Статус по фазам:
  * Phase A baseline: done
  * Phase B baseline: done (`normalize -> ingest -> retrieve`)
  * Phase C: active ASR runtime demos + long-lived service/client implemented

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
* Зафиксирован model stack: `Qwen3` family only, policy `OpenVINO-first` (см. `docs/QWEN3_MODEL_STACK.md`).
* `Qwen3-VL-4B-Instruct` успешно конвертирован в OpenVINO IR через custom pipeline
  (`runs/20260220_150028-qwen3-custom-export/`, output: `models/qwen3-vl-4b-instruct-ov-custom`).
* Voice runtime path (active) реализован через native Qwen packages:
  * `scripts/asr_demo.py` (audio file/microphone -> `transcription.json`)
  * `scripts/voice_runtime_service.py` + `scripts/voice_runtime_client.py` (long-lived runtime, ASR path)
  * shared runtime layer: `src/agent_core/io_voice.py`
* Voice latency benchmark (2026-02-20):
  * `runs/20260220_211505-voice-latency-bench/latency_summary.json`
  * `runs/20260220_211708-voice-latency-oneshot-bench/latency_oneshot_summary.json`
  * вывод: SLA `<=2s` на текущем CPU runtime выполняется для ASR; `Qwen3-TTS` path archived/deactivated.

## Структура репозитория

* `src/agent_core/`
  * `vlm.py`: VLM interface contract
  * `vlm_stub.py`: deterministic stub provider
  * `io_voice.py`: voice runtime wrappers + audio IO helpers (active ASR path)
* `src/rag/`
  * `doc_contract.py`: JSONL contract + validation
  * `ftbquests_ingest.py`: discovery и normalization квестов
  * `retrieval.py`: in-memory retrieval + Qdrant REST integration
* `scripts/`
  * `discover_instance.py`
  * `asr_demo.py`
  * `asr_demo_whisper_genai.py`
  * `benchmark_asr_backends.py`
  * `export_qwen3_custom_openvino.py`
  * `export_qwen3_openvino.py`
  * `phase_a_smoke.py`
  * `openvino_diag.py`
  * `normalize_ftbquests.py`
  * `ingest_qdrant.py`
  * `retrieve_demo.py`
  * `eval_retrieval.py`
  * `run_qwen3_openvino.ps1`
  * `start_voice_whisper_npu.ps1`
  * `voice_runtime_service.py`
  * `voice_runtime_client.py`
  * `tts_demo.py` (archived)
* `tests/`
  * `test_discover_instance.py`
  * `test_asr_demo.py`
  * `test_asr_demo_whisper_genai.py`
  * `test_benchmark_asr_backends.py`
  * `test_export_qwen3_openvino.py`
  * `test_export_qwen3_custom_openvino.py`
  * `test_phase_a_smoke.py`
  * `test_openvino_diag.py`
  * `test_rag_doc_contract.py`
  * `test_ftbquests_ingest.py`
  * `test_retrieval_demo.py`
  * `test_voice_runtime_service.py`
  * `test_voice_runtime_client.py`
  * `test_qdrant_integration.py`
  * `test_eval_retrieval.py`
  * `test_tts_demo.py` (archived)

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
  * ASR demo: `run.json`, `transcription.json`

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

* Подготовить рабочий self-conversion path для `Qwen3-ASR-0.6B`.
  * Исторический блокер: `qwen3_asr` в upstream export flow (`transformers/optimum`).
  * Текущий статус (2026-02-22): после прогона в `.venv` с export toolchain probe-status=`blocked_upstream`,
    unlock-gate=`ready=false` (artifacts: `runs/20260222_142450-qwen3-voice-probe/`,
    `runs/20260222_142518-qwen3-custom-export/`).

## Ключевые документы

* `README.md`: high-level overview
* `PLANS.md`: milestones и прогресс
* `TODO.md`: actionable backlog
* `docs/RUNBOOK.md`: runnable commands
* `docs/DECISIONS.md`: architecture decisions log
* `docs/QWEN3_MODEL_STACK.md`: approved Qwen3 stack + OpenVINO readiness/conversion map
* `docs/SESSION_2026-02-20.md`: исторический session snapshot (ключевые результаты и метрики)
* `docs/SESSION_2026-02-22.md`: актуальный session snapshot (baseline + open gaps)
