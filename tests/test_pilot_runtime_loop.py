from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

import scripts.pilot_runtime_loop as pilot_runtime
import scripts.pilot_turn_smoke as pilot_turn_smoke
from src.agent_core.grounded_reply_openvino import DeterministicGroundedReplyStub
from src.agent_core.io_voice import write_wav_pcm16
from src.agent_core.vlm_stub import DeterministicStubVLM


def _write_audio_fixture(path: Path, *, sample_rate: int = 16000) -> dict[str, Any]:
    timeline = np.linspace(0.0, 0.4, int(sample_rate * 0.4), endpoint=False)
    waveform = (0.1 * np.sin(2.0 * np.pi * 220.0 * timeline)).astype(np.float32)
    write_wav_pcm16(path=path, waveform=waveform, sample_rate=sample_rate)
    return {
        "mode": "fixture_audio",
        "sample_rate": sample_rate,
        "duration_sec": 0.4,
        "num_samples": int(waveform.shape[0]),
        "audio_path": str(path),
    }


def _write_image_fixture(path: Path) -> None:
    image = Image.new("RGB", (320, 180), color=(15, 20, 22))
    image.save(path)


def test_parse_capture_region_and_hotkey() -> None:
    assert pilot_runtime.parse_capture_region_value("10,20,300,400") == (10, 20, 300, 400)
    assert pilot_runtime.normalize_pilot_hotkey("f8") == "F8"
    assert pilot_runtime.hotkey_virtual_key("F8") == 0x77


def test_run_pilot_turn_with_injected_locals_writes_contract(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    image_path = tmp_path / "image.png"
    audio_meta = _write_audio_fixture(audio_path)
    _write_image_fixture(image_path)

    def _fake_capture(*, output_path: Path, **_kwargs: Any) -> dict[str, Any]:
        output_path.write_bytes(image_path.read_bytes())
        return {
            "capture_mode": "fixture",
            "monitor_index": 0,
            "region": None,
            "bbox": [0, 0, 320, 180],
            "width": 320,
            "height": 180,
            "screenshot_path": str(output_path),
        }

    def _fake_asr(*, voice_runtime_url: str, audio_path: Path, service_token: str | None = None) -> dict[str, Any]:
        _ = voice_runtime_url, audio_path, service_token
        return {"text": "What should I do next?", "language": "en"}

    def _fake_hybrid(*, gateway_url: str, query: str, service_token: str | None = None) -> dict[str, Any]:
        _ = gateway_url, query, service_token
        return {
            "response_payload": {"status": "ok"},
            "result_payload": {
                "backend": "hybrid_combo_a",
                "profile": "combo_a",
                "planner_mode": "retrieval_first_kag_expansion",
                "planner_status": "hybrid_merged",
                "degraded": False,
                "results_count": 1,
                "retrieval_results_count": 1,
                "kag_results_count": 1,
            },
            "hybrid_results_payload": {
                "planner_mode": "retrieval_first_kag_expansion",
                "planner_status": "hybrid_merged",
                "degraded": False,
                "warnings": [],
                "results_count": 1,
                "retrieval_results_count": 1,
                "kag_results_count": 1,
                "merged_results": [
                    {
                        "id": "quest_book",
                        "title": "Quest Book",
                        "planner_source": "retrieval_and_kag",
                        "matched_entities": ["quest"],
                        "citation": {"id": "quest_book", "source": "fixture", "path": "fixture.jsonl"},
                    }
                ],
            },
            "hybrid_results_json": None,
            "hybrid_run_dir": None,
        }

    def _fake_tts(
        *,
        tts_runtime_url: str,
        text: str,
        turn_dir: Path,
        service_token: str | None = None,
        playback_enabled: bool = True,
    ) -> dict[str, Any]:
        _ = tts_runtime_url, service_token, playback_enabled
        out_wav = turn_dir / "tts_audio_out.wav"
        _write_audio_fixture(out_wav)
        return {
            "status": "ok",
            "mode": "stub",
            "streaming_mode": "fixture",
            "fallback_used": False,
            "fallback_reason": None,
            "chunk_count": 1,
            "events_count": 1,
            "audio_out_wav": str(out_wav),
            "stream_events_jsonl": None,
            "playback_error": None,
            "completed_event": {"event": "completed"},
            "text": text,
        }

    result = pilot_runtime.run_pilot_turn(
        runtime_run_dir=runtime_run_dir,
        audio_input_path=audio_path,
        audio_input_meta=audio_meta,
        hotkey="F8",
        capture_monitor=0,
        capture_region=None,
        gateway_url="http://fixture.gateway",
        voice_runtime_url="http://fixture.voice",
        tts_runtime_url="http://fixture.tts",
        vlm_client=DeterministicStubVLM(),
        grounded_reply_client=DeterministicGroundedReplyStub(),
        playback_enabled=False,
        capture_func=_fake_capture,
        asr_func=_fake_asr,
        hybrid_query_func=_fake_hybrid,
        tts_func=_fake_tts,
        now=datetime(2026, 3, 22, 18, 0, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    payload = result["turn_payload"]
    assert payload["schema_version"] == pilot_runtime.PILOT_TURN_SCHEMA
    assert payload["status"] == "ok"
    assert payload["request"]["transcript"] == "What should I do next?"
    assert payload["hybrid"]["planner_status"] == "hybrid_merged"
    assert payload["citations"][0]["title"] == "Quest Book"
    assert payload["tts"]["status"] == "ok"
    assert Path(payload["paths"]["turn_json"]).is_file()
    saved_payload = json.loads(Path(payload["paths"]["turn_json"]).read_text(encoding="utf-8"))
    assert saved_payload["answer_text"]


def test_run_pilot_turn_records_degraded_failures(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    audio_meta = _write_audio_fixture(audio_path)

    def _failing_capture(*, output_path: Path, **_kwargs: Any) -> dict[str, Any]:
        _ = output_path
        raise RuntimeError("desktop capture unavailable")

    def _fake_asr(*, voice_runtime_url: str, audio_path: Path, service_token: str | None = None) -> dict[str, Any]:
        _ = voice_runtime_url, audio_path, service_token
        return {"text": "Where am I?", "language": "en"}

    def _fake_hybrid(*, gateway_url: str, query: str, service_token: str | None = None) -> dict[str, Any]:
        _ = gateway_url, query, service_token
        return {
            "response_payload": {"status": "ok"},
            "result_payload": {"planner_status": "retrieval_only_fallback", "degraded": True},
            "hybrid_results_payload": {
                "planner_status": "retrieval_only_fallback",
                "degraded": True,
                "warnings": ["kag fallback"],
                "merged_results": [],
            },
            "hybrid_results_json": None,
            "hybrid_run_dir": None,
        }

    def _failing_tts(
        *,
        tts_runtime_url: str,
        text: str,
        turn_dir: Path,
        service_token: str | None = None,
        playback_enabled: bool = True,
    ) -> dict[str, Any]:
        _ = tts_runtime_url, text, turn_dir, service_token, playback_enabled
        raise RuntimeError("tts unavailable")

    result = pilot_runtime.run_pilot_turn(
        runtime_run_dir=runtime_run_dir,
        audio_input_path=audio_path,
        audio_input_meta=audio_meta,
        hotkey="F8",
        capture_monitor=None,
        capture_region=None,
        gateway_url="http://fixture.gateway",
        voice_runtime_url="http://fixture.voice",
        tts_runtime_url="http://fixture.tts",
        vlm_client=None,
        grounded_reply_client=None,
        playback_enabled=False,
        capture_func=_failing_capture,
        asr_func=_fake_asr,
        hybrid_query_func=_fake_hybrid,
        tts_func=_failing_tts,
        now=datetime(2026, 3, 22, 18, 5, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "degraded"
    assert "capture_failed" in payload["degraded_flags"]
    assert "tts_failed" in payload["degraded_flags"]
    assert "retrieval_only_fallback" in payload["degraded_flags"]
    assert "desktop capture unavailable" in payload["errors"]["capture"]
    assert payload["answer_text"].startswith("Pilot degraded mode")


def test_pilot_turn_smoke_writes_turn_and_status_artifacts(tmp_path: Path) -> None:
    summary_json = tmp_path / "summary.json"
    result = pilot_turn_smoke.run_pilot_turn_smoke(
        runs_dir=tmp_path / "runs",
        summary_json=summary_json,
        now=datetime(2026, 3, 22, 19, 0, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    assert summary_json.is_file()
    summary_payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert summary_payload["schema_version"] == pilot_turn_smoke.SMOKE_SUMMARY_SCHEMA
    assert Path(summary_payload["paths"]["turn_json"]).is_file()
    assert Path(summary_payload["paths"]["latest_status_json"]).is_file()
