# Model Stack (OpenVINO-first)

Current as of: 2026-03-23

This file keeps the historical path `docs/QWEN3_MODEL_STACK.md` for continuity, but the active local stack is now task-first rather than Qwen3-only.

## Active target stack

1. Text core LLM: `Qwen3-8B`
2. Vision core: `Qwen2.5-VL-7B-Instruct`
3. Retrieval: `Qwen3-Embedding-0.6B` + `Qwen3-Reranker-0.6B`
4. Voice IN (active runtime): `Whisper v3 Turbo (OpenVINO GenAI)`
5. Voice OUT (active runtime): `tts_runtime_service`

Rule: prefer the strongest locally supported OpenVINO path per task. `Qwen3` remains the default text/retrieval family, but the active pilot vision path is allowed to use `Qwen2.5-VL` when current OpenVINO VLM runtime support is better.

## Pilot runtime defaults

* Grounded reply text core: `models/qwen3-8b-int4-cw-ov` on `GPU`
* Live screen grounding: `models/qwen2.5-vl-7b-instruct-int4-ov` on `GPU`
* ASR: `models/whisper-large-v3-turbo-ov` on `NPU`

## Archived / recoverable components

* `Qwen3-TTS-12Hz-0.6B-CustomVoice` + `Qwen3-TTS-Tokenizer-12Hz` remain removed from the active stack.
  * Reason: they do not meet production latency SLA and remain blocked for the preferred NPU path.
* `Qwen3-ASR-0.6B` remains archived/recoverable.
  * Reason: the active ASR path is Whisper GenAI; restore only through explicit opt-in flags.
* `Qwen3-VL-4B-Instruct` custom OpenVINO export is archived for the active pilot path.
  * Reason: the current OpenVINO GenAI VLM runtime rejects the exported `qwen3_vl` model type, so it is not used as the launch-gate vision baseline.

## Local hardware/runtime profile

* CPU: `Intel Core Ultra 9 285H`
* RAM: `31.43 GiB`
* OpenVINO devices: `CPU`, `GPU` (`Intel Arc 140T`), `NPU` (`Intel AI Boost`)
* OpenVINO version: `2026.0.0`
* OpenVINO GenAI version: `2026.0.0.0`

## OpenVINO readiness matrix

### Use pre-converted OpenVINO models now

* Text core:
  * `OpenVINO/Qwen3-8B-int4-cw-ov` (preferred `GPU` for the active pilot runtime on the repo host)
  * fallback: `OpenVINO/Qwen3-8B-int8-ov`, `OpenVINO/Qwen3-8B-fp16-ov`
* Vision:
  * `OpenVINO/Qwen2.5-VL-7B-Instruct-int4-ov` (preferred `GPU`)
  * `CPU` fallback is valid for diagnostics; `NPU` is not the current default for this model on the repo host
* Retrieval:
  * `OpenVINO/Qwen3-Embedding-0.6B-int8-ov` (or fp16)
  * `OpenVINO/Qwen3-Reranker-0.6B-fp16-ov`

### Archived conversion tracks (do not use as pilot launch-gate)

* Vision:
  * source: `Qwen/Qwen3-VL-4B-Instruct`
  * status: archived experiment, blocked for the active OpenVINO GenAI VLM runtime path
* Voice IN:
  * source: `Qwen/Qwen3-ASR-0.6B`
  * status: archived candidate path, validate before restore

## Runtime policy

* Default runtime for the active local stack in this project: OpenVINO (`CPU|GPU|NPU`).
* Pilot/Gateway surfaces stay local-first and artifacted under `runs/...`.
* The OpenAI-compatible adapter remains in the repo as an optional gateway layer; it does not replace the local OpenVINO stack as the pilot baseline.
