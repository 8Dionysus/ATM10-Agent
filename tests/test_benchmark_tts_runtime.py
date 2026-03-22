from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.benchmark_tts_runtime import run_benchmark_tts_runtime
from src.agent_core.tts_runtime import CallbackTTSEngine, TTSRuntimeService, make_silence_wav_bytes


def _write_manifest(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                json.dumps({"id": "tts_1", "text": "Hello operator", "language": "en"}),
                json.dumps({"id": "tts_2", "text": "Service voice fallback", "language": "ru", "service_voice": True}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _service_with_audio(*, empty_audio: bool = False) -> TTSRuntimeService:
    def _synthesize(_text: str, _language: str, _speaker: str | None) -> tuple[bytes, int]:
        if empty_audio:
            return b"", 22050
        return make_silence_wav_bytes(duration_ms=320, sample_rate=22050), 22050

    engine = CallbackTTSEngine(name="fake_tts", synthesize_fn=_synthesize, prewarm_fn=lambda: None)
    return TTSRuntimeService(
        xtts_engine=engine,
        piper_engine=engine,
        silero_engine=engine,
        max_chunk_chars=220,
        queue_size=8,
        cache=None,
    )


def test_run_benchmark_tts_runtime_writes_summary_and_service_sla(tmp_path: Path) -> None:
    manifest_path = tmp_path / "tts_manifest.jsonl"
    _write_manifest(manifest_path)

    result = run_benchmark_tts_runtime(
        manifest=manifest_path,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 3, 22, 18, 0, 0, tzinfo=timezone.utc),
        service=_service_with_audio(),
    )

    run_dir = result["run_dir"]
    summary_payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    service_sla_payload = json.loads((run_dir / "service_sla_summary.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260322_180000-tts-runtime-bench"
    assert summary_payload["schema_version"] == "tts_runtime_benchmark_summary_v1"
    assert summary_payload["summary"]["num_ok"] == 2
    assert service_sla_payload["schema_version"] == "service_sla_summary_v1"
    assert service_sla_payload["service_name"] == "voice_tts"
    assert service_sla_payload["status"] == "ok"
    assert service_sla_payload["quality"]["non_empty_audio_rate"] == 1.0


def test_run_benchmark_tts_runtime_marks_empty_audio_as_error(tmp_path: Path) -> None:
    manifest_path = tmp_path / "tts_manifest.jsonl"
    _write_manifest(manifest_path)

    result = run_benchmark_tts_runtime(
        manifest=manifest_path,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 3, 22, 18, 15, 0, tzinfo=timezone.utc),
        service=_service_with_audio(empty_audio=True),
    )

    service_sla_payload = json.loads(
        (result["run_dir"] / "service_sla_summary.json").read_text(encoding="utf-8")
    )
    assert result["ok"] is True
    assert service_sla_payload["status"] == "error"
    assert "empty_audio_detected" in service_sla_payload["breaches"]
