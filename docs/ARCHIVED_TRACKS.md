# ARCHIVED_TRACKS.md — atm10-agent

Файл для archived/recoverable направлений, которые не являются active roadmap,
но сохраняются для возможного восстановления.

## 1) Qwen3-ASR-0.6B OpenVINO Self-Conversion

Status: `archived / blocked_upstream`

Причина:

* На целевом стеке `transformers/optimum` модель `qwen3_asr` не распознается в export flow.
* Последний подтвержденный статус: `blocked_upstream`.

Reference artifacts:

* `runs/20260222_142450-qwen3-voice-probe/`
* `runs/20260222_142518-qwen3-custom-export/`

Current policy:

* Active ASR path = `whisper_genai`.
* `qwen_asr` path в runtime сохранен как recoverable и включается только explicit opt-in:
  * `scripts/asr_demo.py --allow-archived-qwen-asr`
  * `scripts/voice_runtime_service.py --asr-backend qwen_asr --allow-archived-qwen-asr`
  * `scripts/benchmark_asr_backends.py --include-archived-qwen-asr`

Re-open criteria:

* Upstream support для `qwen3_asr` подтвержден в целевом toolchain.
* Есть успешный `--execute` export run с валидным artifact contract.
* Есть smoke/e2e test без regression active voice path.

## 2) Qwen3-TTS

Status: `archived / deactivated`

Причина:

* Не проходит operational latency/SLA для текущего игрового цикла.
* NPU compile-path остается ограниченным в текущем pipeline.

Current policy:

* Для operational TTS используется отдельный fast-fallback runtime path (`tts_runtime_service`).
* `Qwen3-TTS` сохраняется только как historical reference artifacts.

Re-open criteria:

* Подтверждено улучшение latency до целевого SLA в стабильном runtime.
* Есть воспроизводимый export+runtime path без критичных blockers.
