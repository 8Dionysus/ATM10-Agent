from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.grounded_reply_openvino import DeterministicGroundedReplyStub
from src.agent_core.io_voice import write_wav_pcm16
from src.agent_core.vlm_stub import DeterministicStubVLM
from scripts.pilot_runtime_loop import (
    PilotRuntimeStatusHandle,
    _create_run_dir,
    _write_json,
    run_pilot_turn,
)

SMOKE_SUMMARY_SCHEMA = "pilot_turn_smoke_summary_v1"


def _write_placeholder_audio(path: Path, *, sample_rate: int = 16000) -> dict[str, Any]:
    duration_sec = 0.5
    timeline = np.linspace(0.0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    waveform = (0.15 * np.sin(2.0 * np.pi * 440.0 * timeline)).astype(np.float32)
    write_wav_pcm16(path=path, waveform=waveform, sample_rate=sample_rate)
    return {
        "mode": "fixture_audio",
        "sample_rate": sample_rate,
        "duration_sec": duration_sec,
        "num_samples": int(waveform.shape[0]),
        "audio_path": str(path),
    }


def _write_placeholder_image(path: Path) -> None:
    image = Image.new("RGB", (640, 360), color=(23, 28, 31))
    draw = ImageDraw.Draw(image)
    draw.rectangle((32, 32, 608, 328), outline=(122, 196, 96), width=4)
    draw.text((48, 56), "ATM10 Pilot Smoke", fill=(245, 242, 214))
    draw.text((48, 96), "Quest book nearby", fill=(245, 242, 214))
    draw.text((48, 136), "Mekanism steel progression visible", fill=(245, 242, 214))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def run_pilot_turn_smoke(
    *,
    runs_dir: Path = Path("runs") / "pilot-runtime-smoke",
    summary_json: Path | None = None,
    transcript: str = "What is the next progression step on this screen?",
    audio_in: Path | None = None,
    image_in: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    effective_now = now or datetime.now(timezone.utc)
    runtime_run_dir = _create_run_dir(runs_dir, effective_now)
    smoke_audio_path = runtime_run_dir / "fixture_audio.wav"
    smoke_image_path = runtime_run_dir / "fixture_image.png"
    latest_status_path = runs_dir / "pilot_runtime_status_latest.json"

    if audio_in is None:
        audio_meta = _write_placeholder_audio(smoke_audio_path)
        audio_input_path = smoke_audio_path
    else:
        audio_input_path = Path(audio_in)
        audio_meta = {
            "mode": "fixture_audio",
            "audio_path": str(audio_input_path),
        }
    if image_in is None:
        _write_placeholder_image(smoke_image_path)
        image_input_path = smoke_image_path
    else:
        image_input_path = Path(image_in)

    def _fake_capture(*, output_path: Path, **_kwargs: Any) -> dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_input_path.read_bytes())
        return {
            "capture_mode": "fixture",
            "monitor_index": None,
            "region": None,
            "bbox": None,
            "width": 640,
            "height": 360,
            "screenshot_path": str(output_path),
        }

    def _fake_asr(*, voice_runtime_url: str, audio_path: Path, service_token: str | None = None) -> dict[str, Any]:
        _ = voice_runtime_url, audio_path, service_token
        return {
            "timestamp_utc": effective_now.isoformat(),
            "audio_path": str(audio_input_path),
            "text": transcript,
            "language": "en",
        }

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
                "results_count": 2,
                "retrieval_results_count": 2,
                "kag_results_count": 1,
            },
            "hybrid_results_payload": {
                "planner_mode": "retrieval_first_kag_expansion",
                "planner_status": "hybrid_merged",
                "degraded": False,
                "warnings": [],
                "results_count": 2,
                "retrieval_results_count": 2,
                "kag_results_count": 1,
                "merged_results": [
                    {
                        "id": "quest_book",
                        "title": "Quest Book Progression",
                        "planner_source": "retrieval_and_kag",
                        "matched_entities": ["mekanism", "steel"],
                        "citation": {"id": "quest_book", "source": "fixture", "path": "tests/fixtures/retrieval_docs_sample.jsonl"},
                    },
                    {
                        "id": "mekanism_steel",
                        "title": "Mekanism Steel Setup",
                        "planner_source": "retrieval_only",
                        "matched_entities": ["steel"],
                        "citation": {"id": "mekanism_steel", "source": "fixture", "path": "tests/fixtures/retrieval_docs_sample.jsonl"},
                    },
                ],
            },
            "hybrid_results_json": None,
            "hybrid_run_dir": None,
        }

    def _fake_session_probe(
        *,
        capture_target_kind: str,
        capture_bbox: list[int] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        _ = capture_bbox
        return {
            "schema_version": "atm10_session_probe_v1",
            "checked_at_utc": effective_now.isoformat() if now is None else now.isoformat(),
            "status": "ok",
            "window_found": True,
            "process_name": "javaw.exe",
            "window_title": "Minecraft 1.21.1 - ATM10",
            "foreground": True,
            "window_bounds": {"left": 0, "top": 0, "right": 640, "bottom": 360, "width": 640, "height": 360},
            "capture_target_kind": capture_target_kind,
            "capture_bbox": [0, 0, 640, 360],
            "capture_intersects_window": True,
            "atm10_probable": True,
            "reason_codes": [],
        }

    def _fake_live_hud_state(
        *,
        screenshot_path: Path,
        hook_json: Path | None = None,
        tesseract_bin: str = "tesseract",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        _ = hook_json, tesseract_bin, now
        return {
            "schema_version": "live_hud_state_v1",
            "checked_at_utc": effective_now.isoformat(),
            "status": "ok",
            "screenshot_path": str(screenshot_path),
            "sources": {
                "screenshot": {"status": "ok", "path": str(screenshot_path), "detail": None},
                "mod_hook": {"status": "not_configured", "path": None, "detail": None},
                "ocr": {"status": "ok", "path": str(screenshot_path), "detail": None, "line_count": 2},
            },
            "hud_lines": ["Quest book nearby", "Mekanism steel progression visible"],
            "quest_updates": [{"id": "quest_book", "text": "Open quest book", "status": "active"}],
            "player_state": {"dimension": "minecraft:overworld"},
            "context_tags": ["hud", "quest"],
            "text_preview": "Quest book nearby Mekanism steel progression visible",
            "hud_line_count": 2,
            "quest_update_count": 1,
            "has_player_state": True,
            "reason_codes": ["mod_hook_not_configured"],
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
        output_path = turn_dir / "tts_audio_out.wav"
        timeline = np.linspace(0.0, 0.3, int(16000 * 0.3), endpoint=False)
        waveform = (0.1 * np.sin(2.0 * np.pi * 330.0 * timeline)).astype(np.float32)
        write_wav_pcm16(path=output_path, waveform=waveform, sample_rate=16000)
        payload = {
            "status": "ok",
            "mode": "stub",
            "streaming_mode": "fixture",
            "fallback_used": False,
            "fallback_reason": None,
            "chunk_count": 1,
            "events_count": 1,
            "audio_out_wav": str(output_path),
            "stream_events_jsonl": None,
            "playback_error": None,
            "completed_event": {"event": "completed"},
            "text": text,
        }
        _write_json(turn_dir / "tts_response.json", payload)
        return payload

    turn_result = run_pilot_turn(
        runtime_run_dir=runtime_run_dir,
        audio_input_path=audio_input_path,
        audio_input_meta=audio_meta,
        hotkey="F8",
        capture_monitor=None,
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
        now=effective_now,
    )
    turn_payload = turn_result["turn_payload"]

    status_handle = PilotRuntimeStatusHandle(
        runtime_run_dir=runtime_run_dir,
        latest_status_path=latest_status_path,
        hotkey="F8",
        gateway_url="http://fixture.gateway",
        voice_runtime_url="http://fixture.voice",
        tts_runtime_url="http://fixture.tts",
        input_device_index=None,
        capture_monitor=None,
        capture_region=None,
        vlm_model_dir=Path("stub-vlm"),
        text_model_dir=Path("stub-text"),
        vlm_provider="stub",
        text_provider="stub",
        provider_init={
            "vlm": {"status": "ok", "provider": "stub"},
            "text": {"status": "ok", "provider": "stub"},
        },
        degraded_services=list(turn_payload.get("degraded_services", [])),
        last_turn_payload=turn_payload,
    )
    status_handle.publish()

    summary_payload: dict[str, Any] = {
        "schema_version": SMOKE_SUMMARY_SCHEMA,
        "status": "ok" if turn_result["ok"] else "error",
        "timestamp_utc": effective_now.astimezone(timezone.utc).isoformat(),
        "turn_id": turn_payload.get("turn_id"),
        "turn_status": turn_payload.get("status"),
        "degraded_flags": turn_payload.get("degraded_flags", []),
        "answer_text": turn_payload.get("answer_text"),
        "paths": {
            "runtime_run_dir": str(runtime_run_dir),
            "turn_json": turn_payload.get("paths", {}).get("turn_json"),
            "latest_status_json": str(latest_status_path),
        },
    }
    if summary_json is not None:
        _write_json(summary_json, summary_payload)
    return {
        "ok": turn_result["ok"],
        "runtime_run_dir": runtime_run_dir,
        "turn_payload": turn_payload,
        "summary_payload": summary_payload,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pilot turn smoke: fixture audio/image -> pilot_turn_v1 artifact.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs") / "pilot-runtime-smoke", help="Smoke artifact root.")
    parser.add_argument("--summary-json", type=Path, default=None, help="Optional summary JSON output path.")
    parser.add_argument("--transcript", type=str, default="What is the next progression step on this screen?")
    parser.add_argument("--audio-in", type=Path, default=None, help="Optional fixture WAV input.")
    parser.add_argument("--image-in", type=Path, default=None, help="Optional fixture screenshot input.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_pilot_turn_smoke(
        runs_dir=args.runs_dir,
        summary_json=args.summary_json,
        transcript=args.transcript,
        audio_in=args.audio_in,
        image_in=args.image_in,
    )
    print(f"[pilot_turn_smoke] runtime_run_dir: {result['runtime_run_dir']}")
    print(f"[pilot_turn_smoke] turn_json: {result['turn_payload']['paths']['turn_json']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
