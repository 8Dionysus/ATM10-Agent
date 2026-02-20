from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.io_voice import (
    DEFAULT_QWEN3_TTS_MODEL,
    QwenTTSClient,
    VoiceRuntimeUnavailableError,
    play_audio,
    write_wav_pcm16,
)


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-tts-demo")
    run_dir = runs_dir / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    suffix = 1
    while True:
        candidate = runs_dir / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_tts_demo(
    *,
    text: str,
    model_id: str = DEFAULT_QWEN3_TTS_MODEL,
    speaker: str | None = None,
    language: str = "Auto",
    instruct: str | None = None,
    device_map: str = "auto",
    dtype: str = "auto",
    play: bool = False,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    result_json_path = run_dir / "tts_result.json"
    audio_path = run_dir / "audio_out.wav"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "qwen3_tts_demo",
        "status": "started",
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "tts_result_json": str(result_json_path),
            "audio_out_wav": str(audio_path),
        },
        "model": {
            "id": model_id,
            "device_map": device_map,
            "dtype": dtype,
        },
        "request": {
            "text": text,
            "speaker": speaker,
            "language": language,
            "instruct": instruct,
            "play": play,
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        if not text.strip():
            raise ValueError("--text must not be empty.")

        client = QwenTTSClient.from_pretrained(
            model_id=model_id,
            device_map=device_map,
            dtype=dtype,
        )
        selected_speaker = client.resolve_speaker(speaker)
        waveform, sample_rate = client.synthesize_custom_voice(
            text=text,
            speaker=selected_speaker,
            language=language,
            instruct=instruct,
        )
        write_wav_pcm16(path=audio_path, waveform=waveform, sample_rate=sample_rate)
        if play:
            play_audio(waveform=waveform, sample_rate=sample_rate)

        result_payload = {
            "text": text,
            "speaker_selected": selected_speaker,
            "language": language,
            "instruct": instruct,
            "sample_rate": sample_rate,
            "num_samples": int(waveform.shape[0]),
            "audio_out_wav": str(audio_path),
            "playback_attempted": play,
        }
        _write_json(result_json_path, result_payload)
        run_payload["status"] = "ok"
        run_payload["speaker_selected"] = selected_speaker
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "result_payload": result_payload,
            "ok": True,
        }
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, VoiceRuntimeUnavailableError):
            run_payload["error_code"] = "voice_runtime_missing_dependency"
        else:
            run_payload["error_code"] = "tts_demo_failed"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "result_payload": None,
            "ok": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Qwen3 TTS demo: text -> wav artifact.")
    parser.add_argument("--text", type=str, required=True, help="Input text to synthesize.")
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_QWEN3_TTS_MODEL,
        help=f"TTS model id/path (default: {DEFAULT_QWEN3_TTS_MODEL}).",
    )
    parser.add_argument("--speaker", type=str, default=None, help="Speaker id/name for custom voice model.")
    parser.add_argument("--language", type=str, default="Auto", help="Language (default: Auto).")
    parser.add_argument("--instruct", type=str, default=None, help="Optional style instruction text.")
    parser.add_argument("--device-map", type=str, default="auto", help="Model device_map (default: auto).")
    parser.add_argument(
        "--dtype",
        type=str,
        default="auto",
        choices=("auto", "float16", "bfloat16", "float32"),
        help="Torch dtype (default: auto).",
    )
    parser.add_argument("--play", action="store_true", help="Play generated audio after saving WAV.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_tts_demo(
        text=args.text,
        model_id=args.model,
        speaker=args.speaker,
        language=args.language,
        instruct=args.instruct,
        device_map=args.device_map,
        dtype=args.dtype,
        play=args.play,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[tts_demo] run_dir: {run_dir}")
    print(f"[tts_demo] run_json: {run_dir / 'run.json'}")
    print(f"[tts_demo] tts_result_json: {run_dir / 'tts_result.json'}")
    print(f"[tts_demo] audio_out_wav: {run_dir / 'audio_out.wav'}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
