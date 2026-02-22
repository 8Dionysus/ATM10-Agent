from __future__ import annotations

import json
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import scripts.asr_demo_whisper_genai as whisper_demo


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


def test_whisper_genai_asr_demo_audio_file_mode_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: dict[str, object] = {}

    class _FakeWhisperPipeline:
        def __init__(self, model_dir: str, device: str, **kwargs):
            calls["model_dir"] = model_dir
            calls["device"] = device
            calls["pipeline_kwargs"] = kwargs

        def generate(self, raw_speech: list[float], **kwargs):
            assert isinstance(raw_speech, list)
            assert raw_speech
            calls["generate_kwargs"] = kwargs
            return SimpleNamespace(
                texts=["hello from whisper genai"],
                language="<|en|>",
                chunks=[SimpleNamespace(start_ts=0.0, end_ts=0.5, text="hello")],
                words=[SimpleNamespace(start_ts=0.0, end_ts=0.2, word="hello")],
            )

    fake_ov_genai = SimpleNamespace(WhisperPipeline=_FakeWhisperPipeline)
    monkeypatch.setattr(whisper_demo, "_load_openvino_genai", lambda: fake_ov_genai)

    audio_in = tmp_path / "input.wav"
    _write_test_wav(audio_in)
    model_dir = tmp_path / "whisper-model"
    model_dir.mkdir(parents=True, exist_ok=True)

    result = whisper_demo.run_asr_demo_whisper_genai(
        model_dir=model_dir,
        audio_in=audio_in,
        device="NPU",
        language="en",
        return_timestamps=True,
        word_timestamps=True,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 15, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    result_payload = json.loads((run_dir / "transcription.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260222_150000-asr-whisper-genai"
    assert run_payload["status"] == "ok"
    assert result_payload["text"] == "hello from whisper genai"
    assert result_payload["chunks"][0]["text"] == "hello"
    assert result_payload["words"][0]["word"] == "hello"
    assert calls["model_dir"] == str(model_dir)
    assert calls["device"] == "NPU"
    assert calls["pipeline_kwargs"] == {"STATIC_PIPELINE": True, "word_timestamps": True}
    assert calls["generate_kwargs"] == {
        "max_new_tokens": 128,
        "task": "transcribe",
        "language": "<|en|>",
        "return_timestamps": True,
        "word_timestamps": True,
    }


def test_whisper_genai_asr_demo_missing_runtime_reports_dependency_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _raise_missing_runtime():
        raise whisper_demo.VoiceRuntimeUnavailableError("OpenVINO GenAI runtime is not installed.")

    monkeypatch.setattr(whisper_demo, "_load_openvino_genai", _raise_missing_runtime)

    audio_in = tmp_path / "input.wav"
    _write_test_wav(audio_in)
    model_dir = tmp_path / "whisper-model"
    model_dir.mkdir(parents=True, exist_ok=True)

    result = whisper_demo.run_asr_demo_whisper_genai(
        model_dir=model_dir,
        audio_in=audio_in,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 15, 1, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["run_payload"]["error_code"] == "voice_runtime_missing_dependency"


def test_whisper_genai_asr_demo_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["asr_demo_whisper_genai.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        whisper_demo.parse_args()
    assert exc.value.code == 0
