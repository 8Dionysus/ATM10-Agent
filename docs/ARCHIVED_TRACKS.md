# ARCHIVED_TRACKS.md — atm10-agent

File for archived/recoverable directions that are not part of the active roadmap but are preserved for possible restoration.

## 1) Qwen3-ASR-0.6B OpenVINO Self-Conversion

Status: `archived / blocked_upstream`

Reason:

* On the target `transformers/optimum` stack, the `qwen3_asr` model is not recognized in the export flow.
* Latest confirmed status: `blocked_upstream`.

Reference artifacts are local-only historical runs from the original validation pass and are not part of the public repository surface.

Current policy:

* Active ASR path = `whisper_genai`.
* The `qwen_asr` runtime path is preserved as recoverable and is enabled only via explicit opt-in:
  * `scripts/asr_demo.py --allow-archived-qwen-asr`
  * `scripts/voice_runtime_service.py --asr-backend qwen_asr --allow-archived-qwen-asr`
  * `scripts/benchmark_asr_backends.py --include-archived-qwen-asr`

Re-open criteria:

* Upstream support for `qwen3_asr` is confirmed in the target toolchain.
* There is a successful `--execute` export run with a valid artifact contract.
* There is a smoke/e2e test without regression in the active voice path.

## 2) Qwen3-TTS

Status: `archived / deactivated`

Reason:

* It does not meet the operational latency/SLA for the current gameplay loop.
* The NPU compile path remains limited in the current pipeline.

Current policy:

* Operational TTS uses a separate fast-fallback runtime path (`tts_runtime_service`).
* `Qwen3-TTS` is kept only as historical reference artifacts.

Re-open criteria:

* Latency improvement to the target SLA is confirmed in a stable runtime.
* There is a reproducible export+runtime path without critical blockers.
