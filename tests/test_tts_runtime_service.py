from __future__ import annotations

import base64
import io
import sys
import types
import wave
from pathlib import Path

import numpy as np
import pytest
import scripts.tts_runtime_service as tts_runtime_service
from src.agent_core.tts_runtime import TTSChunk


def test_request_from_payload_validates_text() -> None:
    request = tts_runtime_service._request_from_payload(
        {
            "text": "hello",
            "language": "en",
            "speaker": "voice_a",
            "service_voice": True,
            "chunk_chars": 180,
        }
    )
    assert request.text == "hello"
    assert request.language == "en"
    assert request.speaker == "voice_a"
    assert request.service_voice is True
    assert request.chunk_chars == 180


def test_serialize_result_encodes_audio_wav_b64() -> None:
    raw_audio = b"RIFFfakewav"
    result = {
        "chunk_count": 1,
        "cache_hits": 0,
        "router_chain": ["xtts_v2", "piper"],
        "chunks": [
            TTSChunk(
                index=0,
                text="hello",
                engine="xtts_v2",
                sample_rate=22050,
                audio_wav_bytes=raw_audio,
                cached=False,
            )
        ],
    }
    serialized = tts_runtime_service._serialize_result(result)
    chunk = serialized["chunks"][0]

    assert serialized["chunk_count"] == 1
    assert chunk["engine"] == "xtts_v2"
    assert base64.b64decode(chunk["audio_wav_b64"]) == raw_audio


def test_build_piper_engine_without_model_path_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)
    engine = tts_runtime_service._build_piper_engine()
    with pytest.raises(Exception):
        engine.synthesize(text="hello", language="en", speaker=None)


def test_build_piper_engine_invokes_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PIPER_MODEL_PATH", "models/piper/en.onnx")

    def _fake_run(command, input, capture_output, text, check, timeout):
        output_file = Path(command[command.index("--output_file") + 1])
        waveform = np.zeros(1600, dtype=np.float32)
        pcm16 = (waveform * 32767.0).astype(np.int16)
        with wave.open(str(output_file), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(pcm16.tobytes())
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tts_runtime_service.subprocess, "run", _fake_run)
    engine = tts_runtime_service._build_piper_engine()
    wav_bytes, sample_rate = engine.synthesize(text="hello", language="en", speaker=None)
    assert sample_rate == 22050
    assert wav_bytes.startswith(b"RIFF")


def test_build_xtts_engine_uses_lazy_import(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeSynthesizer:
        output_sample_rate = 24000

    class _FakeTTS:
        def __init__(self, model_name: str, progress_bar: bool, gpu: bool) -> None:
            assert model_name
            self.synthesizer = _FakeSynthesizer()

        def tts(self, **kwargs):
            assert kwargs["text"] == "hello"
            return np.array([0.0, 0.1, -0.1], dtype=np.float32)

    fake_tts_api = types.ModuleType("TTS.api")
    fake_tts_api.TTS = _FakeTTS
    fake_tts_root = types.ModuleType("TTS")
    fake_tts_root.api = fake_tts_api
    monkeypatch.setitem(sys.modules, "TTS", fake_tts_root)
    monkeypatch.setitem(sys.modules, "TTS.api", fake_tts_api)

    engine = tts_runtime_service._build_xtts_engine()
    wav_bytes, sample_rate = engine.synthesize(text="hello", language="en", speaker=None)
    assert sample_rate == 24000
    assert wav_bytes.startswith(b"RIFF")
