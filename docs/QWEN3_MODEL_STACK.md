# Model Stack and Host Runtime Profiles (OpenVINO-first)

Current as of: 2026-03-28

This file keeps the historical path `docs/QWEN3_MODEL_STACK.md` for continuity, but it now records the machine-specific runtime policy for `ATM10-Agent`, not only a Qwen3-only stack snapshot.

## Architecture posture

- `ATM10-Agent` is a local-first ATM10 companion with active operator-facing entrypoints and an internal agent stack built on top of perception, memory, routing, evals, dry-run automation, and artifacted worker-style processes.
- Runtime backend choice is a host-profile decision. A host profile selects the inference/runtime path for one machine; it does not redefine the repo architecture.
- The current baseline is the validated Intel/OpenVINO host path on this repo machine. Future `NVIDIA`/`Ollama` or other paths should land as explicit additive host profiles with their own measurements, evals, and promotion criteria.

## Canonical current host profile

- Host profile id: `ov_intel_core_ultra_local`
- Status: current validated repo-host baseline
- Runtime family: `OpenVINO-first`
- Placement policy: explicit per-stage `CPU/GPU/NPU` placement with artifacted measurement; use multi-accelerator parallelism where it helps instead of silently swapping the entire stack
- Promotion rule: this profile remains canonical until another host profile is explicitly documented, evaluated, and promoted

## Future host profiles (additive)

- Expected examples: `ollama_nvidia_local`, `cuda_native_local`, or another explicit machine-specific path
- New host profiles must document their own runtime assumptions, model choices, eval posture, and operator/pilot launch notes
- Adding a future host profile does not silently rewrite `ov_intel_core_ultra_local`; the current baseline remains the default until public docs and validation say otherwise

## Active target stack

1. Text core LLM: `Qwen3-8B`
2. Vision core: `Qwen2.5-VL-7B-Instruct`
3. Retrieval: `Qwen3-Embedding-0.6B` + `Qwen3-Reranker-0.6B`
4. Voice IN (active runtime): `Whisper v3 Turbo (OpenVINO GenAI)`
5. Voice OUT (active runtime): `tts_runtime_service`

Rule: prefer the strongest locally supported OpenVINO path per task on `ov_intel_core_ultra_local`. `Qwen3` remains the default text/retrieval family, but the active pilot vision path is allowed to use `Qwen2.5-VL` when current OpenVINO VLM runtime support is better.

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

* Default runtime for the active repo-host stack in this project: OpenVINO (`CPU|GPU|NPU`).
* Device placement is stage-specific and may exploit multiple accelerators in parallel when the repo host supports it.
* Pilot/Gateway surfaces stay local-first and artifacted under `runs/...`.
* Future non-OpenVINO paths must arrive as explicit host profiles instead of silent backend swaps.
* The OpenAI-compatible adapter remains in the repo as an optional gateway layer; it does not replace the local OpenVINO stack as the pilot baseline.
