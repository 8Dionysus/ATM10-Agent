from __future__ import annotations

import base64
import json
import threading
from concurrent.futures import Future
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


def _write_too_short_quiet_audio_fixture(path: Path, *, sample_rate: int = 16000) -> dict[str, Any]:
    timeline = np.linspace(0.0, 0.03, int(sample_rate * 0.03), endpoint=False)
    waveform = (0.0005 * np.sin(2.0 * np.pi * 220.0 * timeline)).astype(np.float32)
    write_wav_pcm16(path=path, waveform=waveform, sample_rate=sample_rate)
    return {
        "mode": "fixture_audio_too_short_quiet",
        "sample_rate": sample_rate,
        "duration_sec": 0.03,
        "num_samples": int(waveform.shape[0]),
        "audio_path": str(path),
    }


def _write_image_fixture(path: Path) -> None:
    image = Image.new("RGB", (320, 180), color=(15, 20, 22))
    image.save(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


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


def test_short_screen_grounded_request_detector_rejects_recipe_style_queries() -> None:
    assert pilot_runtime._looks_like_short_screen_grounded_request("Это меню?") is True
    assert pilot_runtime._looks_like_short_screen_grounded_request("Как открыть меню крафта?") is False


def test_build_visual_observation_answer_compacts_direct_context() -> None:
    answer = pilot_runtime.build_visual_observation_answer(
        visual_summary=(
            "Меню ATM10 и заснеженная деревня на фоне. "
            "HUD: Quest Updated Collect 16 wood. "
            "Window: Minecraft 1.21.1 - ATM10."
        ),
        preferred_language="ru",
    )

    assert answer == "Меню ATM10 и заснеженная деревня на фоне."


def test_build_visual_observation_answer_extracts_summary_from_jsonish_text() -> None:
    answer = pilot_runtime.build_visual_observation_answer(
        visual_summary='```json {"summary":"A snowy village menu is visible!!!!!!!!!!"} ```',
        preferred_language="en",
    )

    assert answer == "A snowy village menu is visible!"


def test_capture_screen_image_uses_window_handle_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PIL import ImageGrab

    captured: dict[str, Any] = {}
    monkeypatch.setattr(pilot_runtime.sys, "platform", "win32")

    def _fake_grab(
        bbox: tuple[int, int, int, int] | None = None,
        include_layered_windows: bool = False,
        all_screens: bool = False,
        xdisplay: str | None = None,
        window: int | None = None,
    ) -> Image.Image:
        _ = include_layered_windows, xdisplay
        captured.update(
            {
                "bbox": bbox,
                "all_screens": all_screens,
                "window": window,
            }
        )
        return Image.new("RGB", (640, 360), color=(20, 28, 40))

    monkeypatch.setattr(ImageGrab, "grab", _fake_grab)
    screenshot_path = tmp_path / "window_capture.png"
    payload = pilot_runtime.capture_screen_image(
        output_path=screenshot_path,
        monitor_index=0,
        region=None,
        window_handle=4242,
        window_title="Minecraft 1.21.1 - ATM10",
        window_bounds=[0, 0, 320, 180],
    )

    assert captured == {"bbox": None, "all_screens": False, "window": 4242}
    assert screenshot_path.is_file()
    assert payload["capture_mode"] == "window"
    assert payload["capture_backend"] == "pillow_imagegrab_window"
    assert payload["window_handle"] == 4242
    assert payload["window_title"] == "Minecraft 1.21.1 - ATM10"
    assert payload["window_bounds"] == [0, 0, 320, 180]
    assert payload["bbox"] == [0, 0, 320, 180]
    assert payload["raw_width"] == 640
    assert payload["raw_height"] == 360
    assert payload["resized_from"] == [640, 360]
    with Image.open(screenshot_path) as image:
        assert image.size == (320, 180)


def test_capture_screen_image_prefers_dxcam_monitor_capture_and_resizes_to_logical_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import ImageGrab

    pilot_runtime._DXCAM_CAMERA_CACHE.clear()
    seen: dict[str, Any] = {}
    monkeypatch.setattr(pilot_runtime.sys, "platform", "win32")

    class _FakeCamera:
        width = 2880
        height = 1920

        def grab(self, region: tuple[int, int, int, int] | None = None, new_frame_only: bool = True) -> np.ndarray:
            seen["region"] = region
            seen["new_frame_only"] = new_frame_only
            return np.zeros((1920, 2880, 4), dtype=np.uint8)

    def _unexpected_pillow_grab(**_kwargs: Any) -> Image.Image:
        raise AssertionError("Pillow desktop fallback should not run when DXcam succeeds")

    monkeypatch.setattr(pilot_runtime, "enumerate_display_monitors", lambda: [(0, 0, 1152, 768)])
    monkeypatch.setattr(pilot_runtime, "_get_dxcam_camera", lambda *, output_idx: _FakeCamera())
    monkeypatch.setattr(ImageGrab, "grab", _unexpected_pillow_grab)

    screenshot_path = tmp_path / "dxcam_monitor_capture.png"
    payload = pilot_runtime.capture_screen_image(
        output_path=screenshot_path,
        monitor_index=0,
        region=None,
    )

    assert seen == {"region": None, "new_frame_only": False}
    assert payload["capture_mode"] == "monitor"
    assert payload["capture_backend"] == "dxcam_dxgi"
    assert payload["monitor_index"] == 0
    assert payload["resolved_monitor_index"] == 0
    assert payload["bbox"] == [0, 0, 1152, 768]
    assert payload["raw_width"] == 2880
    assert payload["raw_height"] == 1920
    assert payload["resized_from"] == [2880, 1920]
    assert payload["native_region"] is None
    assert "backend_errors" not in payload
    with Image.open(screenshot_path) as image:
        assert image.size == (1152, 768)


def test_capture_screen_image_scales_region_for_dxcam_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pilot_runtime._DXCAM_CAMERA_CACHE.clear()
    seen: dict[str, Any] = {}
    monkeypatch.setattr(pilot_runtime.sys, "platform", "win32")

    class _FakeCamera:
        width = 1920
        height = 1080

        def grab(self, region: tuple[int, int, int, int] | None = None, new_frame_only: bool = True) -> np.ndarray:
            seen["region"] = region
            seen["new_frame_only"] = new_frame_only
            return np.zeros((100, 200, 4), dtype=np.uint8)

    monkeypatch.setattr(pilot_runtime, "enumerate_display_monitors", lambda: [(100, 50, 1060, 590)])
    monkeypatch.setattr(pilot_runtime, "_get_dxcam_camera", lambda *, output_idx: _FakeCamera())

    screenshot_path = tmp_path / "dxcam_region_capture.png"
    payload = pilot_runtime.capture_screen_image(
        output_path=screenshot_path,
        monitor_index=None,
        region=(110, 70, 100, 50),
    )

    assert seen == {"region": (20, 40, 220, 140), "new_frame_only": False}
    assert payload["capture_mode"] == "region"
    assert payload["capture_backend"] == "dxcam_dxgi"
    assert payload["monitor_index"] is None
    assert payload["resolved_monitor_index"] == 0
    assert payload["bbox"] == [110, 70, 210, 120]
    assert payload["native_region"] == [20, 40, 220, 140]
    assert payload["raw_width"] == 200
    assert payload["raw_height"] == 100
    assert payload["resized_from"] == [200, 100]
    with Image.open(screenshot_path) as image:
        assert image.size == (100, 50)


def test_capture_screen_image_falls_back_to_pillow_when_dxcam_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import ImageGrab

    pilot_runtime._DXCAM_CAMERA_CACHE.clear()
    captured: dict[str, Any] = {}
    monkeypatch.setattr(pilot_runtime.sys, "platform", "win32")

    def _failing_get_dxcam_camera(*, output_idx: int) -> Any:
        _ = output_idx
        raise RuntimeError("dxcam failed")

    def _fake_pillow_grab(
        bbox: tuple[int, int, int, int] | None = None,
        include_layered_windows: bool = False,
        all_screens: bool = False,
        xdisplay: str | None = None,
        window: int | None = None,
    ) -> Image.Image:
        _ = include_layered_windows, xdisplay
        captured.update({"bbox": bbox, "all_screens": all_screens, "window": window})
        return Image.new("RGB", (320, 180), color=(12, 24, 36))

    monkeypatch.setattr(pilot_runtime, "enumerate_display_monitors", lambda: [(0, 0, 320, 180)])
    monkeypatch.setattr(pilot_runtime, "_get_dxcam_camera", _failing_get_dxcam_camera)
    monkeypatch.setattr(ImageGrab, "grab", _fake_pillow_grab)

    screenshot_path = tmp_path / "pillow_fallback_capture.png"
    payload = pilot_runtime.capture_screen_image(
        output_path=screenshot_path,
        monitor_index=0,
        region=None,
    )

    assert captured == {"bbox": (0, 0, 320, 180), "all_screens": True, "window": None}
    assert payload["capture_mode"] == "monitor"
    assert payload["capture_backend"] == "pillow_imagegrab_desktop"
    assert payload["backend_errors"] == [{"backend": "dxcam_dxgi", "error": "dxcam failed"}]
    with Image.open(screenshot_path) as image:
        assert image.size == (320, 180)


def test_parse_args_uses_gpu_defaults_for_live_openvino_models() -> None:
    args = pilot_runtime.parse_args([])

    assert args.host_profile == "ov_intel_core_ultra_local"
    assert args.host_profile_config["id"] == "ov_intel_core_ultra_local"
    assert args.pilot_vlm_device == "GPU"
    assert args.pilot_text_device == "GPU"
    assert args.pilot_vlm_max_new_tokens == 64
    assert args.pilot_text_max_new_tokens == 64


def test_parse_args_accepts_disabled_runtime_urls() -> None:
    args = pilot_runtime.parse_args(
        [
            "--voice-runtime-url",
            "disabled",
            "--tts-runtime-url",
            "off",
        ]
    )

    assert args.voice_runtime_url is None
    assert args.tts_runtime_url is None
    assert args.pilot_hybrid_timeout_sec == 1.0


def test_build_pilot_vlm_prompt_defaults_to_russian() -> None:
    prompt = pilot_runtime._build_pilot_vlm_prompt(preferred_language="ru")

    assert "Write summary in Russian." in prompt
    assert "Default summary language is Russian" in prompt
    assert "Prefer menu state, visible buttons, biome or structures" in prompt


def test_visual_observation_request_detects_colloquial_russian_phrase() -> None:
    assert pilot_runtime._looks_like_visual_observation_request("Сейчас что-то видишь.") is True
    assert pilot_runtime._looks_like_visual_observation_request("Видишь что-нибудь на экране?") is True
    assert pilot_runtime._looks_like_visual_observation_request("Открой карту мира.") is False


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


def test_push_to_talk_recorder_collapse_to_mono_selects_strongest_channel() -> None:
    waveform = np.array(
        [
            [0.0001, 0.20],
            [0.0002, -0.25],
            [0.0001, 0.30],
            [0.0002, -0.35],
        ],
        dtype=np.float32,
    )

    mono, meta = pilot_runtime.PushToTalkRecorder._collapse_to_mono(waveform)

    assert meta["channels"] == 2
    assert meta["selected_channel_index"] == 1
    assert meta["selected_channel_rms"] is not None
    assert len(meta["channel_rms"]) == 2
    assert np.allclose(mono, waveform[:, 1])


def test_push_to_talk_recorder_collapse_to_mono_handles_empty_waveform() -> None:
    mono, meta = pilot_runtime.PushToTalkRecorder._collapse_to_mono(np.zeros((0, 2), dtype=np.float32))

    assert mono.size == 0
    assert meta["channels"] == 2
    assert meta["selected_channel_index"] is None
    assert meta["selected_channel_rms"] is None
    assert meta["channel_rms"] == []


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


def test_write_silence_fallback_audio_creates_short_wav(tmp_path: Path) -> None:
    audio_path = tmp_path / "silence.wav"
    capture_diagnostics = {
        "callback_count": 0,
        "callback_frames": 0,
        "total_frames": 0,
        "overflow_count": 0,
        "first_callback_offset_sec": None,
        "last_callback_offset_sec": None,
        "duration_sec": 0.3,
    }

    payload = pilot_runtime._write_silence_fallback_audio(
        output_path=audio_path,
        sample_rate=16000,
        duration_sec=0.3,
        capture_error="No audio frames were captured during push-to-talk.",
        input_device_index=1,
        input_device_name="Mic Array",
        capture_diagnostics=capture_diagnostics,
    )

    assert audio_path.is_file()
    assert payload["mode"] == "push_to_talk_silence_fallback"
    assert payload["input_device_index"] == 1
    assert payload["input_device_name"] == "Mic Array"
    assert payload["sample_rate"] == 16000
    assert payload["num_samples"] >= int(16000 * 0.2)
    assert payload["capture_diagnostics"] == capture_diagnostics


def test_push_to_talk_recorder_capture_diagnostics_reports_callback_stats() -> None:
    recorder = pilot_runtime.PushToTalkRecorder(sample_rate=16000)
    recorder._started_at = 10.0
    recorder._callback_count = 3
    recorder._callback_frames = 1536
    recorder._overflow_count = 1
    recorder._first_callback_at = 10.05
    recorder._last_callback_at = 10.31

    diagnostics = recorder.capture_diagnostics(duration_sec=0.42, total_frames=1536)

    assert diagnostics == {
        "callback_count": 3,
        "callback_frames": 1536,
        "total_frames": 1536,
        "overflow_count": 1,
        "first_callback_offset_sec": 0.05,
        "last_callback_offset_sec": 0.31,
        "duration_sec": 0.42,
    }


def test_run_pilot_turn_falls_back_to_hotkey_down_prefetch_when_live_capture_fails(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    audio_meta = _write_audio_fixture(audio_path)

    prefetched_image = tmp_path / "prefetched_menu.png"
    Image.new("RGB", (320, 180), color=(210, 230, 255)).save(prefetched_image)
    prefetched_capture_payload = {
        "capture_mode": "monitor",
        "monitor_index": 0,
        "region": None,
        "bbox": [0, 0, 320, 180],
        "width": 320,
        "height": 180,
        "screenshot_path": str(prefetched_image),
    }

    def _capture_should_fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("live capture failed")

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
            "result_payload": {"planner_status": "hybrid_merged", "degraded": False},
            "hybrid_results_payload": {"planner_status": "hybrid_merged", "degraded": False, "warnings": [], "merged_results": []},
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
        capture_func=_capture_should_fail,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_fake_hybrid,
        tts_func=_fake_tts,
        pre_captured_screenshot_path=prefetched_image,
        pre_captured_capture_payload=prefetched_capture_payload,
        expected_asr_language="en",
        now=datetime(2026, 3, 28, 2, 0, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    screenshot_path = Path(payload["paths"]["screenshot_png"])
    assert payload["capture"]["capture_source"] == "hotkey_down_prefetch_fallback"
    assert screenshot_path.read_bytes() == prefetched_image.read_bytes()
    assert payload["capture"]["prefetch_fallback_reason"] == "live capture failed"
    assert payload["vision"]["provider"] == "deterministic_stub_v1"
    assert payload["vision"]["summary"] == "Stub analysis: no real vision model invoked."
    assert payload["capture"]["bbox"] == [0, 0, 320, 180]


def test_run_pilot_turn_prefers_live_capture_over_hotkey_down_prefetch(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    audio_meta = _write_audio_fixture(audio_path)

    prefetched_image = tmp_path / "prefetched_menu.png"
    live_image = tmp_path / "live_frame.png"
    Image.new("RGB", (320, 180), color=(210, 230, 255)).save(prefetched_image)
    Image.new("RGB", (320, 180), color=(22, 30, 44)).save(live_image)
    prefetched_capture_payload = {
        "capture_mode": "monitor",
        "monitor_index": 0,
        "region": None,
        "bbox": [0, 0, 320, 180],
        "width": 320,
        "height": 180,
        "screenshot_path": str(prefetched_image),
    }

    def _capture_live(*, output_path: Path, **_kwargs: Any) -> dict[str, Any]:
        output_path.write_bytes(live_image.read_bytes())
        return {
            "capture_mode": "monitor",
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
            "result_payload": {"planner_status": "hybrid_merged", "degraded": False},
            "hybrid_results_payload": {"planner_status": "hybrid_merged", "degraded": False, "warnings": [], "merged_results": []},
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
        capture_func=_capture_live,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_fake_hybrid,
        tts_func=_fake_tts,
        pre_captured_screenshot_path=prefetched_image,
        pre_captured_capture_payload=prefetched_capture_payload,
        expected_asr_language="en",
        now=datetime(2026, 3, 28, 2, 1, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    screenshot_path = Path(payload["paths"]["screenshot_png"])
    assert payload["capture"]["capture_source"] == "hotkey_up_capture"
    assert payload["capture"]["prefetched_screenshot_path"] == str(prefetched_image)
    assert screenshot_path.read_bytes() == live_image.read_bytes()


def test_run_pilot_turn_reuses_prefetched_vision_when_frame_matches(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    audio_meta = _write_audio_fixture(audio_path)

    prefetched_image = tmp_path / "prefetched_menu.png"
    live_image = tmp_path / "live_menu.png"
    Image.new("RGB", (320, 180), color=(210, 230, 255)).save(prefetched_image)
    live_image.write_bytes(prefetched_image.read_bytes())
    prefetched_capture_payload = {
        "capture_mode": "monitor",
        "monitor_index": 0,
        "region": None,
        "bbox": [0, 0, 320, 180],
        "width": 320,
        "height": 180,
        "screenshot_path": str(prefetched_image),
    }
    prefetched_vision_future: Future[dict[str, Any]] = Future()
    prefetched_vision_future.set_result(
        {
            "input_image": None,
            "vision_payload": {
                "provider": "fixture_vlm_prefetch",
                "summary": "A snowy village menu is visible.",
                "next_steps": [],
            },
            "visual_summary": "A snowy village menu is visible.",
            "error": None,
            "degraded_flags": [],
            "latency_sec": 0.25,
            "source": "live_capture_v1",
        }
    )

    class _UnusedVisionClient:
        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
            _ = image_path, prompt
            raise AssertionError("live vision should be skipped when prefetched vision is reusable")

    def _capture_live(*, output_path: Path, **_kwargs: Any) -> dict[str, Any]:
        output_path.write_bytes(live_image.read_bytes())
        return {
            "capture_mode": "monitor",
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
        return {"text": "What do you see on the screen?", "language": "en"}

    def _failing_hybrid(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hybrid should be skipped for direct visual observation requests")

    def _failing_grounded_reply(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("grounded reply should be skipped for direct visual observation requests")

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
        vlm_client=_UnusedVisionClient(),
        grounded_reply_client=type("UnusedReply", (), {"generate_reply": staticmethod(_failing_grounded_reply)})(),
        playback_enabled=False,
        capture_func=_capture_live,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_failing_hybrid,
        tts_func=_fake_tts,
        pre_captured_screenshot_path=prefetched_image,
        pre_captured_capture_payload=prefetched_capture_payload,
        pre_captured_vision_future=prefetched_vision_future,
        expected_asr_language="en",
        now=datetime(2026, 3, 28, 2, 2, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "ok"
    assert payload["capture"]["prefetched_frame_match"]["reusable"] is True
    assert payload["vision"]["source"] == "prefetched_reuse_v1"
    assert payload["vision"]["summary"] == "A snowy village menu is visible."
    assert payload["answer_text"] == "A snowy village menu is visible."


def test_run_pilot_turn_ignores_prefetched_vision_when_frame_differs(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    audio_meta = _write_audio_fixture(audio_path)

    prefetched_image = tmp_path / "prefetched_menu.png"
    live_image = tmp_path / "live_cave.png"
    Image.new("RGB", (320, 180), color=(210, 230, 255)).save(prefetched_image)
    Image.new("RGB", (320, 180), color=(20, 28, 40)).save(live_image)
    prefetched_capture_payload = {
        "capture_mode": "monitor",
        "monitor_index": 0,
        "region": None,
        "bbox": [0, 0, 320, 180],
        "width": 320,
        "height": 180,
        "screenshot_path": str(prefetched_image),
    }
    prefetched_vision_future: Future[dict[str, Any]] = Future()
    prefetched_vision_future.set_result(
        {
            "input_image": None,
            "vision_payload": {
                "provider": "fixture_vlm_prefetch",
                "summary": "A snowy village menu is visible.",
                "next_steps": [],
            },
            "visual_summary": "A snowy village menu is visible.",
            "error": None,
            "degraded_flags": [],
            "latency_sec": 0.25,
            "source": "live_capture_v1",
        }
    )

    class _LiveVisionClient:
        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
            _ = image_path, prompt
            return {
                "provider": "fixture_vlm_live",
                "summary": "A dark cave wall with visible ore.",
                "next_steps": [],
            }

    def _capture_live(*, output_path: Path, **_kwargs: Any) -> dict[str, Any]:
        output_path.write_bytes(live_image.read_bytes())
        return {
            "capture_mode": "monitor",
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
        return {"text": "What do you see on the screen?", "language": "en"}

    def _failing_hybrid(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hybrid should be skipped for direct visual observation requests")

    def _failing_grounded_reply(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("grounded reply should be skipped for direct visual observation requests")

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
        vlm_client=_LiveVisionClient(),
        grounded_reply_client=type("UnusedReply", (), {"generate_reply": staticmethod(_failing_grounded_reply)})(),
        playback_enabled=False,
        capture_func=_capture_live,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_failing_hybrid,
        tts_func=_fake_tts,
        pre_captured_screenshot_path=prefetched_image,
        pre_captured_capture_payload=prefetched_capture_payload,
        pre_captured_vision_future=prefetched_vision_future,
        expected_asr_language="en",
        now=datetime(2026, 3, 28, 2, 3, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "ok"
    assert payload["capture"]["prefetched_frame_match"]["reusable"] is False
    assert payload["vision"]["source"] == "live_capture_v1"
    assert payload["vision"]["summary"] == "A dark cave wall with visible ore."
    assert payload["answer_text"] == "A dark cave wall with visible ore."


def test_run_pilot_turn_cancels_unused_prefetched_vision_future(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    audio_meta = _write_audio_fixture(audio_path)

    prefetched_image = tmp_path / "prefetched_menu.png"
    live_image = tmp_path / "live_cave.png"
    Image.new("RGB", (320, 180), color=(210, 230, 255)).save(prefetched_image)
    Image.new("RGB", (320, 180), color=(20, 28, 40)).save(live_image)
    prefetched_capture_payload = {
        "capture_mode": "monitor",
        "monitor_index": 0,
        "region": None,
        "bbox": [0, 0, 320, 180],
        "width": 320,
        "height": 180,
        "screenshot_path": str(prefetched_image),
    }
    prefetched_vision_future: Future[dict[str, Any]] = Future()

    class _LiveVisionClient:
        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
            _ = image_path, prompt
            return {
                "provider": "fixture_vlm_live",
                "summary": "A dark cave wall with visible ore.",
                "next_steps": [],
            }

    def _capture_live(*, output_path: Path, **_kwargs: Any) -> dict[str, Any]:
        output_path.write_bytes(live_image.read_bytes())
        return {
            "capture_mode": "monitor",
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
        return {"text": "What do you see on the screen?", "language": "en"}

    def _failing_hybrid(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hybrid should be skipped for direct visual observation requests")

    def _failing_grounded_reply(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("grounded reply should be skipped for direct visual observation requests")

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
        vlm_client=_LiveVisionClient(),
        grounded_reply_client=type("UnusedReply", (), {"generate_reply": staticmethod(_failing_grounded_reply)})(),
        playback_enabled=False,
        capture_func=_capture_live,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_failing_hybrid,
        tts_func=_fake_tts,
        pre_captured_screenshot_path=prefetched_image,
        pre_captured_capture_payload=prefetched_capture_payload,
        pre_captured_vision_future=prefetched_vision_future,
        expected_asr_language="en",
        now=datetime(2026, 3, 28, 2, 3, 30, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "ok"
    assert payload["capture"]["prefetched_frame_match"]["reusable"] is False
    assert prefetched_vision_future.cancelled() is True


def test_run_pilot_turn_prefers_desktop_capture_backend_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    audio_meta = _write_audio_fixture(audio_path)
    image_path = tmp_path / "window_frame.png"
    Image.new("RGB", (320, 180), color=(30, 36, 52)).save(image_path)
    seen_capture_kwargs: list[dict[str, Any]] = []

    def _capture_live(*, output_path: Path, **kwargs: Any) -> dict[str, Any]:
        seen_capture_kwargs.append(dict(kwargs))
        output_path.write_bytes(image_path.read_bytes())
        return {
            "capture_mode": "window" if kwargs.get("window_handle") is not None else "monitor",
            "capture_backend": (
                "pillow_imagegrab_window"
                if kwargs.get("window_handle") is not None
                else "pillow_imagegrab_desktop"
            ),
            "monitor_index": kwargs.get("monitor_index"),
            "region": None,
            "bbox": [0, 0, 320, 180],
            "width": 320,
            "height": 180,
            "screenshot_path": str(output_path),
            "window_handle": kwargs.get("window_handle"),
            "window_title": kwargs.get("window_title"),
            "window_bounds": kwargs.get("window_bounds"),
        }

    def _fake_asr(
        *,
        voice_runtime_url: str,
        audio_path: Path,
        language: str | None = None,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = voice_runtime_url, audio_path, language, service_token
        return {"text": "What do you see?", "language": "en"}

    def _fake_hybrid(
        *,
        gateway_url: str,
        query: str,
        topk: int = 3,
        candidate_k: int = 6,
        max_entities_per_doc: int = 32,
        timeout_sec: float = 1.0,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = gateway_url, query, topk, candidate_k, max_entities_per_doc, timeout_sec, service_token
        return {"planner_status": "hybrid_merged", "degraded": False, "merged_results": []}

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
        return {
            "status": "ok",
            "mode": "fixture_tts",
            "chunk_count": 1,
            "events_count": 1,
            "audio_out_wav": None,
            "stream_events_jsonl": None,
            "playback_error": None,
            "completed_event": {"event": "completed"},
            "text": text,
        }

    monkeypatch.setattr(
        pilot_runtime,
        "find_best_atm10_window",
        lambda: {
            "hwnd": 4242,
            "window_title": "Minecraft 1.21.1 - ATM10",
            "process_name": "javaw.exe",
            "window_bounds": [0, 0, 320, 180],
            "foreground": True,
            "heuristic_score": 9,
        },
    )

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
        capture_func=_capture_live,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_fake_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="en",
        now=datetime(2026, 3, 28, 2, 2, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert seen_capture_kwargs == [{"monitor_index": 0, "region": None}]
    assert payload["capture"]["capture_mode"] == "monitor"
    assert payload["capture"]["capture_backend"] == "pillow_imagegrab_desktop"
    assert payload["capture"]["window_handle"] is None


def test_run_pilot_turn_falls_back_to_window_capture_when_desktop_capture_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    audio_meta = _write_audio_fixture(audio_path)
    image_path = tmp_path / "desktop_frame.png"
    Image.new("RGB", (320, 180), color=(42, 64, 92)).save(image_path)
    seen_capture_kwargs: list[dict[str, Any]] = []

    def _capture_live(*, output_path: Path, **kwargs: Any) -> dict[str, Any]:
        seen_capture_kwargs.append(dict(kwargs))
        if kwargs.get("window_handle") is None:
            raise RuntimeError("desktop capture returned stale surface")
        output_path.write_bytes(image_path.read_bytes())
        return {
            "capture_mode": "window",
            "capture_backend": "pillow_imagegrab_window",
            "monitor_index": kwargs.get("monitor_index"),
            "region": None,
            "bbox": [0, 0, 320, 180],
            "width": 320,
            "height": 180,
            "screenshot_path": str(output_path),
            "window_handle": kwargs.get("window_handle"),
            "window_title": kwargs.get("window_title"),
            "window_bounds": kwargs.get("window_bounds"),
        }

    def _fake_asr(
        *,
        voice_runtime_url: str,
        audio_path: Path,
        language: str | None = None,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = voice_runtime_url, audio_path, language, service_token
        return {"text": "What do you see?", "language": "en"}

    def _fake_hybrid(
        *,
        gateway_url: str,
        query: str,
        topk: int = 3,
        candidate_k: int = 6,
        max_entities_per_doc: int = 32,
        timeout_sec: float = 1.0,
        service_token: str | None = None,
    ) -> dict[str, Any]:
        _ = gateway_url, query, topk, candidate_k, max_entities_per_doc, timeout_sec, service_token
        return {"planner_status": "hybrid_merged", "degraded": False, "merged_results": []}

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
        return {
            "status": "ok",
            "mode": "fixture_tts",
            "chunk_count": 1,
            "events_count": 1,
            "audio_out_wav": None,
            "stream_events_jsonl": None,
            "playback_error": None,
            "completed_event": {"event": "completed"},
            "text": text,
        }

    monkeypatch.setattr(
        pilot_runtime,
        "find_best_atm10_window",
        lambda: {
            "hwnd": 4242,
            "window_title": "Minecraft 1.21.1 - ATM10",
            "process_name": "javaw.exe",
            "window_bounds": [0, 0, 320, 180],
            "foreground": True,
            "heuristic_score": 9,
        },
    )

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
        capture_func=_capture_live,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_fake_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="en",
        now=datetime(2026, 3, 28, 2, 3, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert len(seen_capture_kwargs) == 2
    assert seen_capture_kwargs[0] == {"monitor_index": 0, "region": None}
    assert seen_capture_kwargs[1]["window_handle"] == 4242
    assert payload["capture"]["capture_backend"] == "pillow_imagegrab_window"
    assert payload["capture"]["attempt_errors"] == [
        {"attempt": "desktop", "error": "desktop capture returned stale surface"}
    ]


def test_maybe_emit_pilot_return_event_requires_repeat(tmp_path: Path) -> None:
    runs_dir = tmp_path / "pilot-runtime"
    _write_json(
        runs_dir / "pilot_runtime_status_latest.json",
        {
            "schema_version": "pilot_runtime_status_v1",
            "status": "running",
            "paths": {"latest_status_json": str(runs_dir / "pilot_runtime_status_latest.json")},
        },
    )
    turn_json = runs_dir / "turns" / "20260322_120501-pilot-turn" / "pilot_turn.json"
    _write_json(turn_json, {"schema_version": "pilot_turn_v1"})
    turn_payload = {
        "status": "degraded",
        "degraded_flags": ["retrieval_only_fallback"],
        "transcript_quality": {"status": "ok"},
        "paths": {"turn_json": str(turn_json)},
    }

    loop_state, return_event = pilot_runtime._maybe_emit_pilot_return_event(
        runs_dir=runs_dir,
        turn_payload=turn_payload,
        loop_state=pilot_runtime.reset_return_loop_state(suppress_first_occurrence=True),
    )

    assert return_event is None
    assert loop_state["last_reason_code"] == "pilot_grounding_degraded"
    assert loop_state["occurrence_count"] == 1
    assert loop_state["emitted_count"] == 0
    assert not (runs_dir / "return" / "latest_return_event.json").exists()


def test_maybe_emit_pilot_return_event_reaches_safe_stop_after_repeat(tmp_path: Path) -> None:
    runs_dir = tmp_path / "pilot-runtime"
    _write_json(
        runs_dir / "pilot_runtime_status_latest.json",
        {
            "schema_version": "pilot_runtime_status_v1",
            "status": "running",
            "paths": {"latest_status_json": str(runs_dir / "pilot_runtime_status_latest.json")},
        },
    )
    turn_json = runs_dir / "turns" / "20260322_120501-pilot-turn" / "pilot_turn.json"
    _write_json(turn_json, {"schema_version": "pilot_turn_v1"})
    turn_payload = {
        "status": "degraded",
        "degraded_flags": ["retrieval_only_fallback"],
        "transcript_quality": {"status": "ok"},
        "paths": {"turn_json": str(turn_json)},
    }

    loop_state = pilot_runtime.reset_return_loop_state(suppress_first_occurrence=True)
    loop_state, first_event = pilot_runtime._maybe_emit_pilot_return_event(
        runs_dir=runs_dir,
        turn_payload=turn_payload,
        loop_state=loop_state,
    )
    loop_state, second_event = pilot_runtime._maybe_emit_pilot_return_event(
        runs_dir=runs_dir,
        turn_payload=turn_payload,
        loop_state=loop_state,
    )
    loop_state, third_event = pilot_runtime._maybe_emit_pilot_return_event(
        runs_dir=runs_dir,
        turn_payload=turn_payload,
        loop_state=loop_state,
    )

    assert first_event is None
    assert second_event is not None
    assert second_event["status"] == "open"
    assert second_event["reason_code"] == "pilot_grounding_degraded"
    assert third_event is not None
    assert third_event["status"] == "safe_stop"
    assert third_event["loop_count"] == 2
    assert loop_state["emitted_count"] == 2
    assert Path(runs_dir / "return" / "latest_return_event.json").is_file()
    log_lines = (runs_dir / "return" / "return_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 2


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
    assert payload["reply_mode"] == "low_signal_retry"
    assert payload["answer_language"] == "ru"
    assert payload["grounded_reply"]["provider"] == "low_signal_retry_v1"
    assert payload["answer_text"] == "Не расслышал, удерживай F8 пока говоришь и повтори коротко."
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
    assert payload["reply_mode"] == "low_signal_retry"
    assert payload["grounded_reply"]["provider"] == "low_signal_retry_v1"
    assert payload["answer_text"] == "Не расслышал, удерживай F8 пока говоришь и повтори коротко."
    assert "Продолжение следует" not in payload["answer_text"]


def test_run_pilot_turn_skips_asr_and_vision_for_too_short_audio(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    image_path = tmp_path / "image.png"
    audio_meta = _write_too_short_quiet_audio_fixture(audio_path)
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

    def _failing_asr(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("ASR should be skipped when audio is too short")

    class _UnusedVisionClient:
        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
            _ = image_path, prompt
            raise AssertionError("Vision should be skipped when audio is too short")

    def _failing_hybrid(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hybrid should be skipped for low-signal transcript")

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
        vlm_client=_UnusedVisionClient(),
        grounded_reply_client=DeterministicGroundedReplyStub(),
        playback_enabled=False,
        capture_func=_fake_capture,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_failing_asr,
        hybrid_query_func=_failing_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="ru",
        now=datetime(2026, 3, 28, 5, 0, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "degraded"
    assert payload["transcript_quality"]["status"] == "low_signal"
    assert "audio_too_short" in payload["transcript_quality"]["reason_codes"]
    assert payload["reply_mode"] == "low_signal_retry"
    assert payload["grounded_reply"]["provider"] == "low_signal_retry_v1"
    assert payload["answer_text"] == "Не расслышал, удерживай F8 пока говоришь и повтори коротко."
    assert payload["latency"]["asr_sec"] == 0.0
    assert payload["latency"]["vision_sec"] == 0.0
    assert payload["vision"]["source"] == "skipped_low_signal_v1"


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


def test_run_pilot_turn_uses_visual_observation_fast_path(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    image_path = tmp_path / "image.png"
    audio_meta = _write_audio_fixture(audio_path)
    _write_image_fixture(image_path)
    seen_prompts: list[str] = []
    seen_tts_texts: list[str] = []

    class _RussianVisionClient:
        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
            _ = image_path
            seen_prompts.append(prompt)
            return {
                "provider": "fixture_vlm",
                "summary": "A dark cave wall with visible ore.",
                "next_steps": [],
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
        return {"text": "Сейчас что-то видишь.", "language": "ru"}

    def _failing_hybrid(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hybrid should be skipped for direct visual observation requests")

    def _failing_grounded_reply(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("grounded reply should be skipped for direct visual observation requests")

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
        gateway_url="http://fixture.gateway",
        voice_runtime_url="http://fixture.voice",
        tts_runtime_url="http://fixture.tts",
        vlm_client=_RussianVisionClient(),
        grounded_reply_client=type("UnusedReply", (), {"generate_reply": staticmethod(_failing_grounded_reply)})(),
        playback_enabled=False,
        capture_func=_fake_capture,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_failing_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="ru",
        now=datetime(2026, 3, 28, 4, 20, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "ok"
    assert payload["degraded_flags"] == []
    assert payload["hybrid"]["planner_status"] == "skipped_visual_observation"
    assert payload["hybrid"]["degraded"] is False
    assert payload["reply_mode"] == "visual_observation_direct"
    assert payload["grounded_reply"]["provider"] == "visual_observation_direct_v1"
    assert payload["answer_text"] == "На экране: A dark cave wall with visible ore."
    assert seen_tts_texts == [payload["answer_text"]]
    assert seen_prompts and "Write summary in Russian." in seen_prompts[0]


def test_run_pilot_turn_uses_short_screen_grounded_fast_path(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    image_path = tmp_path / "image.png"
    audio_meta = _write_audio_fixture(audio_path)
    _write_image_fixture(image_path)
    seen_tts_texts: list[str] = []

    class _VisionClient:
        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
            _ = image_path, prompt
            return {
                "provider": "fixture_vlm",
                "summary": (
                    "Меню ATM10 и заснеженная деревня на фоне. "
                    "Внизу видны стандартные кнопки Minecraft."
                ),
                "next_steps": [],
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
        return {"text": "Это меню?", "language": "ru"}

    def _failing_hybrid(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hybrid should be skipped for short screen-grounded requests")

    def _failing_grounded_reply(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("grounded reply should be skipped for short screen-grounded requests")

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
        vlm_client=_VisionClient(),
        grounded_reply_client=type("UnusedReply", (), {"generate_reply": staticmethod(_failing_grounded_reply)})(),
        playback_enabled=False,
        capture_func=_fake_capture,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_failing_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="ru",
        now=datetime(2026, 3, 28, 4, 20, 15, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "ok"
    assert payload["hybrid"]["planner_status"] == "skipped_screen_grounded"
    assert payload["hybrid"]["warnings"] == ["screen_grounded_request"]
    assert payload["reply_mode"] == "screen_grounded_direct"
    assert payload["grounded_reply"]["provider"] == "screen_grounded_direct_v1"
    assert payload["answer_text"] == "Меню ATM10 и заснеженная деревня на фоне."
    assert seen_tts_texts == [payload["answer_text"]]


def test_run_pilot_turn_sanitizes_jsonish_vlm_summary_for_visual_observation(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    image_path = tmp_path / "image.png"
    audio_meta = _write_audio_fixture(audio_path)
    _write_image_fixture(image_path)
    seen_tts_texts: list[str] = []

    class _VisionClient:
        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
            _ = image_path, prompt
            return {
                "provider": "fixture_vlm",
                "summary": '```json\n{"summary":"A snowy village menu is visible!!!!!!!!!!"\n',
                "next_steps": [],
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
        return {"text": "Что ты сейчас видишь?", "language": "ru"}

    def _failing_hybrid(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hybrid should be skipped for direct visual observation requests")

    def _failing_grounded_reply(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("grounded reply should be skipped for direct visual observation requests")

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
        vlm_client=_VisionClient(),
        grounded_reply_client=type("UnusedReply", (), {"generate_reply": staticmethod(_failing_grounded_reply)})(),
        playback_enabled=False,
        capture_func=_fake_capture,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_failing_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="ru",
        now=datetime(2026, 3, 28, 4, 20, 25, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert payload["status"] == "ok"
    assert payload["reply_mode"] == "visual_observation_direct"
    assert payload["vision"]["summary"] == "A snowy village menu is visible!"
    assert payload["answer_text"] == "На экране: A snowy village menu is visible!"
    assert seen_tts_texts == [payload["answer_text"]]


def test_run_pilot_turn_runs_asr_and_vision_in_parallel(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    image_path = tmp_path / "image.png"
    audio_meta = _write_audio_fixture(audio_path)
    _write_image_fixture(image_path)
    asr_started = threading.Event()
    vision_started = threading.Event()
    overlap: dict[str, bool] = {"asr_saw_vision": False, "vision_saw_asr": False}

    class _VisionClient:
        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
            _ = image_path, prompt
            vision_started.set()
            overlap["vision_saw_asr"] = asr_started.wait(0.25)
            return {
                "provider": "fixture_vlm",
                "summary": "A snowy village menu is visible.",
                "next_steps": [],
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
            "raw_width": 320,
            "raw_height": 180,
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
        asr_started.set()
        overlap["asr_saw_vision"] = vision_started.wait(0.25)
        return {"text": "What do you see on the screen?", "language": "en"}

    def _failing_hybrid(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hybrid should be skipped for direct visual observation requests")

    def _failing_grounded_reply(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("grounded reply should be skipped for direct visual observation requests")

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
        vlm_client=_VisionClient(),
        grounded_reply_client=type("UnusedReply", (), {"generate_reply": staticmethod(_failing_grounded_reply)})(),
        playback_enabled=False,
        capture_func=_fake_capture,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_failing_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="en",
        now=datetime(2026, 3, 28, 4, 20, 30, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    assert overlap == {"asr_saw_vision": True, "vision_saw_asr": True}
    assert payload["status"] == "ok"
    assert payload["reply_mode"] == "visual_observation_direct"


def test_run_pilot_turn_prepares_downscaled_vision_input_for_vlm(tmp_path: Path) -> None:
    runtime_run_dir = tmp_path / "pilot-runtime"
    runtime_run_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "audio.wav"
    raw_image_path = tmp_path / "large_image.png"
    audio_meta = _write_audio_fixture(audio_path)
    Image.new("RGB", (2000, 1200), color=(90, 120, 150)).save(raw_image_path)
    seen_vlm_sizes: list[tuple[int, int]] = []
    seen_vlm_paths: list[Path] = []

    class _VisionClient:
        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
            _ = prompt
            seen_vlm_paths.append(Path(image_path))
            with Image.open(image_path) as image:
                seen_vlm_sizes.append((int(image.width), int(image.height)))
            return {
                "provider": "fixture_vlm",
                "summary": "A snowy village menu is visible.",
                "next_steps": [],
            }

    def _fake_capture(*, output_path: Path, **_kwargs: Any) -> dict[str, Any]:
        output_path.write_bytes(raw_image_path.read_bytes())
        return {
            "capture_mode": "monitor",
            "capture_backend": "fixture_desktop",
            "monitor_index": 0,
            "region": None,
            "bbox": [0, 0, 2000, 1200],
            "width": 2000,
            "height": 1200,
            "raw_width": 2000,
            "raw_height": 1200,
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
        return {"text": "What do you see on the screen?", "language": "en"}

    def _failing_hybrid(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("hybrid should be skipped for direct visual observation requests")

    def _failing_grounded_reply(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("grounded reply should be skipped for direct visual observation requests")

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
        vlm_client=_VisionClient(),
        grounded_reply_client=type("UnusedReply", (), {"generate_reply": staticmethod(_failing_grounded_reply)})(),
        playback_enabled=False,
        capture_func=_fake_capture,
        session_probe_func=_fake_session_probe,
        live_hud_state_func=_fake_live_hud_state,
        asr_func=_fake_asr,
        hybrid_query_func=_failing_hybrid,
        tts_func=_fake_tts,
        expected_asr_language="en",
        now=datetime(2026, 3, 28, 4, 21, 0, tzinfo=timezone.utc),
    )

    payload = result["turn_payload"]
    with Image.open(Path(payload["paths"]["screenshot_png"])) as screenshot_image:
        assert (int(screenshot_image.width), int(screenshot_image.height)) == (2000, 1200)
    assert seen_vlm_paths == [Path(payload["paths"]["vision_input_png"])]
    assert seen_vlm_sizes == [(pilot_runtime.DEFAULT_PILOT_VISION_MAX_EDGE, 768)]
    assert payload["vision"]["input_image"] == {
        "image_path": payload["paths"]["vision_input_png"],
        "source_path": payload["paths"]["screenshot_png"],
        "width": pilot_runtime.DEFAULT_PILOT_VISION_MAX_EDGE,
        "height": 768,
        "raw_width": 2000,
        "raw_height": 1200,
        "resized_from": [2000, 1200],
        "max_edge": pilot_runtime.DEFAULT_PILOT_VISION_MAX_EDGE,
    }


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
    assert latest_status_payload["host_profile"]["id"] == "ov_intel_core_ultra_local"
    assert latest_status_payload["effective_config"]["host_profile_id"] == "ov_intel_core_ultra_local"
    assert latest_status_payload["effective_config"]["vlm_provider"] == "openvino"
    assert latest_status_payload["effective_config"]["text_provider"] == "openvino"
    assert latest_status_payload["provider_init"]["vlm"]["status"] == "ok"
    assert latest_status_payload["provider_init"]["text"]["status"] == "ok"
    assert latest_status_payload["paths"]["run_dir"] == str(result["run_dir"])


def test_run_pilot_runtime_loop_marks_error_turn_as_degraded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transition_calls: list[dict[str, Any]] = []

    def _fake_build_provider(**kwargs: Any) -> Any:
        if kwargs.get("provider_kind") == "vlm":
            return DeterministicStubVLM()
        return DeterministicGroundedReplyStub()

    class _FakeStatusHandle:
        def __init__(self, **kwargs: Any) -> None:
            self.state = "idle"
            self.status = "running"
            self.degraded_services = list(kwargs.get("degraded_services", []))
            self.last_error = None

        def publish(self) -> None:
            return None

        def transition(self, **kwargs: Any) -> None:
            self.state = str(kwargs.get("state", self.state))
            self.status = str(kwargs.get("status", self.status))
            self.degraded_services = list(kwargs.get("degraded_services", self.degraded_services))
            self.last_error = kwargs.get("last_error", self.last_error)
            transition_calls.append(
                {
                    "state": self.state,
                    "status": self.status,
                    "degraded_services": list(self.degraded_services),
                    "last_error": self.last_error,
                }
            )

    class _FakeHotkey:
        def __init__(self, hotkey: str) -> None:
            _ = hotkey
            self._events = iter(["down", "up", KeyboardInterrupt()])

        def poll_transition(self) -> str | None:
            event = next(self._events)
            if isinstance(event, BaseException):
                raise event
            return event

    class _FakeRecorder:
        def __init__(self, sample_rate: int, preferred_input_device_index: int | None) -> None:
            _ = sample_rate, preferred_input_device_index

        def start(self) -> None:
            return None

        def stop_to_wav(self, output_path: Path) -> dict[str, Any]:
            return _write_audio_fixture(output_path)

        def capture_diagnostics(self, *, duration_sec: float, total_frames: int) -> dict[str, Any]:
            return {
                "callback_count": 1,
                "callback_frames": int(total_frames),
                "total_frames": int(total_frames),
                "overflow_count": 0,
                "first_callback_offset_sec": 0.0,
                "last_callback_offset_sec": round(float(duration_sec), 6),
                "duration_sec": round(float(duration_sec), 6),
            }

        def discard(self) -> None:
            return None

    def _fake_run_pilot_turn(**kwargs: Any) -> dict[str, Any]:
        runtime_run_dir = kwargs["runtime_run_dir"]
        turn_dir = runtime_run_dir / "turns" / "20260323_210001-pilot-turn"
        turn_dir.mkdir(parents=True, exist_ok=True)
        turn_json_path = turn_dir / "pilot_turn.json"
        turn_json_path.write_text("{}", encoding="utf-8")
        return {
            "turn_payload": {
                "turn_id": turn_dir.name,
                "status": "error",
                "error": "turn failed",
                "degraded_services": ["gateway"],
                "paths": {"turn_json": str(turn_json_path)},
            }
        }

    monkeypatch.setattr(pilot_runtime, "_build_provider", _fake_build_provider)
    monkeypatch.setattr(pilot_runtime, "PilotRuntimeStatusHandle", _FakeStatusHandle)
    monkeypatch.setattr(pilot_runtime, "PollingHotkey", _FakeHotkey)
    monkeypatch.setattr(pilot_runtime, "PushToTalkRecorder", _FakeRecorder)
    monkeypatch.setattr(pilot_runtime, "run_pilot_turn", _fake_run_pilot_turn)

    result = pilot_runtime.run_pilot_runtime_loop(
        runs_dir=tmp_path / "pilot-runtime",
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

    assert result["ok"] is True
    assert any(call["status"] == "degraded" for call in transition_calls)
    degraded_call = next(call for call in transition_calls if call["status"] == "degraded")
    assert degraded_call["last_error"] == "turn failed"
    assert "gateway" in degraded_call["degraded_services"]


def test_run_pilot_runtime_loop_uses_silence_fallback_when_no_audio_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_audio_meta: dict[str, Any] = {}

    def _fake_build_provider(**kwargs: Any) -> Any:
        if kwargs.get("provider_kind") == "vlm":
            return DeterministicStubVLM()
        return DeterministicGroundedReplyStub()

    class _FakeStatusHandle:
        def __init__(self, **kwargs: Any) -> None:
            self.state = "idle"
            self.status = "running"
            self.degraded_services = list(kwargs.get("degraded_services", []))
            self.last_error = None

        def publish(self) -> None:
            return None

        def transition(self, **kwargs: Any) -> None:
            self.state = str(kwargs.get("state", self.state))
            self.status = str(kwargs.get("status", self.status))
            self.degraded_services = list(kwargs.get("degraded_services", self.degraded_services))
            self.last_error = kwargs.get("last_error", self.last_error)

    class _FakeHotkey:
        def __init__(self, hotkey: str) -> None:
            _ = hotkey
            self._events = iter(["down", "up", KeyboardInterrupt()])

        def poll_transition(self) -> str | None:
            event = next(self._events)
            if isinstance(event, BaseException):
                raise event
            return event

    class _FakeRecorder:
        def __init__(self, sample_rate: int, preferred_input_device_index: int | None) -> None:
            _ = sample_rate, preferred_input_device_index
            self._input_device_index = 1
            self._input_device_name = "Mic Array"
            self._started_at = 10.0

        def start(self) -> None:
            return None

        def stop_to_wav(self, output_path: Path) -> dict[str, Any]:
            _ = output_path
            raise RuntimeError("No audio frames were captured during push-to-talk.")

        def capture_diagnostics(self, *, duration_sec: float, total_frames: int) -> dict[str, Any]:
            return {
                "callback_count": 0,
                "callback_frames": 0,
                "total_frames": int(total_frames),
                "overflow_count": 0,
                "first_callback_offset_sec": None,
                "last_callback_offset_sec": None,
                "duration_sec": round(float(duration_sec), 6),
            }

        def discard(self) -> None:
            return None

    def _fake_run_pilot_turn(**kwargs: Any) -> dict[str, Any]:
        runtime_run_dir = kwargs["runtime_run_dir"]
        captured_audio_meta.update(dict(kwargs["audio_input_meta"]))
        turn_dir = runtime_run_dir / "turns" / "20260323_220001-pilot-turn"
        turn_dir.mkdir(parents=True, exist_ok=True)
        turn_json_path = turn_dir / "pilot_turn.json"
        turn_json_path.write_text("{}", encoding="utf-8")
        return {
            "turn_payload": {
                "turn_id": turn_dir.name,
                "status": "ok",
                "error": None,
                "degraded_services": [],
                "paths": {"turn_json": str(turn_json_path)},
            }
        }

    monkeypatch.setattr(pilot_runtime, "_build_provider", _fake_build_provider)
    monkeypatch.setattr(pilot_runtime, "PilotRuntimeStatusHandle", _FakeStatusHandle)
    monkeypatch.setattr(pilot_runtime, "PollingHotkey", _FakeHotkey)
    monkeypatch.setattr(pilot_runtime, "PushToTalkRecorder", _FakeRecorder)
    monkeypatch.setattr(pilot_runtime, "run_pilot_turn", _fake_run_pilot_turn)

    result = pilot_runtime.run_pilot_runtime_loop(
        runs_dir=tmp_path / "pilot-runtime",
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
        now=datetime(2026, 3, 23, 22, 0, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    assert captured_audio_meta["mode"] == "push_to_talk_silence_fallback"
    assert "capture_error" in captured_audio_meta
    assert Path(captured_audio_meta["audio_path"]).is_file()


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
    assert result["run_payload"]["host_profile"]["id"] == "ov_intel_core_ultra_local"
    provider_init = result["run_payload"]["provider_init"]
    assert provider_init["vlm"]["warmup"]["requested"] is True
    assert provider_init["vlm"]["warmup"]["ok"] is True
    assert provider_init["text"]["warmup"]["requested"] is True
    assert provider_init["text"]["warmup"]["ok"] is True

    latest_status_payload = json.loads((runs_dir / "pilot_runtime_status_latest.json").read_text(encoding="utf-8"))
    assert latest_status_payload["provider_init"]["vlm"]["warmup"]["ok"] is True
    assert latest_status_payload["provider_init"]["text"]["warmup"]["ok"] is True
