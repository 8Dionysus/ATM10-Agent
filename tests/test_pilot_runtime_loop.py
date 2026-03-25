from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest
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


def _write_quiet_audio_fixture(path: Path, *, sample_rate: int = 16000) -> dict[str, Any]:
    timeline = np.linspace(0.0, 0.4, int(sample_rate * 0.4), endpoint=False)
    waveform = (0.003 * np.sin(2.0 * np.pi * 220.0 * timeline)).astype(np.float32)
    write_wav_pcm16(path=path, waveform=waveform, sample_rate=sample_rate)
    return {
        "mode": "fixture_audio_quiet",
        "sample_rate": sample_rate,
        "duration_sec": 0.4,
        "num_samples": int(waveform.shape[0]),
        "audio_path": str(path),
    }


def _write_image_fixture(path: Path) -> None:
    image = Image.new("RGB", (320, 180), color=(15, 20, 22))
    image.save(path)


def _fake_session_probe(
    *,
    capture_target_kind: str,
    capture_bbox: list[int] | None = None,
    now: datetime | None = None,
    atm10_probable: bool = True,
    foreground: bool = True,
) -> dict[str, Any]:
    _ = now
    return {
        "schema_version": "atm10_session_probe_v1",
        "checked_at_utc": "2026-03-22T18:00:00+00:00",
        "status": "ok" if atm10_probable and foreground else "attention",
        "window_found": True,
        "process_name": "javaw.exe",
        "window_title": "Minecraft 1.21.1 - ATM10",
        "foreground": foreground,
        "window_bounds": {"left": 0, "top": 0, "right": 320, "bottom": 180, "width": 320, "height": 180},
        "capture_target_kind": capture_target_kind,
        "capture_bbox": capture_bbox,
        "capture_intersects_window": True,
        "atm10_probable": atm10_probable,
        "reason_codes": ([] if atm10_probable else ["capture_target_miss"])
        + ([] if foreground else ["atm10_window_not_foreground"]),
    }


def _fake_live_hud_state(
    *,
    screenshot_path: Path,
    hook_json: Path | None = None,
    tesseract_bin: str = "tesseract",
    now: datetime | None = None,
    status: str = "ok",
) -> dict[str, Any]:
    _ = hook_json, tesseract_bin, now
    return {
        "schema_version": "live_hud_state_v1",
        "checked_at_utc": "2026-03-22T18:00:00+00:00",
        "status": status,
        "screenshot_path": str(screenshot_path),
        "sources": {
            "screenshot": {"status": "ok", "path": str(screenshot_path), "detail": None},
            "mod_hook": {"status": "not_configured", "path": None, "detail": None},
            "ocr": {"status": "ok", "path": str(screenshot_path), "detail": None, "line_count": 2},
        },
        "hud_lines": ["Quest Updated", "Collect 16 wood"],
        "quest_updates": [{"id": "quest:start", "text": "Collect 16 wood", "status": "active"}],
        "player_state": {"dimension": "minecraft:overworld"},
        "context_tags": ["hud", "quest"],
        "text_preview": "Quest Updated Collect 16 wood",
        "hud_line_count": 2,
        "quest_update_count": 1,
        "has_player_state": True,
        "reason_codes": ["mod_hook_not_configured"] if status == "ok" else ["ocr_unavailable"],
    }


def test_parse_capture_region_and_hotkey() -> None:
    assert pilot_runtime.parse_capture_region_value("10,20,300,400") == (10, 20, 300, 400)
    assert pilot_runtime.normalize_pilot_hotkey("f8") == "F8"
    assert pilot_runtime.hotkey_virtual_key("F8") == 0x77


def test_parse_args_uses_gpu_defaults_for_live_openvino_models() -> None:
    args = pilot_runtime.parse_args([])

    assert args.pilot_vlm_device == "GPU"
    assert args.pilot_text_device == "GPU"
    assert args.pilot_vlm_max_new_tokens == 64
    assert args.pilot_text_max_new_tokens == 64
    assert args.pilot_hybrid_timeout_sec == 1.0


def test_push_to_talk_recorder_prefers_microphone_over_remap_input() -> None:
    devices = [
        {"name": "Переназначение звуковых устр. - Input", "max_input_channels": 2},
        {"name": "Набор микрофонов (Технология Intel Smart Sound)", "max_input_channels": 4},
    ]

    selected = pilot_runtime.PushToTalkRecorder.select_input_device_index(
        devices=devices,
        default_device=[0, 3],
        preferred_input_device_index=None,
    )

    assert selected == 1


def test_push_to_talk_recorder_uses_explicit_input_device_index() -> None:
    devices = [
        {"name": "Переназначение звуковых устр. - Input", "max_input_channels": 2},
        {"name": "Набор микрофонов", "max_input_channels": 4},
    ]

    selected = pilot_runtime.PushToTalkRecorder.select_input_device_index(
        devices=devices,
        default_device=[0, 3],
        preferred_input_device_index=1,
    )

    assert selected == 1


def test_write_warmup_image_creates_valid_png(tmp_path: Path) -> None:
    warmup_path = pilot_runtime._write_warmup_image(tmp_path / "pilot_vlm_warmup.png")

    assert warmup_path.is_file()

    image = Image.open(warmup_path)
    image.load()

    assert image.size == (56, 56)
    assert image.mode == "RGB"


def test_prepare_asr_audio_input_boosts_quiet_waveform(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.wav"
    _write_quiet_audio_fixture(audio_path)

    prepared = pilot_runtime._prepare_asr_audio_input(
        audio_path=audio_path,
        turn_dir=tmp_path,
    )

    assert Path(prepared["audio_path"]).name == "audio_input_asr.wav"
    assert prepared["signal"]["raw"]["status"] == "low_signal"
    assert prepared["signal"]["raw"]["peak_abs"] < 0.01
    assert prepared["signal"]["asr_input"]["peak_abs"] > prepared["signal"]["raw"]["peak_abs"]
    assert prepared["asr_preprocess"]["mode"] == "normalized_gain"
    assert prepared["asr_preprocess"]["gain_applied"] > 1.0


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

    def _fake_asr(
        *,
        voice_runtime_url: str,
        audio_path: Path,
        language: str | None = None,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = voice_runtime_url, audio_path, language, service_token
        return {"text": "What should I do next?", "language": "en"}

    def _fake_hybrid(
        *,
        gateway_url: str,
        query: str,
        timeout_sec: float = 0.0,
        topk: int = 0,
        candidate_k: int = 0,
        max_entities_per_doc: int = 0,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = gateway_url, query, timeout_sec, topk, candidate_k, max_entities_per_doc, service_token
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
        language: str | None = None,
        turn_dir: Path,
        service_token: str | None = None,
        playback_enabled: bool = True,
    ) -> dict[str, Any]:
        _ = tts_runtime_url, language, service_token, playback_enabled
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
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_fake_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="en",
        now=datetime(2026, 3, 22, 18, 0, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    payload = result["turn_payload"]
    assert payload["schema_version"] == pilot_runtime.PILOT_TURN_SCHEMA
    assert payload["status"] == "ok"
    assert payload["request"]["transcript"] == "What should I do next?"
    assert payload["transcript_quality"]["status"] == "ok"
    assert payload["hybrid"]["planner_status"] == "hybrid_merged"
    assert payload["citations"][0]["title"] == "Quest Book"
    assert payload["tts"]["status"] == "ok"
    assert payload["grounded_reply"]["provider"] == "deterministic_grounded_reply_stub_v1"
    assert payload["vision"]["provider"] == "deterministic_stub_v1"
    assert payload["answer_language"] == "en"
    assert payload["reply_mode"] == "normal_local"
    assert payload["session"]["atm10_probable"] is True
    assert payload["hud_state"]["status"] == "ok"
    assert Path(payload["paths"]["session_probe_json"]).is_file()
    assert Path(payload["paths"]["live_hud_state_json"]).is_file()
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

    def _fake_asr(
        *,
        voice_runtime_url: str,
        audio_path: Path,
        language: str | None = None,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = voice_runtime_url, audio_path, language, service_token
        return {"text": "Where am I?", "language": "en"}

    def _fake_hybrid(
        *,
        gateway_url: str,
        query: str,
        timeout_sec: float = 0.0,
        topk: int = 0,
        candidate_k: int = 0,
        max_entities_per_doc: int = 0,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = gateway_url, query, timeout_sec, topk, candidate_k, max_entities_per_doc, service_token
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
        language: str | None = None,
        turn_dir: Path,
        service_token: str | None = None,
        playback_enabled: bool = True,
    ) -> dict[str, Any]:
        _ = tts_runtime_url, text, language, turn_dir, service_token, playback_enabled
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
        session_probe_func=lambda **kwargs: _fake_session_probe(atm10_probable=False, foreground=False, **kwargs),
        live_hud_state_func=lambda **kwargs: _fake_live_hud_state(status="partial", **kwargs),
        asr_func=_fake_asr,
        hybrid_query_func=_fake_hybrid,
        tts_func=_failing_tts,
        expected_asr_language="en",
        now=datetime(2026, 3, 22, 18, 5, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "degraded"
    assert "capture_failed" in payload["degraded_flags"]
    assert "tts_failed" in payload["degraded_flags"]
    assert "retrieval_only_fallback" in payload["degraded_flags"]
    assert "session_target_not_confirmed" in payload["degraded_flags"]
    assert payload["reply_mode"] == "fallback_answer"
    assert payload["hud_state"]["status"] == "partial"
    assert "desktop capture unavailable" in payload["errors"]["capture"]
    assert payload["grounded_reply"]["provider"] == "deterministic_fallback_v1"
    assert payload["answer_language"] == "en"
    assert not payload["answer_text"].startswith("Pilot degraded mode")


def test_run_pilot_turn_marks_hybrid_degraded_when_gateway_response_is_degraded(tmp_path: Path) -> None:
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

    def _fake_asr(
        *,
        voice_runtime_url: str,
        audio_path: Path,
        language: str | None = None,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = voice_runtime_url, audio_path, language, service_token
        return {"text": "what next", "language": "en"}

    def _fake_hybrid(
        *,
        gateway_url: str,
        query: str,
        timeout_sec: float = 0.0,
        topk: int = 0,
        candidate_k: int = 0,
        max_entities_per_doc: int = 0,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = gateway_url, query, timeout_sec, topk, candidate_k, max_entities_per_doc, service_token
        return {
            "response_payload": {"status": "ok"},
            "result_payload": {"planner_status": "grounding_unavailable", "degraded": True},
            "hybrid_results_payload": {
                "planner_status": "grounding_unavailable",
                "degraded": True,
                "warnings": ["retrieval stage fallback: qdrant collection missing"],
                "merged_results": [],
            },
            "hybrid_results_json": None,
            "hybrid_run_dir": None,
        }

    def _fake_tts(
        *,
        tts_runtime_url: str,
        text: str,
        language: str | None = None,
        turn_dir: Path,
        service_token: str | None = None,
        playback_enabled: bool = True,
    ) -> dict[str, Any]:
        _ = tts_runtime_url, text, language, turn_dir, service_token, playback_enabled
        return {
            "status": "ok",
            "mode": "stub",
            "streaming_mode": "fixture",
            "fallback_used": False,
            "fallback_reason": None,
            "chunk_count": 1,
            "events_count": 1,
            "audio_out_wav": None,
            "stream_events_jsonl": None,
            "playback_error": None,
            "completed_event": {"event": "completed"},
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
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_fake_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="en",
        now=datetime(2026, 3, 22, 18, 7, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "degraded"
    assert "hybrid_degraded" in payload["degraded_flags"]
    assert payload["hybrid"]["planner_status"] == "grounding_unavailable"
    assert payload["answer_language"] == "en"


def test_run_pilot_turn_skips_hybrid_for_low_signal_transcript(tmp_path: Path) -> None:
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

    def _fake_asr(
        *,
        voice_runtime_url: str,
        audio_path: Path,
        language: str | None = None,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = voice_runtime_url, audio_path, language, service_token
        return {"text": "Thank you.", "language": "en"}

    def _failing_hybrid(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hybrid should be skipped for a low-signal transcript")

    def _fake_tts(
        *,
        tts_runtime_url: str,
        text: str,
        language: str | None = None,
        turn_dir: Path,
        service_token: str | None = None,
        playback_enabled: bool = True,
    ) -> dict[str, Any]:
        _ = tts_runtime_url, text, language, turn_dir, service_token, playback_enabled
        return {
            "status": "ok",
            "mode": "stub",
            "streaming_mode": "fixture",
            "fallback_used": False,
            "fallback_reason": None,
            "chunk_count": 1,
            "events_count": 1,
            "audio_out_wav": None,
            "stream_events_jsonl": None,
            "playback_error": None,
            "completed_event": {"event": "completed"},
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
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_failing_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="ru",
        now=datetime(2026, 3, 24, 20, 0, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "degraded"
    assert payload["transcript_quality"]["status"] == "low_signal"
    assert "ascii_filler" in payload["transcript_quality"]["reason_codes"]
    assert "hybrid_skipped_low_signal" in payload["degraded_flags"]
    assert payload["reply_mode"] == "visual_only_fallback"
    assert payload["answer_language"] == "ru"
    assert "Thank you" not in payload["answer_text"]


def test_run_pilot_turn_marks_quiet_russian_hallucination_as_low_signal(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    image_path = tmp_path / "image.png"
    audio_meta = _write_quiet_audio_fixture(audio_path)
    _write_image_fixture(image_path)
    seen_asr_paths: list[Path] = []

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

    def _fake_asr(
        *,
        voice_runtime_url: str,
        audio_path: Path,
        language: str | None = None,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = voice_runtime_url, language, service_token
        seen_asr_paths.append(audio_path)
        return {"text": "Продолжение следует...", "language": "ru"}

    def _failing_hybrid(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hybrid should be skipped for a quiet hallucinated transcript")

    def _failing_grounded_reply(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("grounded reply should be skipped for a quiet hallucinated transcript")

    def _fake_tts(
        *,
        tts_runtime_url: str,
        text: str,
        language: str | None = None,
        turn_dir: Path,
        service_token: str | None = None,
        playback_enabled: bool = True,
    ) -> dict[str, Any]:
        _ = tts_runtime_url, text, language, turn_dir, service_token, playback_enabled
        return {
            "status": "ok",
            "mode": "stub",
            "streaming_mode": "fixture",
            "fallback_used": False,
            "fallback_reason": None,
            "chunk_count": 1,
            "events_count": 1,
            "audio_out_wav": None,
            "stream_events_jsonl": None,
            "playback_error": None,
            "completed_event": {"event": "completed"},
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
        grounded_reply_client=type("UnusedReply", (), {"generate_reply": staticmethod(_failing_grounded_reply)})(),
        playback_enabled=False,
        capture_func=_fake_capture,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_failing_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="ru",
        now=datetime(2026, 3, 25, 4, 20, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert seen_asr_paths
    assert seen_asr_paths[0].name == "audio_input_asr.wav"
    assert payload["status"] == "degraded"
    assert payload["audio"]["signal"]["raw"]["status"] == "low_signal"
    assert payload["transcript_quality"]["status"] == "low_signal"
    assert "known_low_signal_phrase" in payload["transcript_quality"]["reason_codes"]
    assert "audio_signal_low" in payload["transcript_quality"]["reason_codes"]
    assert "hybrid_skipped_low_signal" in payload["degraded_flags"]
    assert "grounded_reply_skipped_low_signal" in payload["degraded_flags"]
    assert payload["reply_mode"] == "visual_only_fallback"
    assert payload["grounded_reply"]["provider"] == "visual_only_fallback_v1"
    assert "Продолжение следует" not in payload["answer_text"]


def test_run_pilot_turn_replaces_reasoning_leak_before_tts(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    image_path = tmp_path / "image.png"
    audio_meta = _write_audio_fixture(audio_path)
    _write_image_fixture(image_path)
    seen_tts_texts: list[str] = []

    class _ReasoningLeakReplyClient:
        def generate_reply(
            self,
            *,
            transcript: str,
            visual_summary: str | None,
            citations: list[dict[str, Any]],
            hybrid_summary: dict[str, Any] | None,
            degraded_flags: list[str] | None = None,
            preferred_language: str | None = None,
        ) -> dict[str, Any]:
            _ = transcript, visual_summary, citations, hybrid_summary, degraded_flags, preferred_language
            return {
                "provider": "openvino_genai_grounded_reply_v1",
                "model": "fixture",
                "device": "CPU",
                "prompt": "",
                "answer_text": (
                    "<think> Okay, let's tackle this. The user is in a dark cave. "
                    "The answer should be in JSON format."
                ),
                "cited_entities": [],
                "degraded_flags": [],
                "raw_response_text": (
                    "<think> Okay, let's tackle this. The user is in a dark cave. "
                    "The answer should be in JSON format."
                ),
            }

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

    def _fake_asr(
        *,
        voice_runtime_url: str,
        audio_path: Path,
        language: str | None = None,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = voice_runtime_url, audio_path, language, service_token
        return {"text": "Что делать дальше?", "language": "ru"}

    def _fake_tts(
        *,
        tts_runtime_url: str,
        text: str,
        language: str | None = None,
        turn_dir: Path,
        service_token: str | None = None,
        playback_enabled: bool = True,
    ) -> dict[str, Any]:
        _ = tts_runtime_url, language, turn_dir, service_token, playback_enabled
        seen_tts_texts.append(text)
        return {
            "status": "ok",
            "mode": "stub",
            "streaming_mode": "fixture",
            "fallback_used": False,
            "fallback_reason": None,
            "chunk_count": 1,
            "events_count": 1,
            "audio_out_wav": None,
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
        gateway_url=None,
        voice_runtime_url="http://fixture.voice",
        tts_runtime_url="http://fixture.tts",
        vlm_client=DeterministicStubVLM(),
        grounded_reply_client=_ReasoningLeakReplyClient(),
        playback_enabled=False,
        capture_func=_fake_capture,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        tts_func=_fake_tts,
        now=datetime(2026, 3, 24, 19, 20, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "degraded"
    assert "grounded_reply_reasoning_leak" in payload["degraded_flags"]
    assert "grounded_reply_answer_fallback" in payload["degraded_flags"]
    assert seen_tts_texts == [payload["answer_text"]]
    assert "<think>" not in payload["answer_text"]
    assert "let's tackle this" not in payload["answer_text"].lower()
    assert payload["degraded_services"] == sorted(dict.fromkeys([*payload["degraded_services"], "text_core"]))


def test_run_pilot_turn_defaults_reply_language_to_russian_when_asr_language_is_missing(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    image_path = tmp_path / "image.png"
    audio_meta = _write_audio_fixture(audio_path)
    _write_image_fixture(image_path)
    seen_tts_languages: list[str | None] = []

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

    def _fake_asr(
        *,
        voice_runtime_url: str,
        audio_path: Path,
        language: str | None = None,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = voice_runtime_url, audio_path, language, service_token
        return {"text": "what next", "language": ""}

    def _fake_tts(
        *,
        tts_runtime_url: str,
        text: str,
        language: str | None = None,
        turn_dir: Path,
        service_token: str | None = None,
        playback_enabled: bool = True,
    ) -> dict[str, Any]:
        _ = tts_runtime_url, text, turn_dir, service_token, playback_enabled
        seen_tts_languages.append(language)
        return {
            "status": "ok",
            "mode": "stub",
            "streaming_mode": "fixture",
            "fallback_used": False,
            "fallback_reason": None,
            "chunk_count": 1,
            "events_count": 1,
            "chunk_engines": ["windows_sapi_fallback"],
            "audio_out_wav": None,
            "stream_events_jsonl": None,
            "playback_error": None,
            "completed_event": {"event": "completed"},
        }

    result = pilot_runtime.run_pilot_turn(
        runtime_run_dir=runtime_run_dir,
        audio_input_path=audio_path,
        audio_input_meta=audio_meta,
        hotkey="F8",
        capture_monitor=0,
        capture_region=None,
        gateway_url=None,
        voice_runtime_url="http://fixture.voice",
        tts_runtime_url="http://fixture.tts",
        vlm_client=DeterministicStubVLM(),
        grounded_reply_client=DeterministicGroundedReplyStub(),
        playback_enabled=False,
        capture_func=_fake_capture,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        tts_func=_fake_tts,
        now=datetime(2026, 3, 22, 18, 9, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["answer_language"] == "ru"
    assert payload["grounded_reply"]["answer_language"] == "ru"
    assert seen_tts_languages == ["ru"]


def test_synthesize_with_tts_runtime_marks_silence_fallback_as_degraded(tmp_path: Path) -> None:
    audio_path = tmp_path / "chunk.wav"
    audio_meta = _write_audio_fixture(audio_path, sample_rate=22050)
    audio_bytes = audio_path.read_bytes()
    seen_payloads: list[dict[str, Any]] = []

    def _fake_request_ndjson(
        *,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        timeout_sec: float = 300.0,
        service_token: str | None = None,
    ) -> list[dict[str, Any]]:
        _ = method, url, payload, timeout_sec, service_token, audio_meta
        if payload is not None:
            seen_payloads.append(dict(payload))
        return [
            {"event": "started"},
            {
                "event": "audio_chunk",
                "index": 0,
                "engine": "silence_fallback",
                "sample_rate": 22050,
                "cached": False,
                "audio_wav_b64": base64.b64encode(audio_bytes).decode("ascii"),
            },
            {"event": "completed"},
        ]

    original_request_ndjson = pilot_runtime._request_ndjson
    try:
        pilot_runtime._request_ndjson = _fake_request_ndjson
        payload = pilot_runtime.synthesize_with_tts_runtime(
            tts_runtime_url="http://fixture.tts",
            text="привет fallback",
            turn_dir=tmp_path / "turn",
            playback_enabled=False,
        )
    finally:
        pilot_runtime._request_ndjson = original_request_ndjson

    assert payload["status"] == "degraded"
    assert payload["fallback_used"] is True
    assert payload["fallback_reason"] == "silence_fallback_audio"
    assert payload["chunk_engines"] == ["silence_fallback"]
    assert seen_payloads[0]["language"] == "ru"


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


def test_run_pilot_runtime_loop_marks_error_when_hotkey_init_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_build_provider(**kwargs: Any) -> Any:
        if kwargs.get("provider_kind") == "vlm":
            return DeterministicStubVLM()
        return DeterministicGroundedReplyStub()

    class _FailingHotkey:
        def __init__(self, hotkey: str) -> None:
            _ = hotkey
            raise RuntimeError("hotkey polling unavailable")

    monkeypatch.setattr(pilot_runtime, "_build_provider", _fake_build_provider)
    monkeypatch.setattr(pilot_runtime, "PollingHotkey", _FailingHotkey)

    runs_dir = tmp_path / "pilot-runtime"
    result = pilot_runtime.run_pilot_runtime_loop(
        runs_dir=runs_dir,
        gateway_url="http://127.0.0.1:8770",
        voice_runtime_url="http://127.0.0.1:8765",
        tts_runtime_url="http://127.0.0.1:8780",
        hotkey="F8",
        capture_monitor=None,
        capture_region=None,
        hud_hook_json=None,
        tesseract_bin="tesseract",
        pilot_vlm_model_dir=tmp_path / "models" / "vlm",
        pilot_text_model_dir=tmp_path / "models" / "text",
        pilot_vlm_device="CPU",
        pilot_text_device="CPU",
        playback_enabled=False,
        now=datetime(2026, 3, 23, 21, 0, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["run_payload"]["status"] == "error"
    assert result["run_payload"]["error"] == "hotkey polling unavailable"

    latest_status_path = runs_dir / "pilot_runtime_status_latest.json"
    latest_status_payload = json.loads(latest_status_path.read_text(encoding="utf-8"))
    assert latest_status_payload["schema_version"] == pilot_runtime.PILOT_RUNTIME_STATUS_SCHEMA
    assert latest_status_payload["status"] == "error"
    assert latest_status_payload["last_error"] == "hotkey polling unavailable"
    assert latest_status_payload["effective_config"]["vlm_provider"] == "openvino"
    assert latest_status_payload["effective_config"]["text_provider"] == "openvino"
    assert latest_status_payload["provider_init"]["vlm"]["status"] == "ok"
    assert latest_status_payload["provider_init"]["text"]["status"] == "ok"
    assert latest_status_payload["paths"]["run_dir"] == str(result["run_dir"])


def test_run_pilot_runtime_loop_records_openvino_warmup_rollup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeVLMProvider:
        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
            assert image_path.exists()
            assert "summary" in prompt
            return {"summary": "Темная пещера", "next_steps": []}

    class _FakeReplyProvider:
        def generate_reply(
            self,
            *,
            transcript: str,
            visual_summary: str | None,
            citations: list[dict[str, Any]],
            hybrid_summary: dict[str, Any] | None,
            degraded_flags: list[str] | None = None,
            preferred_language: str | None = None,
        ) -> dict[str, Any]:
            _ = transcript, visual_summary, citations, hybrid_summary, degraded_flags, preferred_language
            return {"answer_text": "Открой книгу квестов", "cited_entities": [], "degraded_flags": []}

    def _fake_build_provider(**kwargs: Any) -> Any:
        if kwargs.get("provider_kind") == "vlm":
            return _FakeVLMProvider()
        return _FakeReplyProvider()

    class _FailingHotkey:
        def __init__(self, hotkey: str) -> None:
            _ = hotkey
            raise RuntimeError("hotkey polling unavailable")

    monkeypatch.setattr(pilot_runtime, "_build_provider", _fake_build_provider)
    monkeypatch.setattr(pilot_runtime, "PollingHotkey", _FailingHotkey)

    runs_dir = tmp_path / "pilot-runtime"
    result = pilot_runtime.run_pilot_runtime_loop(
        runs_dir=runs_dir,
        gateway_url="http://127.0.0.1:8770",
        voice_runtime_url="http://127.0.0.1:8765",
        tts_runtime_url="http://127.0.0.1:8780",
        hotkey="F8",
        capture_monitor=None,
        capture_region=None,
        hud_hook_json=None,
        tesseract_bin="tesseract",
        pilot_vlm_model_dir=tmp_path / "models" / "vlm",
        pilot_text_model_dir=tmp_path / "models" / "text",
        pilot_vlm_device="GPU",
        pilot_text_device="NPU",
        pilot_vlm_provider="openvino",
        pilot_text_provider="openvino",
        playback_enabled=False,
        now=datetime(2026, 3, 24, 20, 5, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    provider_init = result["run_payload"]["provider_init"]
    assert provider_init["vlm"]["warmup"]["requested"] is True
    assert provider_init["vlm"]["warmup"]["ok"] is True
    assert provider_init["text"]["warmup"]["requested"] is True
    assert provider_init["text"]["warmup"]["ok"] is True

    latest_status_payload = json.loads((runs_dir / "pilot_runtime_status_latest.json").read_text(encoding="utf-8"))
    assert latest_status_payload["provider_init"]["vlm"]["warmup"]["ok"] is True
    assert latest_status_payload["provider_init"]["text"]["warmup"]["ok"] is True
