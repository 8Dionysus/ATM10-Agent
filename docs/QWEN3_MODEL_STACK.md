# QWEN3 Model Stack (OpenVINO-first)

Актуально на: 2026-02-20 (updated)

## Active target stack

1. Text core LLM: `Qwen3-8B`
2. Vision core: `Qwen3-VL-4B-Instruct`
3. Retrieval: `Qwen3-Embedding-0.6B` + `Qwen3-Reranker-0.6B`
4. Voice IN: `Qwen3-ASR-0.6B`

Rule: no substitution to `Qwen2.5*`.

## Deactivated components

* `Qwen3-TTS-12Hz-0.6B-CustomVoice` + `Qwen3-TTS-Tokenizer-12Hz` removed from active stack on 2026-02-20.
* Причина: не проходит production SLA по latency и остается заблокированным для NPU compile-path в текущем OpenVINO pipeline.
* Все TTS-эксперименты оставлены только как архив артефактов (`runs/*qwen3-tts*`), без operational rollout.

## Local hardware profile (this repo host)

* CPU: `Intel Core Ultra 9 285H`
* RAM: `31.43 GiB`
* OpenVINO devices: `CPU`, `GPU` (`Intel Arc 140T`), `NPU` (`Intel AI Boost`)
* OpenVINO version: `2025.4.1`

## OpenVINO readiness matrix

### Use pre-converted OpenVINO models now

* Text core:
  * `OpenVINO/Qwen3-8B-int4-cw-ov` (NPU-oriented INT4)
  * fallback: `OpenVINO/Qwen3-8B-int8-ov`, `OpenVINO/Qwen3-8B-fp16-ov`
* Retrieval:
  * `OpenVINO/Qwen3-Embedding-0.6B-int8-ov` (or fp16)
  * `OpenVINO/Qwen3-Reranker-0.6B-fp16-ov`

### Self-convert to OpenVINO (project-owned conversion path)

* Vision:
  * source: `Qwen/Qwen3-VL-4B-Instruct`
  * export target: OpenVINO IR INT4 (`image-text-to-text`)
* Voice IN:
  * source: `Qwen/Qwen3-ASR-0.6B`
  * export target: OpenVINO IR (ASR pipeline, custom validation required)

## Baseline commands (active)

### Qwen3-VL -> OpenVINO IR

```powershell
# Dry-run (standard path, known upstream blocker)
python scripts/export_qwen3_openvino.py --preset qwen3-vl-4b

# Execute export (standard path, known upstream blocker)
python scripts/export_qwen3_openvino.py --preset qwen3-vl-4b --execute

# Working custom path (project-owned)
python scripts/export_qwen3_custom_openvino.py --preset qwen3-vl-4b --model-source models\hf_raw\qwen3-vl-4b
python scripts/export_qwen3_custom_openvino.py --preset qwen3-vl-4b --execute --model-source models\hf_raw\qwen3-vl-4b
```

### Qwen3-ASR -> OpenVINO IR (candidate path, validate first)

```powershell
# Dry-run
python scripts/export_qwen3_openvino.py --preset qwen3-asr-0.6b

# Execute export
python scripts/export_qwen3_openvino.py --preset qwen3-asr-0.6b --execute

# Dry-run custom exporter (with transformers support probe)
python scripts/export_qwen3_custom_openvino.py --preset qwen3-asr-0.6b

# Execute custom exporter (writes diagnostic in run.json on failure)
python scripts/export_qwen3_custom_openvino.py --preset qwen3-asr-0.6b --execute
```

## Archived Qwen3-TTS notes (history only)

* `qwen3-tts` custom/export/INT8/INT4 runs kept for reference.
* Historical artifacts:
  * `runs/20260220_214546-qwen3-tts-ov-helper-smoke/`
  * `runs/20260220_221511-qwen3-tts-ov-speed-bench-int8-cpu/`
  * `runs/20260220_222426-qwen3-tts-ov-speed-bench-int4-cpu/`
  * `runs/20260220_222650-qwen3-tts-npu-compile-diag-int4/`
* Эти path'ы не считаются active roadmap и не используются в production planning.

## Runtime policy

* Default runtime for active Qwen3 stack in this project: OpenVINO (`CPU|GPU|NPU`).
* OpenAI-compatible adapter stays in repo as gateway layer; it does not replace Qwen3 as core stack.
