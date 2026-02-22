from __future__ import annotations

import json
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

import scripts.asr_demo as asr_demo


def _write_test_wav(path: Path, *, sample_rate: int = 16000) -> None:
    t = np.linspace(0, 0.05, int(sample_rate * 0.05), endpoint=False)
    waveform = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    pcm16 = np.clip(waveform, -1.0, 1.0)
    pcm16 = (pcm16 * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())


def test_asr_demo_audio_file_mode_writes_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _FakeASRClient:
        @classmethod
        def from_pretrained(cls, *, model_id: str, device_map: str, dtype: str, max_new_tokens: int):
            assert model_id == "Qwen/Qwen3-ASR-0.6B"
            assert device_map == "auto"
            assert dtype == "auto"
            assert max_new_tokens == 512
            return cls()

        def transcribe_path(self, *, audio_path: Path, context: str, language: str | None) -> dict[str, str]:
            assert audio_path.exists()
            assert context == ""
            assert language is None
            return {"text": "hello from fake asr", "language": "english"}

    monkeypatch.setattr(asr_demo, "QwenASRClient", _FakeASRClient)

    audio_in = tmp_path / "input.wav"
    _write_test_wav(audio_in)
    result = asr_demo.run_asr_demo(
        audio_in=audio_in,
        runs_dir=tmp_path / "runs",
        allow_archived_qwen_asr=True,
        now=datetime(2026, 2, 20, 21, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    result_payload = json.loads((run_dir / "transcription.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260220_210000-asr-demo"
    assert run_payload["status"] == "ok"
    assert result_payload["text"] == "hello from fake asr"
    assert Path(result_payload["audio_path"]).exists()


def test_asr_demo_requires_exactly_one_audio_input_mode(tmp_path: Path) -> None:
    audio_in = tmp_path / "input.wav"
    _write_test_wav(audio_in)

    result = asr_demo.run_asr_demo(
        audio_in=audio_in,
        record_seconds=3.0,
        runs_dir=tmp_path / "runs",
        allow_archived_qwen_asr=True,
        now=datetime(2026, 2, 20, 21, 1, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is False
    assert result["run_payload"]["error_code"] == "asr_demo_failed"
    assert "Choose exactly one input mode" in result["run_payload"]["error"]


def test_asr_demo_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["asr_demo.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        asr_demo.parse_args()
    assert exc.value.code == 0


def test_asr_demo_requires_archive_opt_in(tmp_path: Path) -> None:
    audio_in = tmp_path / "input.wav"
    _write_test_wav(audio_in)

    result = asr_demo.run_asr_demo(
        audio_in=audio_in,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 20, 21, 2, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["run_payload"]["error_code"] == "archived_backend_disabled"
    assert "archived" in result["run_payload"]["error"]
