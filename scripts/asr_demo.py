from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.io_voice import (
    DEFAULT_QWEN3_ASR_MODEL,
    QwenASRClient,
    VoiceRuntimeUnavailableError,
    record_audio_to_wav,
)


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-asr-demo")
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


def _prepare_audio_input(
    *,
    audio_in: Path | None,
    record_seconds: float,
    sample_rate: int,
    run_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    has_audio_file = audio_in is not None
    has_record = record_seconds > 0
    if has_audio_file == has_record:
        raise ValueError("Choose exactly one input mode: either --audio-in or --record-seconds > 0.")

    if has_record:
        recorded_path = run_dir / "input_recorded.wav"
        meta = record_audio_to_wav(
            output_path=recorded_path,
            seconds=record_seconds,
            sample_rate=sample_rate,
        )
        return recorded_path, meta

    assert audio_in is not None
    if not audio_in.exists():
        raise FileNotFoundError(f"--audio-in file does not exist: {audio_in}")
    copied_path = run_dir / f"input_from_file{audio_in.suffix.lower() or '.wav'}"
    shutil.copyfile(audio_in, copied_path)
    return copied_path, {
        "mode": "audio_file",
        "source_path": str(audio_in),
        "audio_path": str(copied_path),
    }


def run_asr_demo(
    *,
    audio_in: Path | None = None,
    record_seconds: float = 0.0,
    sample_rate: int = 16000,
    model_id: str = DEFAULT_QWEN3_ASR_MODEL,
    device_map: str = "auto",
    dtype: str = "auto",
    context: str = "",
    language: str | None = None,
    max_new_tokens: int = 512,
    runs_dir: Path = Path("runs"),
    allow_archived_qwen_asr: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    result_json_path = run_dir / "transcription.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "qwen3_asr_demo_archived",
        "status": "started",
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "transcription_json": str(result_json_path),
        },
        "model": {
            "id": model_id,
            "device_map": device_map,
            "dtype": dtype,
            "max_new_tokens": max_new_tokens,
        },
        "request": {
            "audio_in": str(audio_in) if audio_in is not None else None,
            "record_seconds": record_seconds,
            "sample_rate": sample_rate,
            "context": context,
            "language": language,
        },
        "archived": {
            "qwen3_asr": True,
            "enabled": allow_archived_qwen_asr,
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        if not allow_archived_qwen_asr:
            raise RuntimeError(
                "qwen3-asr path is archived. Use --allow-archived-qwen-asr to run this demo."
            )
        audio_path, input_meta = _prepare_audio_input(
            audio_in=audio_in,
            record_seconds=record_seconds,
            sample_rate=sample_rate,
            run_dir=run_dir,
        )
        client = QwenASRClient.from_pretrained(
            model_id=model_id,
            device_map=device_map,
            dtype=dtype,
            max_new_tokens=max_new_tokens,
        )
        transcription = client.transcribe_path(
            audio_path=audio_path,
            context=context,
            language=language,
        )
        result_payload = {
            "audio_path": str(audio_path),
            "text": transcription["text"],
            "language": transcription["language"],
            "input": input_meta,
        }
        _write_json(result_json_path, result_payload)
        run_payload["status"] = "ok"
        run_payload["input"] = input_meta
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
        elif isinstance(exc, RuntimeError) and "archived" in str(exc):
            run_payload["error_code"] = "archived_backend_disabled"
        elif isinstance(exc, RuntimeError) and "No audio input device" in str(exc):
            run_payload["error_code"] = "audio_input_device_unavailable"
        else:
            run_payload["error_code"] = "asr_demo_failed"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "result_payload": None,
            "ok": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archived Qwen3 ASR demo: audio file or microphone -> text artifact."
    )
    parser.add_argument(
        "--audio-in",
        type=Path,
        default=None,
        help="Path to input audio file. Mutually exclusive with --record-seconds.",
    )
    parser.add_argument(
        "--record-seconds",
        type=float,
        default=0.0,
        help="Record from microphone for N seconds. Mutually exclusive with --audio-in.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="Recording sample rate for --record-seconds mode (default: 16000).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_QWEN3_ASR_MODEL,
        help=f"ASR model id/path (default: {DEFAULT_QWEN3_ASR_MODEL}).",
    )
    parser.add_argument("--device-map", type=str, default="auto", help="Model device_map (default: auto).")
    parser.add_argument(
        "--dtype",
        type=str,
        default="auto",
        choices=("auto", "float16", "bfloat16", "float32"),
        help="Torch dtype (default: auto).",
    )
    parser.add_argument("--context", type=str, default="", help="Optional ASR system context.")
    parser.add_argument("--language", type=str, default=None, help="Optional forced language.")
    parser.add_argument("--max-new-tokens", type=int, default=512, help="ASR max_new_tokens (default: 512).")
    parser.add_argument(
        "--allow-archived-qwen-asr",
        action="store_true",
        help="Required to run archived qwen3-asr demo path.",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_asr_demo(
        audio_in=args.audio_in,
        record_seconds=args.record_seconds,
        sample_rate=args.sample_rate,
        model_id=args.model,
        device_map=args.device_map,
        dtype=args.dtype,
        context=args.context,
        language=args.language,
        max_new_tokens=args.max_new_tokens,
        runs_dir=args.runs_dir,
        allow_archived_qwen_asr=args.allow_archived_qwen_asr,
    )
    run_dir = result["run_dir"]
    print(f"[asr_demo] run_dir: {run_dir}")
    print(f"[asr_demo] run_json: {run_dir / 'run.json'}")
    print(f"[asr_demo] transcription_json: {run_dir / 'transcription.json'}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
