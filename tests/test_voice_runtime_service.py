from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

import scripts.voice_runtime_service as voice_runtime_service


def test_process_asr_request_returns_transcription(tmp_path: Path) -> None:
    class _FakeASRClient:
        def transcribe_path(self, *, audio_path: Path, context: str, language: str | None) -> dict[str, str]:
            assert audio_path.exists()
            assert context == "quest context"
            assert language == "en"
            return {"text": "recognized", "language": "english"}

    class _FakeState:
        def ensure_asr(self) -> _FakeASRClient:
            return _FakeASRClient()

    audio_path = tmp_path / "input.wav"
    audio_path.write_bytes(b"fake")

    result = voice_runtime_service.process_asr_request(
        _FakeState(),
        {"audio_path": str(audio_path), "context": "quest context", "language": "en"},
    )

    assert result["text"] == "recognized"
    assert result["language"] == "english"
    assert result["audio_path"] == str(audio_path)


def test_process_asr_request_validates_audio_path() -> None:
    class _FakeState:
        def ensure_asr(self) -> object:
            raise AssertionError("ensure_asr must not be called for invalid payload")

    with pytest.raises(ValueError):
        voice_runtime_service.process_asr_request(_FakeState(), {"audio_path": ""})

    with pytest.raises(FileNotFoundError):
        voice_runtime_service.process_asr_request(_FakeState(), {"audio_path": "missing.wav"})


def test_process_tts_request_writes_audio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _FakeTTSClient:
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
            assert text == "hello"
            assert speaker == "speaker_a"
            assert language == "Auto"
            assert instruct is None
            return np.linspace(-0.1, 0.1, 32, dtype=np.float32), 22050

    class _FakeState:
        def __init__(self, run_dir: Path) -> None:
            self.run_dir = run_dir

        def ensure_tts(self) -> _FakeTTSClient:
            return _FakeTTSClient()

    def _fake_write_wav_pcm16(*, path: Path, waveform: np.ndarray, sample_rate: int) -> None:
        captured["path"] = path
        captured["samples"] = int(waveform.shape[0])
        captured["sample_rate"] = sample_rate
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"wav")

    monkeypatch.setattr(voice_runtime_service, "write_wav_pcm16", _fake_write_wav_pcm16)

    result = voice_runtime_service.process_tts_request(_FakeState(tmp_path), {"text": "hello"})
    output_path = Path(result["audio_out_wav"])

    assert output_path.exists()
    assert output_path.parent.name == "tts_outputs"
    assert result["speaker_selected"] == "speaker_a"
    assert result["sample_rate"] == 22050
    assert result["num_samples"] == 32
    assert captured["path"] == output_path


def test_process_tts_stream_request_emits_chunk_events(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    class _FakeTTSClient:
        def resolve_speaker(self, requested_speaker: str | None) -> str:
            assert requested_speaker is None
            return "speaker_stream"

        def stream_synthesize_custom_voice(
            self,
            *,
            text: str,
            speaker: str,
            language: str,
            instruct: str | None,
            chunk_duration_ms: int,
        ):
            assert text == "stream hello"
            assert speaker == "speaker_stream"
            assert language == "Auto"
            assert instruct is None
            assert chunk_duration_ms == 120
            yield np.array([0.1, 0.0, -0.1], dtype=np.float32), 16000, "native"
            yield np.array([0.2, 0.1], dtype=np.float32), 16000, "native"

    class _FakeState:
        def __init__(self, run_dir: Path) -> None:
            self.run_dir = run_dir

        def ensure_tts(self) -> _FakeTTSClient:
            return _FakeTTSClient()

    def _fake_write_wav_pcm16(*, path: Path, waveform: np.ndarray, sample_rate: int) -> None:
        captured["path"] = path
        captured["sample_rate"] = sample_rate
        captured["num_samples"] = int(waveform.shape[0])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"wav")

    monkeypatch.setattr(voice_runtime_service, "write_wav_pcm16", _fake_write_wav_pcm16)

    events = voice_runtime_service.process_tts_stream_request(
        _FakeState(tmp_path),
        {"text": "stream hello", "chunk_ms": 120},
    )

    event_names = [event.get("event") for event in events]
    assert event_names == ["started", "audio_chunk", "audio_chunk", "completed"]
    completed = events[-1]
    assert completed["streaming_mode"] == "native"
    assert completed["num_samples"] == 5
    assert completed["first_chunk_latency_sec"] is not None
    output_path = Path(str(completed["audio_out_wav"]))
    assert output_path.exists()
    assert captured["path"] == output_path
    assert captured["sample_rate"] == 16000
    assert captured["num_samples"] == 5


def test_run_voice_runtime_service_writes_stopped_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _FakeServer:
        def __init__(self, bind: tuple[str, int], handler: type[object]) -> None:
            self.bind = bind
            self.handler = handler
            self.closed = False

        def serve_forever(self) -> None:
            return

        def server_close(self) -> None:
            self.closed = True

    monkeypatch.setattr(voice_runtime_service, "ThreadingHTTPServer", _FakeServer)

    now = datetime(2026, 2, 20, 22, 0, 0, tzinfo=timezone.utc)
    result = voice_runtime_service.run_voice_runtime_service(
        host="127.0.0.1",
        port=8765,
        runs_dir=tmp_path / "runs",
        asr_model_id="asr-model",
        tts_model_id="tts-model",
        device_map="auto",
        dtype="auto",
        asr_max_new_tokens=512,
        preload_asr=False,
        preload_tts=False,
        now=now,
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260220_220000-voice-service"
    assert run_payload["status"] == "stopped"
    assert run_payload["preload"]["asr"]["requested"] is False
    assert run_payload["preload"]["tts"]["requested"] is False


def test_voice_runtime_service_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["voice_runtime_service.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        voice_runtime_service.parse_args()
    assert exc.value.code == 0
