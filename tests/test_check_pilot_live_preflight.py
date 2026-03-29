from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import scripts.check_pilot_live_preflight as preflight


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_pilot_status(path: Path) -> None:
    _write_json(
        path,
        {
            "schema_version": "pilot_runtime_status_v1",
            "timestamp_utc": datetime(2026, 3, 28, 2, 0, 0, tzinfo=timezone.utc).isoformat(),
            "status": "running",
            "state": "idle",
            "effective_config": {
                "gateway_url": "http://127.0.0.1:8770",
                "voice_runtime_url": "http://127.0.0.1:8765",
                "tts_runtime_url": "http://127.0.0.1:8780",
                "input_device_index": 1,
            },
            "provider_init": {
                "vlm": {"status": "ok", "provider": "openvino", "device": "GPU", "warmup": {"ok": True}},
                "text": {"status": "ok", "provider": "openvino", "device": "CPU", "warmup": {"ok": True}},
            },
            "paths": {
                "run_dir": "runs/pilot-runtime/fixture",
                "status_json": str(path),
                "latest_status_json": str(path),
                "last_turn_json": None,
            },
        },
    )


class _RecorderOk:
    def __init__(self, sample_rate: int, preferred_input_device_index: int | None) -> None:
        _ = sample_rate, preferred_input_device_index

    def start(self) -> dict[str, Any]:
        return {"input_device_index": 1, "input_device_name": "Mic Array"}

    def stop_to_wav(self, *, output_path: Path) -> dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"RIFF")
        return {
            "audio_path": str(output_path),
            "input_device_index": 1,
            "input_device_name": "Mic Array",
            "selected_channel_index": 1,
            "channel_rms": [0.001, 0.12, 0.003, 0.002],
        }

    def discard(self) -> None:
        return


def _request_ok(*, url: str, timeout_sec: float, service_token: str | None) -> dict[str, Any]:
    _ = timeout_sec, service_token
    if url.endswith("/healthz"):
        return {"status": "ok"}
    if url.endswith(":8765/health"):
        return {"status": "ok", "service": "voice_runtime"}
    if url.endswith(":8780/health"):
        return {"status": "ok", "engines": {"piper": {"ok": True}}}
    return {"status": "ok"}


def test_check_pilot_live_preflight_ready_with_microphone_probe(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    pilot_status = runs_dir / "pilot-runtime" / "pilot_runtime_status_latest.json"
    _write_pilot_status(pilot_status)

    result = preflight.run_check_pilot_live_preflight(
        runs_dir=runs_dir,
        mic_probe_seconds=0.2,
        request_json_func=_request_ok,
        sleep_func=lambda _seconds: None,
        recorder_factory=_RecorderOk,
        prepare_audio_func=lambda **kwargs: {
            "audio_path": kwargs["audio_path"],
            "signal": {"status": "ok", "raw": {"status": "ok"}, "asr_input": {"status": "ok"}},
            "asr_preprocess": {"status": "ok", "mode": "copy", "gain_applied": 1.0},
        },
        asr_func=lambda **_kwargs: {"text": "привет, проверка", "language": "ru"},
        transcript_quality_func=lambda **_kwargs: {"status": "ok", "reason_codes": [], "transcript_used": True},
        now=datetime(2026, 3, 28, 2, 30, 0, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["schema_version"] == preflight.SCHEMA_VERSION
    assert summary["readiness_status"] == "ready"
    assert summary["blocking_reason_codes"] == []
    assert summary["checks"]["microphone_probe"]["status"] == "ok"
    assert Path(summary["paths"]["summary_json"]).is_file()
    assert Path(summary["paths"]["summary_md"]).is_file()


def test_check_pilot_live_preflight_blocks_when_pilot_status_missing(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"

    result = preflight.run_check_pilot_live_preflight(
        runs_dir=runs_dir,
        request_json_func=_request_ok,
        skip_mic_probe=True,
        now=datetime(2026, 3, 28, 2, 31, 0, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "blocked"
    assert "pilot_status_missing" in summary["blocking_reason_codes"]
    assert summary["next_step_code"] == "start_pilot_runtime"


def test_check_pilot_live_preflight_blocks_when_voice_runtime_unreachable(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    pilot_status = runs_dir / "pilot-runtime" / "pilot_runtime_status_latest.json"
    _write_pilot_status(pilot_status)

    def _request_partial(*, url: str, timeout_sec: float, service_token: str | None) -> dict[str, Any]:
        _ = timeout_sec, service_token
        if url.endswith(":8765/health"):
            raise RuntimeError("voice runtime offline")
        if url.endswith(":8780/health"):
            return {"status": "ok", "engines": {"piper": {"ok": True}}}
        return {"status": "ok"}

    result = preflight.run_check_pilot_live_preflight(
        runs_dir=runs_dir,
        request_json_func=_request_partial,
        skip_mic_probe=True,
        now=datetime(2026, 3, 28, 2, 32, 0, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "blocked"
    assert "voice_runtime_unreachable" in summary["blocking_reason_codes"]


def test_check_pilot_live_preflight_blocks_when_microphone_probe_low_signal(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    pilot_status = runs_dir / "pilot-runtime" / "pilot_runtime_status_latest.json"
    _write_pilot_status(pilot_status)

    result = preflight.run_check_pilot_live_preflight(
        runs_dir=runs_dir,
        mic_probe_seconds=0.2,
        request_json_func=_request_ok,
        sleep_func=lambda _seconds: None,
        recorder_factory=_RecorderOk,
        prepare_audio_func=lambda **kwargs: {
            "audio_path": kwargs["audio_path"],
            "signal": {"status": "low_signal", "raw": {"status": "low_signal"}, "asr_input": {"status": "ok"}},
            "asr_preprocess": {"status": "ok", "mode": "normalized_gain", "gain_applied": 12.0},
        },
        asr_func=lambda **_kwargs: {"text": "", "language": "ru"},
        transcript_quality_func=lambda **_kwargs: {
            "status": "low_signal",
            "reason_codes": ["empty", "audio_signal_low"],
            "transcript_used": False,
        },
        now=datetime(2026, 3, 28, 2, 33, 0, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "blocked"
    assert "microphone_probe_failed" in summary["blocking_reason_codes"]
    assert summary["checks"]["microphone_probe"]["status"] == "error"


def test_check_pilot_live_preflight_serializes_prepared_audio_path_on_asr_failure(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    pilot_status = runs_dir / "pilot-runtime" / "pilot_runtime_status_latest.json"
    _write_pilot_status(pilot_status)

    result = preflight.run_check_pilot_live_preflight(
        runs_dir=runs_dir,
        mic_probe_seconds=0.2,
        request_json_func=_request_ok,
        sleep_func=lambda _seconds: None,
        recorder_factory=_RecorderOk,
        prepare_audio_func=lambda **kwargs: {
            "audio_path": kwargs["audio_path"],
            "signal": {"status": "ok", "raw": {"status": "ok"}, "asr_input": {"status": "ok"}},
            "asr_preprocess": {"status": "ok", "mode": "copy", "gain_applied": 1.0},
        },
        asr_func=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("voice runtime offline")),
        transcript_quality_func=lambda **_kwargs: {"status": "ok", "reason_codes": [], "transcript_used": True},
        now=datetime(2026, 3, 28, 2, 34, 0, tzinfo=timezone.utc),
    )

    summary = json.loads(Path(result["summary_json_path"]).read_text(encoding="utf-8"))
    assert summary["readiness_status"] == "blocked"
    assert summary["checks"]["microphone_probe"]["status"] == "error"
    assert isinstance(summary["checks"]["microphone_probe"]["prepared_audio"]["audio_path"], str)
