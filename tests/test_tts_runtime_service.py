from __future__ import annotations

import base64
import io
import json
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


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("true", True),
        ("false", False),
        ("1", True),
        ("0", False),
    ],
)
def test_request_from_payload_coerces_service_voice_string(raw_value: str, expected: bool) -> None:
    request = tts_runtime_service._request_from_payload({"text": "hello", "service_voice": raw_value})
    assert request.service_voice is expected


def test_request_from_payload_rejects_invalid_service_voice() -> None:
    with pytest.raises(ValueError, match="service_voice"):
        tts_runtime_service._request_from_payload({"text": "hello", "service_voice": "maybe"})


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


def test_parse_args_accepts_explicit_piper_cli_args() -> None:
    args = tts_runtime_service.parse_args(
        [
            "--tts-piper-executable",
            "C:/Tools/piper/piper.exe",
            "--tts-piper-model-path",
            "models/piper/ru.onnx",
            "--tts-piper-speaker",
            "0",
        ]
    )

    assert args.tts_piper_executable == "C:/Tools/piper/piper.exe"
    assert args.tts_piper_model_path == "models/piper/ru.onnx"
    assert args.tts_piper_speaker == "0"


def test_build_windows_sapi_engine_invokes_system_speech(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(command, capture_output, text, check, timeout):
        assert command[:4] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand"]
        decoded_script = base64.b64decode(command[4]).decode("utf-16le")
        assert "System.Speech" in decoded_script
        marker = "FromBase64String('"
        segments = decoded_script.split(marker)
        language_b64 = segments[2].split("')", 1)[0]
        output_path_b64 = segments[4].split("')", 1)[0]
        assert base64.b64decode(language_b64).decode("utf-8") == "en"
        output_path = Path(base64.b64decode(output_path_b64).decode("utf-8"))
        waveform = np.zeros(2205, dtype=np.float32)
        pcm16 = (waveform * 32767.0).astype(np.int16)
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(pcm16.tobytes())
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tts_runtime_service.subprocess, "run", _fake_run)

    engine = tts_runtime_service._build_windows_sapi_engine()
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


def test_build_silero_engine_blocks_remote_without_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    monkeypatch.delenv("SILERO_ALLOW_REMOTE_HUB", raising=False)
    monkeypatch.delenv("SILERO_REPO_REF", raising=False)

    with pytest.raises(tts_runtime_service.TTSRuntimeError, match="disabled by default"):
        tts_runtime_service._build_silero_engine()


def test_build_silero_engine_blocks_remote_without_pinned_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    monkeypatch.setenv("SILERO_ALLOW_REMOTE_HUB", "true")
    monkeypatch.delenv("SILERO_REPO_REF", raising=False)

    with pytest.raises(tts_runtime_service.TTSRuntimeError, match="requires pinned revision"):
        tts_runtime_service._build_silero_engine()


def test_build_silero_engine_uses_local_repo_without_remote_opt_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("SILERO_REPO_OR_DIR", str(tmp_path))
    monkeypatch.delenv("SILERO_ALLOW_REMOTE_HUB", raising=False)
    monkeypatch.delenv("SILERO_REPO_REF", raising=False)

    class _FakeSileroModel:
        def apply_tts(self, *, text: str, speaker: str, sample_rate: int):
            assert text == "hello"
            assert speaker == "xenia"
            assert sample_rate == 24000
            return np.array([0.0, 0.1, -0.1], dtype=np.float32)

    def _fake_hub_load(**kwargs):
        captured.update(kwargs)
        return _FakeSileroModel(), "example"

    fake_torch = types.ModuleType("torch")
    fake_torch.hub = types.SimpleNamespace(load=_fake_hub_load)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    engine = tts_runtime_service._build_silero_engine()
    wav_bytes, sample_rate = engine.synthesize(text="hello", language="ru", speaker=None)
    assert sample_rate == 24000
    assert wav_bytes.startswith(b"RIFF")
    assert captured["repo_or_dir"] == str(tmp_path)
    assert captured["source"] == "local"


def test_build_silero_engine_uses_remote_with_opt_in_and_pinned_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    monkeypatch.setenv("SILERO_ALLOW_REMOTE_HUB", "true")
    monkeypatch.setenv("SILERO_REPO_REF", "v4.1.0")

    class _FakeSileroModel:
        def apply_tts(self, *, text: str, speaker: str, sample_rate: int):
            assert text == "hello"
            assert speaker == "xenia"
            assert sample_rate == 24000
            return np.array([0.0, 0.1, -0.1], dtype=np.float32)

    def _fake_hub_load(**kwargs):
        captured.update(kwargs)
        return _FakeSileroModel(), "example"

    fake_torch = types.ModuleType("torch")
    fake_torch.hub = types.SimpleNamespace(load=_fake_hub_load)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    engine = tts_runtime_service._build_silero_engine()
    wav_bytes, sample_rate = engine.synthesize(text="hello", language="ru", speaker=None)
    assert sample_rate == 24000
    assert wav_bytes.startswith(b"RIFF")
    assert captured["repo_or_dir"] == "snakers4/silero-models:v4.1.0"
    assert captured["source"] == "github"


def test_build_default_service_degrades_silero_to_disabled_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    monkeypatch.delenv("SILERO_ALLOW_REMOTE_HUB", raising=False)
    monkeypatch.delenv("SILERO_REPO_REF", raising=False)
    monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)
    monkeypatch.setattr(
        tts_runtime_service,
        "_synthesize_windows_sapi_wav",
        lambda **_kwargs: (_ for _ in ()).throw(tts_runtime_service.TTSRuntimeError("windows unavailable")),
    )

    service = tts_runtime_service._build_default_service(
        cache_items=32,
        chunk_chars=220,
        queue_size=16,
    )

    prewarm_status = service.prewarm()
    assert service.silero_engine is not None
    assert prewarm_status["silero_ru_service"]["ok"] is False
    assert "disabled by default" in str(prewarm_status["silero_ru_service"]["error"])
    result = service.synthesize(
        tts_runtime_service.TTSRequest(
            text="служебное сообщение",
            language="ru",
            service_voice=True,
        )
    )
    assert result["chunks"][0].engine == "silence_fallback"


def test_build_default_service_uses_silence_fallback_for_standard_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    monkeypatch.delenv("SILERO_ALLOW_REMOTE_HUB", raising=False)
    monkeypatch.delenv("SILERO_REPO_REF", raising=False)
    monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)
    monkeypatch.setattr(
        tts_runtime_service,
        "_synthesize_windows_sapi_wav",
        lambda **_kwargs: (_ for _ in ()).throw(tts_runtime_service.TTSRuntimeError("windows unavailable")),
    )

    service = tts_runtime_service._build_default_service(
        cache_items=32,
        chunk_chars=220,
        queue_size=16,
    )

    prewarm_status = service.prewarm()
    result = service.synthesize(tts_runtime_service.TTSRequest(text="hello there", language="en"))

    assert prewarm_status["silence_fallback"]["ok"] is True
    assert result["chunks"][0].engine == "silence_fallback"
    assert result["router_chain"][-2:] == ["windows_sapi_fallback", "silence_fallback"]


def test_build_default_service_uses_windows_sapi_before_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    monkeypatch.delenv("SILERO_ALLOW_REMOTE_HUB", raising=False)
    monkeypatch.delenv("SILERO_REPO_REF", raising=False)
    monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)
    monkeypatch.setattr(
        tts_runtime_service,
        "_synthesize_windows_sapi_wav",
        lambda **_kwargs: (b"RIFFfakewindows", 22050),
    )

    service = tts_runtime_service._build_default_service(
        cache_items=32,
        chunk_chars=220,
        queue_size=16,
    )

    prewarm_status = service.prewarm()
    result = service.synthesize(tts_runtime_service.TTSRequest(text="hello there", language="en"))

    assert prewarm_status["windows_sapi_fallback"]["ok"] is True
    assert result["chunks"][0].engine == "windows_sapi_fallback"
    assert result["router_chain"][-2:] == ["windows_sapi_fallback", "silence_fallback"]


def test_build_default_service_prefers_piper_before_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    monkeypatch.delenv("SILERO_ALLOW_REMOTE_HUB", raising=False)
    monkeypatch.delenv("SILERO_REPO_REF", raising=False)
    monkeypatch.setattr(
        tts_runtime_service,
        "_build_xtts_engine",
        lambda: tts_runtime_service._disabled_engine("xtts_v2", "xtts unavailable"),
    )
    monkeypatch.setattr(
        tts_runtime_service,
        "_synthesize_windows_sapi_wav",
        lambda **_kwargs: (b"RIFFfakewindows", 22050),
    )

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

    service = tts_runtime_service._build_default_service(
        cache_items=32,
        chunk_chars=220,
        queue_size=16,
        piper_executable="C:/Tools/piper/piper.exe",
        piper_model_path="models/piper/ru.onnx",
        piper_speaker="0",
    )

    prewarm_status = service.prewarm()
    health = service.health()
    result = service.synthesize(tts_runtime_service.TTSRequest(text="привет", language="ru"))

    assert prewarm_status["piper"]["ok"] is True
    assert health["preferred_tts_engine"] == "piper"
    assert health["piper_available"] is True
    assert health["piper_prewarm_ok"] is True
    assert health["effective_config"]["piper"]["model_path"] == "models/piper/ru.onnx"
    assert result["chunks"][0].engine == "piper"


def test_build_default_service_reports_piper_not_configured_in_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    monkeypatch.delenv("SILERO_ALLOW_REMOTE_HUB", raising=False)
    monkeypatch.delenv("SILERO_REPO_REF", raising=False)
    monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)

    service = tts_runtime_service._build_default_service(
        cache_items=32,
        chunk_chars=220,
        queue_size=16,
    )

    service.prewarm()
    health = service.health()

    assert health["preferred_tts_engine"] == "windows_sapi_fallback"
    assert health["piper_available"] is False
    assert health["piper_prewarm_ok"] is False
    assert health["tts_degraded_reason"] == "piper_not_configured"
    assert health["engines"]["piper"]["configured"] is False
    assert health["engines"]["piper"]["ok"] is False


def test_tts_runtime_service_main_starts_with_disabled_silero_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = lambda app, host, port, log_level: None
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    monkeypatch.delenv("SILERO_ALLOW_REMOTE_HUB", raising=False)
    monkeypatch.delenv("SILERO_REPO_REF", raising=False)
    monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)

    exit_code = tts_runtime_service.main(
        [
            "--host",
            "127.0.0.1",
            "--port",
            "8780",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--tts-piper-model-path",
            "models/piper/ru.onnx",
            "--tts-piper-speaker",
            "0",
            "--no-prewarm",
        ]
    )

    assert exit_code == 0
    run_dirs = sorted((tmp_path / "runs").glob("*-tts-service*"))
    assert run_dirs
    run_payload = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "stopped"
    assert run_payload["service"]["base_url"] == "http://127.0.0.1:8780"
    assert run_payload["service"]["tts"]["preferred_tts_engine"] == "piper"
    assert run_payload["service"]["tts"]["piper"]["model_path"] == "models/piper/ru.onnx"
    assert run_payload["service"]["tts"]["piper"]["speaker"] == "0"


def test_tts_stream_endpoint_uses_iter_synthesize_without_submit() -> None:
    from fastapi.testclient import TestClient

    class _FakeService:
        def start(self) -> None:
            return

        def stop(self) -> None:
            return

        def prewarm(self) -> dict[str, dict[str, object]]:
            return {}

        def health(self) -> dict[str, object]:
            return {
                "status": "ok",
                "worker_alive": True,
                "queue_size": 0,
                "cache_items": 0,
                "prewarm": {},
            }

        def submit(self, _request):
            raise AssertionError("submit must not be used for /tts_stream")

        def iter_synthesize(self, _request):
            yield TTSChunk(
                index=0,
                text="hello",
                engine="xtts_v2",
                sample_rate=22050,
                audio_wav_bytes=b"RIFFfake",
                cached=False,
            )

    app = tts_runtime_service.create_app(_FakeService(), prewarm=False)
    with TestClient(app) as client:
        response = client.post("/tts_stream", json={"text": "hello"})

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [event["event"] for event in events] == ["started", "audio_chunk", "completed"]
    assert events[1]["text"] == "hello"
    assert events[1]["audio_wav_b64"] == base64.b64encode(b"RIFFfake").decode("ascii")


def test_tts_service_openapi_is_disabled_by_default_and_opt_in_enabled() -> None:
    from fastapi.testclient import TestClient

    class _FakeService:
        def start(self) -> None:
            return

        def stop(self) -> None:
            return

        def prewarm(self) -> dict[str, dict[str, object]]:
            return {}

        def health(self) -> dict[str, object]:
            return {
                "status": "ok",
                "worker_alive": True,
                "queue_size": 0,
                "cache_items": 0,
                "prewarm": {},
            }

        def submit(self, _request):
            raise AssertionError("submit must not be used in openapi exposure test")

    app = tts_runtime_service.create_app(_FakeService(), prewarm=False)
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/redoc").status_code == 404

    exposed_app = tts_runtime_service.create_app(
        _FakeService(),
        prewarm=False,
        expose_openapi=True,
    )
    with TestClient(exposed_app) as client:
        docs_response = client.get("/docs")
        openapi_response = client.get("/openapi.json")
        health_response = client.get("/health")

    assert docs_response.status_code == 200
    assert "Swagger UI" in docs_response.text
    assert openapi_response.status_code == 200
    assert openapi_response.json()["info"]["title"] == "ATM10 TTS Runtime"
    assert health_response.status_code == 200
    assert health_response.json()["api_docs_exposed"] is True


def test_tts_endpoint_keeps_non_streaming_submit_path() -> None:
    from fastapi.testclient import TestClient

    class _FakeFuture:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def result(self, timeout: float) -> dict[str, object]:
            assert timeout == 120.0
            return self._payload

    class _FakeService:
        def __init__(self) -> None:
            self.submit_called = False

        def start(self) -> None:
            return

        def stop(self) -> None:
            return

        def prewarm(self) -> dict[str, dict[str, object]]:
            return {}

        def health(self) -> dict[str, object]:
            return {
                "status": "ok",
                "worker_alive": True,
                "queue_size": 0,
                "cache_items": 0,
                "prewarm": {},
            }

        def submit(self, _request):
            self.submit_called = True
            payload = {
                "chunk_count": 1,
                "cache_hits": 0,
                "router_chain": ["xtts_v2"],
                "chunks": [
                    TTSChunk(
                        index=0,
                        text="hello",
                        engine="xtts_v2",
                        sample_rate=22050,
                        audio_wav_bytes=b"RIFFfake",
                        cached=False,
                    )
                ],
            }
            return _FakeFuture(payload)

        def iter_synthesize(self, _request):
            raise AssertionError("iter_synthesize must not be used for /tts")

    service = _FakeService()
    app = tts_runtime_service.create_app(service, prewarm=False)
    with TestClient(app) as client:
        response = client.post("/tts", json={"text": "hello"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert service.submit_called is True


def test_tts_endpoint_returns_silence_fallback_when_default_engines_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    monkeypatch.delenv("SILERO_ALLOW_REMOTE_HUB", raising=False)
    monkeypatch.delenv("SILERO_REPO_REF", raising=False)
    monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)
    monkeypatch.setattr(
        tts_runtime_service,
        "_synthesize_windows_sapi_wav",
        lambda **_kwargs: (_ for _ in ()).throw(tts_runtime_service.TTSRuntimeError("windows unavailable")),
    )

    service = tts_runtime_service._build_default_service(
        cache_items=32,
        chunk_chars=220,
        queue_size=16,
    )
    app = tts_runtime_service.create_app(service, prewarm=False)
    with TestClient(app) as client:
        response = client.post("/tts", json={"text": "hello fallback", "language": "en"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["chunks"][0]["engine"] == "silence_fallback"


def test_tts_endpoint_returns_windows_sapi_audio_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    monkeypatch.delenv("SILERO_ALLOW_REMOTE_HUB", raising=False)
    monkeypatch.delenv("SILERO_REPO_REF", raising=False)
    monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)
    monkeypatch.setattr(
        tts_runtime_service,
        "_synthesize_windows_sapi_wav",
        lambda **_kwargs: (b"RIFFfakewindows", 22050),
    )

    service = tts_runtime_service._build_default_service(
        cache_items=32,
        chunk_chars=220,
        queue_size=16,
    )
    app = tts_runtime_service.create_app(service, prewarm=False)
    with TestClient(app) as client:
        response = client.post("/tts", json={"text": "hello fallback", "language": "en"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["chunks"][0]["engine"] == "windows_sapi_fallback"


def test_tts_service_maps_payload_too_large_to_413() -> None:
    from fastapi.testclient import TestClient

    class _FakeService:
        def start(self) -> None:
            return

        def stop(self) -> None:
            return

        def prewarm(self) -> dict[str, dict[str, object]]:
            return {}

        def health(self) -> dict[str, object]:
            return {
                "status": "ok",
                "worker_alive": True,
                "queue_size": 0,
                "cache_items": 0,
                "prewarm": {},
            }

        def submit(self, _request):
            raise AssertionError("submit must not be called for oversized payload")

    app = tts_runtime_service.create_app(
        _FakeService(),
        prewarm=False,
        http_policy=tts_runtime_service.TTSHTTPPolicy(max_request_body_bytes=64),
    )
    with TestClient(app) as client:
        response = client.post("/tts", json={"text": "x" * 1024})

    assert response.status_code == 413
    payload = response.json()
    assert payload["error_code"] == "payload_too_large"


def test_tts_service_maps_payload_limit_exceeded_to_413() -> None:
    from fastapi.testclient import TestClient

    class _FakeService:
        def start(self) -> None:
            return

        def stop(self) -> None:
            return

        def prewarm(self) -> dict[str, dict[str, object]]:
            return {}

        def health(self) -> dict[str, object]:
            return {
                "status": "ok",
                "worker_alive": True,
                "queue_size": 0,
                "cache_items": 0,
                "prewarm": {},
            }

        def submit(self, _request):
            raise AssertionError("submit must not be called for invalid payload")

    app = tts_runtime_service.create_app(
        _FakeService(),
        prewarm=False,
        http_policy=tts_runtime_service.TTSHTTPPolicy(max_string_length=4),
    )
    with TestClient(app) as client:
        response = client.post("/tts", json={"text": "12345"})

    assert response.status_code == 413
    payload = response.json()
    assert payload["error_code"] == "payload_limit_exceeded"


def test_tts_service_requires_auth_token_when_configured() -> None:
    from fastapi.testclient import TestClient

    class _FakeService:
        def start(self) -> None:
            return

        def stop(self) -> None:
            return

        def prewarm(self) -> dict[str, dict[str, object]]:
            return {}

        def health(self) -> dict[str, object]:
            return {
                "status": "ok",
                "worker_alive": True,
                "queue_size": 0,
                "cache_items": 0,
                "prewarm": {},
            }

        def submit(self, _request):
            raise AssertionError("submit must not be called in auth test")

    app = tts_runtime_service.create_app(
        _FakeService(),
        prewarm=False,
        service_token="test-token",
    )
    with TestClient(app) as client:
        unauthorized_health = client.get("/health")
        unauthorized_tts = client.post("/tts", json={"text": "hello"})
        authorized_health = client.get("/health", headers={"X-ATM10-Token": "test-token"})

    assert unauthorized_health.status_code == 401
    assert unauthorized_health.json()["error_code"] == "unauthorized"
    assert unauthorized_tts.status_code == 401
    assert unauthorized_tts.json()["error_code"] == "unauthorized"
    assert authorized_health.status_code == 200


def test_tts_service_sanitizes_internal_error_and_logs_locally(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    class _BoomFuture:
        def result(self, timeout: float):
            assert timeout == 120.0
            raise RuntimeError("token=SUPER_SECRET")

    class _FakeService:
        def start(self) -> None:
            return

        def stop(self) -> None:
            return

        def prewarm(self) -> dict[str, dict[str, object]]:
            return {}

        def health(self) -> dict[str, object]:
            return {
                "status": "ok",
                "worker_alive": True,
                "queue_size": 0,
                "cache_items": 0,
                "prewarm": {},
            }

        def submit(self, _request):
            return _BoomFuture()

    app = tts_runtime_service.create_app(
        _FakeService(),
        prewarm=False,
        run_dir=tmp_path,
    )
    with TestClient(app) as client:
        response = client.post("/tts", json={"text": "hello"})

    payload = response.json()
    assert response.status_code == 500
    assert payload == {
        "ok": False,
        "error": "internal service error",
        "error_code": "internal_error",
    }
    assert "SUPER_SECRET" not in json.dumps(payload)

    log_path = tmp_path / "service_errors.jsonl"
    assert log_path.exists()
    log_payload = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert log_payload["error_code"] == "internal_error"
    assert "SUPER_SECRET" not in json.dumps(log_payload)
    assert log_payload["redaction"]["applied"] is True


def test_tts_runtime_service_bind_policy_requires_token_for_non_loopback() -> None:
    assert tts_runtime_service._validate_bind_security(
        host="127.0.0.1",
        service_token=None,
        allow_insecure_no_token=False,
    ) is None
    assert tts_runtime_service._validate_bind_security(
        host="0.0.0.0",
        service_token="test-token",
        allow_insecure_no_token=False,
    ) == "test-token"
    assert tts_runtime_service._validate_bind_security(
        host="0.0.0.0",
        service_token=None,
        allow_insecure_no_token=True,
    ) is None
    with pytest.raises(ValueError, match="allow-insecure-no-token"):
        tts_runtime_service._validate_bind_security(
            host="0.0.0.0",
            service_token=None,
            allow_insecure_no_token=False,
        )
