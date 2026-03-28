# ARCHIVED_TRACKS.md - atm10-agent

This document is the public home for archived, recoverable, and historical command references.
Active runnable commands stay in `docs/RUNBOOK.md`.
Host-profile and model-stack posture stays in `docs/QWEN3_MODEL_STACK.md`.

## 1) Qwen3-ASR-0.6B OpenVINO self-conversion

Status: `archived / blocked_upstream`

Reason:

* On the target `transformers/optimum` stack, the `qwen3_asr` model is not recognized in the export flow.
* Latest confirmed status remains `blocked_upstream`.

Current policy:

* Active ASR path = `whisper_genai`.
* The `qwen_asr` runtime path is recoverable only through explicit opt-in flags and is not part of the active runbook.

Archived command references:

```powershell
# Dry-run conversion
python scripts/export_qwen3_openvino.py --preset qwen3-asr-0.6b
python -m scripts.export_qwen3_custom_openvino --preset qwen3-asr-0.6b

# Execute conversion
python scripts/export_qwen3_openvino.py --preset qwen3-asr-0.6b --execute
python -m scripts.export_qwen3_custom_openvino --preset qwen3-asr-0.6b --execute

# Archived demo path
python scripts/asr_demo.py --allow-archived-qwen-asr --audio-in "<path-to-sample.wav>"
python scripts/asr_demo.py --allow-archived-qwen-asr --record-seconds 5

# Archived runtime rollback
python scripts/voice_runtime_service.py --host 127.0.0.1 --port 8765 --asr-backend qwen_asr --allow-archived-qwen-asr --asr-model Qwen/Qwen3-ASR-0.6B

# Optional archived backend compare
python scripts/benchmark_asr_backends.py --inputs "<path-to-sample.wav>" --backends whisper_genai --include-archived-qwen-asr --whisper-model-dir models\whisper-large-v3-turbo-ov --whisper-device NPU
```

Notes:

* `--execute` requires the export toolchain (`transformers`, `optimum`, `optimum-intel`).
* In a runtime-only environment, dry-run may return `support_probe.status=import_error`.

Re-open criteria:

* Upstream support for `qwen3_asr` is confirmed in the target toolchain.
* There is a successful `--execute` export run with a valid artifact contract.
* There is a smoke/e2e test without regression in the active voice path.

## 2) Qwen3 voice-family upstream monitoring

Status: `archived / monitoring_only`

Purpose:

* Keep lightweight research-only probes available without presenting them as active runtime guidance.

Archived command references:

```powershell
python scripts/probe_qwen3_voice_support.py
python scripts/qwen3_voice_probe_matrix.py
python scripts/qwen3_voice_probe_matrix.py --execute
```

Current policy:

* The historical `qwen3-tts` experimental `.venv-exp` environment is removed from the active path.
* If upstream support needs to be re-checked, create a fresh isolated environment instead of treating an old experiment as a baseline.

## 3) Qwen3-TTS

Status: `archived / deactivated`

Reason:

* It does not meet the operational latency/SLA for the current gameplay loop.
* The NPU compile path remains limited in the current pipeline.

Current policy:

* Operational TTS uses the active `tts_runtime_service` path.
* Historical `Qwen3-TTS` artifacts under `runs/*qwen3-tts*` remain local-only references, not a public repo contract.

Re-open criteria:

* Latency improvement to the target SLA is confirmed in a stable runtime.
* There is a reproducible export+runtime path without critical blockers.

## 4) Qwen3-VL-4B custom OpenVINO export

Status: `archived / blocked_for_active_pilot`

Reason:

* The current OpenVINO GenAI VLM runtime does not accept the `qwen3_vl` model type produced by that export path.

Current policy:

* The active pilot vision baseline stays on `Qwen2.5-VL-7B-Instruct`.
* Treat the custom `Qwen3-VL-4B-Instruct` export as recoverable reference material only.
* Use `docs/QWEN3_MODEL_STACK.md` as the canonical posture document for the active and archived vision stack.
