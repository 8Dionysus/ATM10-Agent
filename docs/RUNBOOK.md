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
python -m pip install -r requirements-dev.txt
python -m pytest
```

## CI smoke (runnable scripts)

```powershell
python scripts/phase_a_smoke.py --vlm-provider stub --runs-dir runs/ci-smoke-phase-a
python scripts/retrieve_demo.py --in tests/fixtures/retrieval_docs_sample.jsonl --query "mekanism steel" --topk 3 --candidate-k 10 --reranker none --runs-dir runs/ci-smoke-retrieve
python scripts/eval_retrieval.py --docs tests/fixtures/retrieval_docs_sample.jsonl --eval tests/fixtures/retrieval_eval_sample.jsonl --topk 3 --candidate-k 10 --reranker none --runs-dir runs/ci-smoke-eval
```

## Qwen3 stack (OpenVINO-first)

Активный стек:

* `Qwen3-8B`
* `Qwen3-VL-4B-Instruct`
* `Qwen3-Embedding-0.6B`
* `Qwen3-Reranker-0.6B`
* `Qwen3-ASR-0.6B`

Деактивировано:

* `Qwen3-TTS-12Hz-0.6B-CustomVoice` (archived; не использовать в production runbook).

Подробная матрица: `docs/QWEN3_MODEL_STACK.md`.

### Qwen3-VL self-conversion (OpenVINO IR)

```powershell
# Dry-run
python scripts/export_qwen3_openvino.py --preset qwen3-vl-4b

# Real export (standard path may still be blocked upstream)
python scripts/export_qwen3_openvino.py --preset qwen3-vl-4b --execute

# Working custom path
python scripts/export_qwen3_custom_openvino.py --preset qwen3-vl-4b --model-source models\hf_raw\qwen3-vl-4b
python scripts/export_qwen3_custom_openvino.py --preset qwen3-vl-4b --execute --model-source models\hf_raw\qwen3-vl-4b
```

### Qwen3-ASR self-conversion (candidate path)

```powershell
# Dry-run
python scripts/export_qwen3_openvino.py --preset qwen3-asr-0.6b

# Real export
python scripts/export_qwen3_openvino.py --preset qwen3-asr-0.6b --execute

# Dry-run custom exporter
python scripts/export_qwen3_custom_openvino.py --preset qwen3-asr-0.6b

# Real custom export
python scripts/export_qwen3_custom_openvino.py --preset qwen3-asr-0.6b --execute
```

### Voice support probe + matrix

```powershell
# Probe current env
python scripts/probe_qwen3_voice_support.py

# Matrix dry-run / execute
python scripts/qwen3_voice_probe_matrix.py
python scripts/qwen3_voice_probe_matrix.py --execute
```

Ожидаемый результат:

* Создается `runs/<timestamp>-qwen3-voice-probe/`.
* Для активного roadmap проверяем в первую очередь `qwen3_asr`.

### Isolated upstream experiment

`qwen3-tts` экспериментальное `.venv-exp` окружение удалено из active path.
Если понадобится повторная проверка upstream, создавай новое изолированное окружение вручную.

### Qwen3 cache cleanup (disk pressure)

```powershell
Remove-Item models\hf_cache -Recurse -Force
Remove-Item models\hf_raw\qwen3-vl-4b\.cache -Recurse -Force
Remove-Item models\hf_raw\qwen3-vl-4b -Recurse -Force
Remove-Item "$env:USERPROFILE\.cache\huggingface" -Recurse -Force
```

## OpenVINO: setup + diagnostics

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -c "import openvino as ov; core=ov.Core(); print('openvino=', ov.__version__); print('devices=', core.available_devices)"
python scripts/openvino_diag.py
```

Ожидаемый результат:

* В `runs/<timestamp>-openvino/` создан `openvino_diag_all_devices.json`.

## M3: Voice runtime demos (active path = ASR)

Установка runtime deps:

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install "qwen-asr==0.0.6"
```

Примечание: `qwen-tts` деактивирован и не входит в active stack.

### ASR demo

```powershell
# File -> text
python scripts/asr_demo.py --audio-in "C:\path\to\sample.wav"

# Microphone -> text (5s)
python scripts/asr_demo.py --record-seconds 5
```

Ожидаемый результат:

* Создается `runs/<timestamp>-asr-demo/`.
* Внутри есть `run.json` и `transcription.json`.

### Long-lived voice runtime service (ASR only)

```powershell
# Service start
python scripts/voice_runtime_service.py --host 127.0.0.1 --port 8765

# Health
python scripts/voice_runtime_client.py --service-url http://127.0.0.1:8765 health

# ASR request
python scripts/voice_runtime_client.py --service-url http://127.0.0.1:8765 asr --audio-in "C:\path\to\sample.wav"
```

### TTS runtime service (separate process/container)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python -m pip install fastapi uvicorn
python scripts/tts_runtime_service.py --host 127.0.0.1 --port 8780
```

Принятый runtime design:

* Router: FastAPI
* Main engine: XTTS v2
* Fallback engines: Piper, Silero (для `ru` service voice)
* Techniques: prewarm, queue, chunking, phrase cache

Минимальная конфигурация adapters (env):

```powershell
# XTTS v2
$env:XTTS_MODEL_NAME="tts_models/multilingual/multi-dataset/xtts_v2"
$env:XTTS_USE_GPU="false"
# optional cloning wav for XTTS
# $env:XTTS_DEFAULT_SPEAKER_WAV="C:\path\to\speaker.wav"

# Piper fallback
$env:PIPER_EXECUTABLE="piper"
$env:PIPER_MODEL_PATH="C:\path\to\piper\en_US-model.onnx"
# optional
# $env:PIPER_SPEAKER="0"

# Silero (ru service voice)
$env:SILERO_REPO_OR_DIR="snakers4/silero-models"
$env:SILERO_MODEL_LANGUAGE="ru"
$env:SILERO_MODEL_ID="v4_ru"
$env:SILERO_SAMPLE_RATE="24000"
$env:SILERO_SPEAKER="xenia"
```

Пример запроса TTS:

```powershell
python scripts/tts_runtime_client.py --service-url http://127.0.0.1:8780 health
python scripts/tts_runtime_client.py --service-url http://127.0.0.1:8780 tts --text "crafting started" --language en
python scripts/tts_runtime_client.py --service-url http://127.0.0.1:8780 tts-stream --text "служебное сообщение" --language ru --service-voice
```

### Voice latency benchmark (historical)

Исторические артефакты `Qwen3-TTS` оставлены для reference в `runs/*qwen3-tts*`.
Для production game-loop этот путь деактивирован.

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

Опционально:

```powershell
python scripts/normalize_ftbquests.py --quests-dir "C:\path\to\config\ftbquests\quests"
```

## M2: Retrieval demo (in-memory)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/retrieve_demo.py --in data/ftbquests_norm --query "steel tools" --topk 5
```

Опционально, с rerank:

```powershell
python scripts/retrieve_demo.py --in data/ftbquests_norm --query "steel tools" --topk 5 --candidate-k 50 --reranker qwen3 --reranker-model "Qwen/Qwen3-Reranker-0.6B"
```

## M2: Retrieval eval benchmark

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/eval_retrieval.py --docs tests/fixtures/retrieval_docs_sample.jsonl --eval tests/fixtures/retrieval_eval_sample.jsonl --topk 3 --candidate-k 50 --reranker none
```

## M2: Qdrant ingest (optional backend)

```powershell
docker run --name atm10-qdrant -p 6333:6333 qdrant/qdrant
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/ingest_qdrant.py --in data/ftbquests_norm --collection atm10
```

## M2: Retrieval demo (qdrant backend)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/retrieve_demo.py --backend qdrant --collection atm10 --query "steel tools" --topk 5
```
