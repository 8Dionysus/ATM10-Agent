from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.voice_runtime_client as voice_runtime_client


def _write_audio_fixture(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-audio")


def test_voice_runtime_client_health_mode_writes_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _fake_request_json(*, method: str, url: str, payload: dict[str, object] | None, timeout_sec: float = 120.0):
        assert method == "GET"
        assert url == "http://127.0.0.1:8765/health"
        assert payload is None
        return {"status": "ok"}

    monkeypatch.setattr(voice_runtime_client, "_request_json", _fake_request_json)

    result = voice_runtime_client.run_voice_runtime_client(
        service_url="http://127.0.0.1:8765",
        mode="health",
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 20, 22, 10, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    response_payload = json.loads((run_dir / "health_response.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260220_221000-voice-client"
    assert run_payload["status"] == "ok"
    assert response_payload["status"] == "ok"


def test_voice_runtime_client_asr_mode_audio_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def _fake_request_json(*, method: str, url: str, payload: dict[str, object] | None, timeout_sec: float = 120.0):
        assert method == "POST"
        assert url == "http://127.0.0.1:8765/asr"
        assert payload is not None
        captured["payload"] = payload
        return {"ok": True, "result": {"text": "hello", "language": "english"}}

    monkeypatch.setattr(voice_runtime_client, "_request_json", _fake_request_json)

    audio_in = tmp_path / "input.wav"
    _write_audio_fixture(audio_in)
    result = voice_runtime_client.run_voice_runtime_client(
        service_url="http://127.0.0.1:8765",
        mode="asr",
        runs_dir=tmp_path / "runs",
        audio_in=audio_in,
        context="quest context",
        language="en",
        now=datetime(2026, 2, 20, 22, 11, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    response_payload = json.loads((run_dir / "asr_response.json").read_text(encoding="utf-8"))
    request_payload = captured["payload"]

    assert isinstance(request_payload, dict)
    assert Path(str(request_payload["audio_path"])).exists()
    assert request_payload["context"] == "quest context"
    assert request_payload["language"] == "en"
    assert run_payload["status"] == "ok"
    assert run_payload["input"]["mode"] == "audio_file"
    assert response_payload["result"]["text"] == "hello"


def test_voice_runtime_client_tts_requires_text(tmp_path: Path) -> None:
    result = voice_runtime_client.run_voice_runtime_client(
        service_url="http://127.0.0.1:8765",
        mode="tts",
        runs_dir=tmp_path / "runs",
        text="",
        now=datetime(2026, 2, 20, 22, 12, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["run_payload"]["status"] == "error"
    assert result["run_payload"]["error_code"] == "voice_client_failed"
    assert "--text is required for tts mode." in result["run_payload"]["error"]


def test_voice_runtime_client_tts_mode_forwards_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def _fake_request_json(*, method: str, url: str, payload: dict[str, object] | None, timeout_sec: float = 120.0):
        assert method == "POST"
        assert url == "http://127.0.0.1:8765/tts"
        assert payload is not None
        captured["payload"] = payload
        return {"ok": True, "result": {"audio_out_wav": "C:/tmp/out.wav"}}

    monkeypatch.setattr(voice_runtime_client, "_request_json", _fake_request_json)

    result = voice_runtime_client.run_voice_runtime_client(
        service_url="http://127.0.0.1:8765",
        mode="tts",
        runs_dir=tmp_path / "runs",
        text="hello runtime",
        tts_runtime="qwen3",
        now=datetime(2026, 2, 20, 22, 13, 30, tzinfo=timezone.utc),
    )

    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["runtime"] == "qwen3"
    assert request_payload["out_wav_path"] == "audio_out.wav"
    assert result["ok"] is True


def test_voice_runtime_client_tts_mode_forwards_ovms_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def _fake_request_json(*, method: str, url: str, payload: dict[str, object] | None, timeout_sec: float = 120.0):
        assert method == "POST"
        assert url == "http://127.0.0.1:8765/tts"
        assert payload is not None
        captured["payload"] = payload
        return {"ok": True, "result": {"audio_out_wav": "C:/tmp/out.wav"}}

    monkeypatch.setattr(voice_runtime_client, "_request_json", _fake_request_json)

    result = voice_runtime_client.run_voice_runtime_client(
        service_url="http://127.0.0.1:8765",
        mode="tts",
        runs_dir=tmp_path / "runs",
        text="ovms override",
        tts_runtime="ovms",
        ovms_tts_url="http://127.0.0.1:9000/v1/audio/tts",
        ovms_tts_model="tts-fast-en",
        now=datetime(2026, 2, 20, 22, 13, 45, tzinfo=timezone.utc),
    )

    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["runtime"] == "ovms"
    assert request_payload["out_wav_path"] == "audio_out.wav"
    assert request_payload["ovms_tts_url"] == "http://127.0.0.1:9000/v1/audio/tts"
    assert request_payload["ovms_tts_model"] == "tts-fast-en"
    assert result["ok"] is True


def test_voice_runtime_client_tts_mode_sends_safe_output_filename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def _fake_request_json(*, method: str, url: str, payload: dict[str, object] | None, timeout_sec: float = 120.0):
        assert method == "POST"
        assert url == "http://127.0.0.1:8765/tts"
        assert payload is not None
        captured["payload"] = payload
        return {"ok": True, "result": {"audio_out_wav": "runs/service/tts_outputs/client.wav"}}

    monkeypatch.setattr(voice_runtime_client, "_request_json", _fake_request_json)

    result = voice_runtime_client.run_voice_runtime_client(
        service_url="http://127.0.0.1:8765",
        mode="tts",
        runs_dir=tmp_path / "runs",
        text="safe filename",
        out_wav=tmp_path / "nested" / "client.wav",
        now=datetime(2026, 2, 20, 22, 13, 50, tzinfo=timezone.utc),
    )

    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["out_wav_path"] == "client.wav"
    assert result["ok"] is True


def test_voice_runtime_client_tts_stream_writes_events(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _fake_request_ndjson(
        *,
        method: str,
        url: str,
        payload: dict[str, object] | None,
        timeout_sec: float = 300.0,
    ):
        assert method == "POST"
        assert url == "http://127.0.0.1:8765/tts_stream"
        assert payload is not None
        assert payload["text"] == "stream text"
        assert payload["chunk_ms"] == 150
        assert payload["runtime"] == "ovms"
        assert payload["out_wav_path"] == "audio_out.wav"
        return [
            {"event": "started"},
            {"event": "audio_chunk", "chunk_index": 0},
            {
                "event": "completed",
                "first_chunk_latency_sec": 0.12,
                "total_synthesis_sec": 1.45,
                "rtf": 0.8,
                "streaming_mode": "native",
            },
        ]

    monkeypatch.setattr(voice_runtime_client, "_request_ndjson", _fake_request_ndjson)

    result = voice_runtime_client.run_voice_runtime_client(
        service_url="http://127.0.0.1:8765",
        mode="tts-stream",
        runs_dir=tmp_path / "runs",
        text="stream text",
        chunk_ms=150,
        now=datetime(2026, 2, 20, 22, 14, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    events_lines = (run_dir / "tts_stream_events.jsonl").read_text(encoding="utf-8").strip().splitlines()

    assert result["ok"] is True
    assert run_payload["status"] == "ok"
    assert run_payload["stream"]["num_audio_chunks"] == 1
    assert run_payload["stream"]["first_chunk_latency_sec"] == 0.12
    assert run_payload["stream"]["rtf"] == 0.8
    assert len(events_lines) == 3


def test_voice_runtime_client_sets_unreachable_error_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _fake_request_json(*, method: str, url: str, payload: dict[str, object] | None, timeout_sec: float = 120.0):
        raise RuntimeError("Cannot connect to voice service at http://127.0.0.1:8765/health: refused")

    monkeypatch.setattr(voice_runtime_client, "_request_json", _fake_request_json)

    result = voice_runtime_client.run_voice_runtime_client(
        service_url="http://127.0.0.1:8765",
        mode="health",
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 20, 22, 13, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["run_payload"]["error_code"] == "voice_service_unreachable"


def test_voice_runtime_client_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["voice_runtime_client.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        voice_runtime_client.parse_args()
    assert exc.value.code == 0
