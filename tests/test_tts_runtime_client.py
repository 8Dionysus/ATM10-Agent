from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.tts_runtime_client as tts_runtime_client


def test_tts_runtime_client_health_writes_response(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _fake_request_json(*, method: str, url: str, payload: dict[str, object] | None, timeout_sec: float = 120.0):
        assert method == "GET"
        assert url == "http://127.0.0.1:8780/health"
        assert payload is None
        return {"status": "ok", "cache_items": 3}

    monkeypatch.setattr(tts_runtime_client, "_request_json", _fake_request_json)

    result = tts_runtime_client.run_tts_runtime_client(
        service_url="http://127.0.0.1:8780",
        mode="health",
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 0, 1, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    response_payload = json.loads((run_dir / "health_response.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260222_000100-tts-client"
    assert run_payload["status"] == "ok"
    assert response_payload["status"] == "ok"


def test_tts_runtime_client_tts_writes_response_and_first_chunk_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    wav_bytes = b"RIFFfakewavdata"

    def _fake_request_json(*, method: str, url: str, payload: dict[str, object] | None, timeout_sec: float = 120.0):
        assert method == "POST"
        assert url == "http://127.0.0.1:8780/tts"
        assert payload is not None
        captured["payload"] = payload
        return {
            "ok": True,
            "result": {
                "chunks": [
                    {"index": 0, "audio_wav_b64": base64.b64encode(wav_bytes).decode("ascii")},
                ]
            },
        }

    monkeypatch.setattr(tts_runtime_client, "_request_json", _fake_request_json)

    result = tts_runtime_client.run_tts_runtime_client(
        service_url="http://127.0.0.1:8780",
        mode="tts",
        runs_dir=tmp_path / "runs",
        text="craft iron",
        language="en",
        speaker="voice_a",
        chunk_chars=180,
        now=datetime(2026, 2, 22, 0, 2, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    request_payload = captured["payload"]

    assert isinstance(request_payload, dict)
    assert request_payload["text"] == "craft iron"
    assert request_payload["language"] == "en"
    assert request_payload["speaker"] == "voice_a"
    assert request_payload["chunk_chars"] == 180
    assert run_payload["status"] == "ok"
    assert Path(run_payload["paths"]["audio_out_wav"]).read_bytes() == wav_bytes


def test_tts_runtime_client_tts_stream_writes_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _fake_request_ndjson(
        *,
        method: str,
        url: str,
        payload: dict[str, object] | None,
        timeout_sec: float = 120.0,
    ):
        assert method == "POST"
        assert url == "http://127.0.0.1:8780/tts_stream"
        assert payload is not None
        assert payload["service_voice"] is True
        return [
            {"event": "started"},
            {"event": "audio_chunk", "index": 0},
            {"event": "completed"},
        ]

    monkeypatch.setattr(tts_runtime_client, "_request_ndjson", _fake_request_ndjson)

    result = tts_runtime_client.run_tts_runtime_client(
        service_url="http://127.0.0.1:8780",
        mode="tts-stream",
        runs_dir=tmp_path / "runs",
        text="service message",
        service_voice=True,
        now=datetime(2026, 2, 22, 0, 3, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    events_lines = (run_dir / "tts_stream_events.jsonl").read_text(encoding="utf-8").strip().splitlines()

    assert result["ok"] is True
    assert run_payload["status"] == "ok"
    assert run_payload["stream"]["num_events"] == 3
    assert run_payload["stream"]["num_audio_chunks"] == 1
    assert len(events_lines) == 3


def test_tts_runtime_client_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["tts_runtime_client.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        tts_runtime_client.parse_args()
    assert exc.value.code == 0

