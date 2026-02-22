from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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


def test_voice_runtime_state_ensure_asr_uses_whisper_genai_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeWhisperClient:
        def transcribe_path(self, *, audio_path: Path, context: str, language: str | None) -> dict[str, str]:
            return {"text": "fake whisper", "language": "en"}

    def _fake_from_pretrained(
        *,
        model_dir: str | Path,
        device: str,
        task: str,
        max_new_tokens: int,
        static_language: str | None,
    ) -> _FakeWhisperClient:
        captured["model_dir"] = str(model_dir)
        captured["device"] = device
        captured["task"] = task
        captured["max_new_tokens"] = max_new_tokens
        captured["static_language"] = static_language
        return _FakeWhisperClient()

    monkeypatch.setattr(
        voice_runtime_service,
        "WhisperGenAIASRClient",
        SimpleNamespace(from_pretrained=_fake_from_pretrained),
    )

    state = voice_runtime_service.VoiceRuntimeState(
        run_dir=tmp_path,
        asr_model_id="models/whisper-large-v3-turbo-ov",
        asr_backend="whisper_genai",
        asr_device="NPU",
        asr_task="transcribe",
        asr_static_language="en",
        tts_model_id="tts-model",
        device_map="auto",
        dtype="auto",
        asr_max_new_tokens=256,
    )

    asr_client = state.ensure_asr()
    assert isinstance(asr_client, _FakeWhisperClient)
    assert captured == {
        "model_dir": "models/whisper-large-v3-turbo-ov",
        "device": "NPU",
        "task": "transcribe",
        "max_new_tokens": 256,
        "static_language": "en",
    }
    health = state.health_payload()
    assert health["models"]["asr"]["backend"] == "whisper_genai"
    assert health["models"]["asr"]["device"] == "NPU"


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


def test_process_tts_request_fast_fallback_runtime_writes_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _FakeState:
        def __init__(self, run_dir: Path) -> None:
            self.run_dir = run_dir

        def ensure_tts(self) -> object:
            raise AssertionError("ensure_tts must not be called for ovms runtime")

    def _fake_ovms_tts(
        *,
        text: str,
        output_path: Path,
        endpoint_url: str | None = None,
        model_id: str | None = None,
        speaker: str | None = None,
        language: str = "Auto",
        instruct: str | None = None,
        timeout_sec: float = 20.0,
    ) -> dict[str, object]:
        assert text == "fast hello"
        assert endpoint_url == "http://127.0.0.1:9000/v1/audio/tts"
        assert model_id == "tts-fast-en"
        assert speaker == "voice_a"
        assert language == "Auto"
        voice_runtime_service.write_wav_pcm16(
            path=output_path,
            waveform=np.array([0.1, 0.0, -0.1, 0.2], dtype=np.float32),
            sample_rate=16000,
        )
        return {"runtime": "ovms", "audio_out_wav": str(output_path)}

    monkeypatch.setattr(voice_runtime_service, "synthesize_ovms_tts_to_wav", _fake_ovms_tts)

    result = voice_runtime_service.process_tts_request(
        _FakeState(tmp_path),
        {
            "text": "fast hello",
            "speaker": "voice_a",
            "runtime": "ovms",
            "ovms_tts_url": "http://127.0.0.1:9000/v1/audio/tts",
            "ovms_tts_model": "tts-fast-en",
        },
    )

    assert result["tts_runtime"] == "ovms"
    assert result["requested_tts_runtime"] == "ovms"
    assert result["speaker_selected"] == "voice_a"
    assert result["num_samples"] == 4
    assert Path(result["audio_out_wav"]).exists()


def test_process_tts_request_auto_falls_back_when_qwen_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _FakeState:
        def __init__(self, run_dir: Path) -> None:
            self.run_dir = run_dir

        def ensure_tts(self) -> object:
            raise voice_runtime_service.VoiceRuntimeUnavailableError("qwen-tts missing")

    def _fake_ovms_tts(
        *,
        text: str,
        output_path: Path,
        endpoint_url: str | None = None,
        model_id: str | None = None,
        speaker: str | None = None,
        language: str = "Auto",
        instruct: str | None = None,
        timeout_sec: float = 20.0,
    ) -> dict[str, object]:
        assert endpoint_url == "http://127.0.0.1:9000/v1/audio/tts"
        assert model_id == "tts-fast-en"
        voice_runtime_service.write_wav_pcm16(
            path=output_path,
            waveform=np.array([0.3, 0.2, 0.1], dtype=np.float32),
            sample_rate=22050,
        )
        return {"runtime": "ovms", "audio_out_wav": str(output_path)}

    monkeypatch.setattr(voice_runtime_service, "synthesize_ovms_tts_to_wav", _fake_ovms_tts)

    result = voice_runtime_service.process_tts_request(
        _FakeState(tmp_path),
        {
            "text": "auto hello",
            "runtime": "auto",
            "ovms_tts_url": "http://127.0.0.1:9000/v1/audio/tts",
            "ovms_tts_model": "tts-fast-en",
        },
    )

    assert result["requested_tts_runtime"] == "auto"
    assert result["tts_runtime"] == "ovms"
    assert result["fallback_used"] is True
    assert "qwen-tts missing" in str(result["fallback_reason"])
    assert result["num_samples"] == 3
    assert Path(result["audio_out_wav"]).exists()


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


def test_run_voice_runtime_service_runs_asr_warmup_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _FakeServer:
        def __init__(self, bind: tuple[str, int], handler: type[object]) -> None:
            self.bind = bind
            self.handler = handler

        def serve_forever(self) -> None:
            return

        def server_close(self) -> None:
            return

    class _FakeASRClient:
        def transcribe_path(self, *, audio_path: Path, context: str, language: str | None) -> dict[str, str]:
            assert audio_path.exists()
            assert context == ""
            assert language == "en"
            return {"text": "warmup ok", "language": "en"}

    class _FakeState:
        def __init__(
            self,
            *,
            run_dir: Path,
            asr_model_id: str,
            asr_backend: str,
            asr_device: str,
            asr_task: str,
            asr_static_language: str | None,
            tts_model_id: str,
            device_map: str,
            dtype: str,
            asr_max_new_tokens: int,
        ) -> None:
            self.run_dir = run_dir

        def ensure_asr(self) -> _FakeASRClient:
            return _FakeASRClient()

        def ensure_tts(self) -> object:
            raise AssertionError("ensure_tts must not be called in this test")

        def health_payload(self) -> dict[str, object]:
            return {"status": "ok"}

    monkeypatch.setattr(voice_runtime_service, "ThreadingHTTPServer", _FakeServer)
    monkeypatch.setattr(voice_runtime_service, "VoiceRuntimeState", _FakeState)

    now = datetime(2026, 2, 22, 16, 30, 0, tzinfo=timezone.utc)
    result = voice_runtime_service.run_voice_runtime_service(
        host="127.0.0.1",
        port=8765,
        runs_dir=tmp_path / "runs",
        asr_model_id="models/whisper-large-v3-turbo-ov",
        asr_backend="whisper_genai",
        asr_device="NPU",
        asr_task="transcribe",
        asr_static_language=None,
        tts_model_id="tts-model",
        device_map="auto",
        dtype="auto",
        asr_max_new_tokens=128,
        preload_asr=False,
        preload_tts=False,
        asr_warmup_request=True,
        asr_warmup_audio=None,
        asr_warmup_language="en",
        now=now,
    )

    run_payload = json.loads((result["run_dir"] / "run.json").read_text(encoding="utf-8"))
    warmup = run_payload["preload"]["asr"]["warmup"]
    assert warmup["requested"] is True
    assert warmup["ok"] is True
    assert isinstance(warmup["latency_sec"], float)
    assert warmup["text_preview"] == "warmup ok"
    assert Path(warmup["audio_path"]).exists()


def test_voice_runtime_service_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["voice_runtime_service.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        voice_runtime_service.parse_args()
    assert exc.value.code == 0


def test_run_voice_runtime_service_blocks_archived_qwen_backend_by_default(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as exc:
        voice_runtime_service.run_voice_runtime_service(
            host="127.0.0.1",
            port=8765,
            runs_dir=tmp_path / "runs",
            asr_model_id="Qwen/Qwen3-ASR-0.6B",
            asr_backend="qwen_asr",
            tts_model_id="tts-model",
            device_map="auto",
            dtype="auto",
            asr_max_new_tokens=128,
            preload_asr=False,
            preload_tts=False,
            now=datetime(2026, 2, 22, 17, 0, 0, tzinfo=timezone.utc),
        )
    assert "archived" in str(exc.value)


def test_run_voice_runtime_service_allows_archived_qwen_backend_with_opt_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _FakeServer:
        def __init__(self, bind: tuple[str, int], handler: type[object]) -> None:
            self.bind = bind
            self.handler = handler

        def serve_forever(self) -> None:
            return

        def server_close(self) -> None:
            return

    monkeypatch.setattr(voice_runtime_service, "ThreadingHTTPServer", _FakeServer)

    result = voice_runtime_service.run_voice_runtime_service(
        host="127.0.0.1",
        port=8765,
        runs_dir=tmp_path / "runs",
        asr_model_id="Qwen/Qwen3-ASR-0.6B",
        asr_backend="qwen_asr",
        allow_archived_asr_backend=True,
        tts_model_id="tts-model",
        device_map="auto",
        dtype="auto",
        asr_max_new_tokens=128,
        preload_asr=False,
        preload_tts=False,
        now=datetime(2026, 2, 22, 17, 1, 0, tzinfo=timezone.utc),
    )

    run_payload = json.loads((result["run_dir"] / "run.json").read_text(encoding="utf-8"))
    assert run_payload["models"]["asr_backend"] == "qwen_asr"
    assert run_payload["models"]["asr_backend_archived"] is True
