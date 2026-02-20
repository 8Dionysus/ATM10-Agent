from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

import scripts.tts_demo as tts_demo


def test_tts_demo_writes_audio_and_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _FakeTTSClient:
        @classmethod
        def from_pretrained(cls, *, model_id: str, device_map: str, dtype: str):
            assert model_id == "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
            assert device_map == "auto"
            assert dtype == "auto"
            return cls()

        def resolve_speaker(self, requested_speaker: str | None) -> str:
            assert requested_speaker is None
            return "speaker_a"

        def synthesize_custom_voice(
            self,
            *,
            text: str,
            speaker: str,
            language: str,
            instruct: str | None,
        ) -> tuple[np.ndarray, int]:
            assert text == "test phrase"
            assert speaker == "speaker_a"
            assert language == "Auto"
            assert instruct is None
            waveform = np.linspace(-0.2, 0.2, 1600, dtype=np.float32)
            return waveform, 16000

    monkeypatch.setattr(tts_demo, "QwenTTSClient", _FakeTTSClient)

    result = tts_demo.run_tts_demo(
        text="test phrase",
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 20, 21, 2, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    result_payload = json.loads((run_dir / "tts_result.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260220_210200-tts-demo"
    assert run_payload["status"] == "ok"
    assert result_payload["speaker_selected"] == "speaker_a"
    assert Path(result_payload["audio_out_wav"]).exists()


def test_tts_demo_playback_flag_calls_play_audio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    class _FakeTTSClient:
        @classmethod
        def from_pretrained(cls, *, model_id: str, device_map: str, dtype: str):
            return cls()

        def resolve_speaker(self, requested_speaker: str | None) -> str:
            return "speaker_b"

        def synthesize_custom_voice(
            self,
            *,
            text: str,
            speaker: str,
            language: str,
            instruct: str | None,
        ) -> tuple[np.ndarray, int]:
            return np.zeros(800, dtype=np.float32), 16000

    def _fake_play_audio(*, waveform: np.ndarray, sample_rate: int) -> None:
        called["samples"] = int(waveform.shape[0])
        called["sample_rate"] = sample_rate

    monkeypatch.setattr(tts_demo, "QwenTTSClient", _FakeTTSClient)
    monkeypatch.setattr(tts_demo, "play_audio", _fake_play_audio)

    result = tts_demo.run_tts_demo(
        text="playback test",
        play=True,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 20, 21, 3, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    assert called["samples"] == 800
    assert called["sample_rate"] == 16000


def test_tts_demo_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["tts_demo.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        tts_demo.parse_args()
    assert exc.value.code == 0
