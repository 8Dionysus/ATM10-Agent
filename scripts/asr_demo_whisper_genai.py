from __future__ import annotations

import argparse
import json
import shutil
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.io_voice import VoiceRuntimeUnavailableError, record_audio_to_wav


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-asr-whisper-genai")
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


def _linear_resample(waveform: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return waveform.astype(np.float32, copy=False)
    if src_sr <= 0 or dst_sr <= 0:
        raise ValueError("Sample rates must be > 0 for resampling.")
    if waveform.size == 0:
        return np.zeros(0, dtype=np.float32)

    duration_sec = waveform.shape[0] / float(src_sr)
    target_size = max(1, int(round(duration_sec * float(dst_sr))))
    x_old = np.linspace(0.0, duration_sec, num=waveform.shape[0], endpoint=False, dtype=np.float64)
    x_new = np.linspace(0.0, duration_sec, num=target_size, endpoint=False, dtype=np.float64)
    resampled = np.interp(x_new, x_old, waveform.astype(np.float64))
    return resampled.astype(np.float32)


def _read_wav_mono_f32(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        num_channels = int(wav_file.getnchannels())
        sample_width = int(wav_file.getsampwidth())
        sample_rate = int(wav_file.getframerate())
        num_frames = int(wav_file.getnframes())
        raw_bytes = wav_file.readframes(num_frames)

    if sample_width == 1:
        data_u8 = np.frombuffer(raw_bytes, dtype=np.uint8)
        data = ((data_u8.astype(np.float32) - 128.0) / 128.0).astype(np.float32)
    elif sample_width == 2:
        data_i16 = np.frombuffer(raw_bytes, dtype=np.int16)
        data = (data_i16.astype(np.float32) / 32768.0).astype(np.float32)
    elif sample_width == 4:
        data_i32 = np.frombuffer(raw_bytes, dtype=np.int32)
        data = (data_i32.astype(np.float32) / 2147483648.0).astype(np.float32)
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes.")

    if num_channels > 1:
        if data.size % num_channels != 0:
            raise ValueError("Corrupted WAV payload: sample count is not divisible by channel count.")
        data = data.reshape(-1, num_channels).mean(axis=1).astype(np.float32)

    return np.clip(data, -1.0, 1.0), sample_rate


def _load_audio_mono_16k(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".wav":
        wav, sr = _read_wav_mono_f32(path)
    else:
        try:
            import librosa  # pragma: no cover - optional dependency
        except Exception as exc:  # pragma: no cover - optional dependency
            raise VoiceRuntimeUnavailableError(
                "Non-WAV input requires librosa. Install dependency: librosa."
            ) from exc
        wav, sr = librosa.load(str(path), sr=None, mono=True)
        wav = np.asarray(wav, dtype=np.float32).reshape(-1)
        sr = int(sr)

    wav_16k = _linear_resample(wav, src_sr=sr, dst_sr=16000)
    return np.clip(wav_16k, -1.0, 1.0).astype(np.float32)


def _normalize_language_tag(language: str | None) -> str | None:
    if language is None:
        return None
    normalized = language.strip()
    if not normalized:
        return None
    if normalized.startswith("<|") and normalized.endswith("|>"):
        return normalized
    return f"<|{normalized.lower()}|>"


def _load_openvino_genai() -> Any:
    try:
        import openvino_genai as ov_genai
    except Exception as exc:  # pragma: no cover - dependency presence
        raise VoiceRuntimeUnavailableError(
            "OpenVINO GenAI runtime is not installed. Install dependency: openvino-genai."
        ) from exc
    return ov_genai


def _extract_result_payload(result: Any) -> dict[str, Any]:
    text_value = ""
    texts = getattr(result, "texts", None)
    if isinstance(texts, (list, tuple)) and texts:
        text_value = str(texts[0])
    else:
        text_attr = getattr(result, "text", None)
        if text_attr is not None:
            text_value = str(text_attr)
        else:
            text_value = str(result)

    chunks_payload: list[dict[str, Any]] = []
    for chunk in list(getattr(result, "chunks", []) or []):
        chunks_payload.append(
            {
                "start_ts": float(getattr(chunk, "start_ts", 0.0)),
                "end_ts": float(getattr(chunk, "end_ts", 0.0)),
                "text": str(getattr(chunk, "text", "")),
            }
        )

    words_payload: list[dict[str, Any]] = []
    for word in list(getattr(result, "words", []) or []):
        text = getattr(word, "word", None)
        if text is None:
            text = getattr(word, "text", "")
        words_payload.append(
            {
                "start_ts": float(getattr(word, "start_ts", 0.0)),
                "end_ts": float(getattr(word, "end_ts", 0.0)),
                "word": str(text),
            }
        )

    return {
        "text": text_value,
        "language": str(getattr(result, "language", "")),
        "chunks": chunks_payload,
        "words": words_payload,
    }


def run_asr_demo_whisper_genai(
    *,
    model_dir: Path,
    audio_in: Path | None = None,
    record_seconds: float = 0.0,
    sample_rate: int = 16000,
    device: str = "NPU",
    language: str | None = None,
    task: str = "transcribe",
    max_new_tokens: int = 128,
    return_timestamps: bool = False,
    word_timestamps: bool = False,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    result_json_path = run_dir / "transcription.json"

    pipeline_kwargs: dict[str, Any] = {}
    normalized_device = device.upper()
    if normalized_device == "NPU":
        pipeline_kwargs["STATIC_PIPELINE"] = True
    if word_timestamps:
        pipeline_kwargs["word_timestamps"] = True

    normalized_language = _normalize_language_tag(language)
    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "whisper_genai_asr_demo",
        "status": "started",
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "transcription_json": str(result_json_path),
        },
        "runtime": {
            "model_dir": str(model_dir),
            "device": normalized_device,
            "pipeline_kwargs": pipeline_kwargs,
            "max_new_tokens": max_new_tokens,
            "task": task,
            "language": normalized_language,
            "return_timestamps": return_timestamps,
            "word_timestamps": word_timestamps,
        },
        "request": {
            "audio_in": str(audio_in) if audio_in is not None else None,
            "record_seconds": record_seconds,
            "sample_rate": sample_rate,
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        if not model_dir.exists():
            raise FileNotFoundError(f"Whisper model directory does not exist: {model_dir}")

        audio_path, input_meta = _prepare_audio_input(
            audio_in=audio_in,
            record_seconds=record_seconds,
            sample_rate=sample_rate,
            run_dir=run_dir,
        )
        raw_speech = _load_audio_mono_16k(audio_path)

        ov_genai = _load_openvino_genai()
        pipe = ov_genai.WhisperPipeline(str(model_dir), normalized_device, **pipeline_kwargs)

        generate_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "task": task,
        }
        if normalized_language is not None:
            generate_kwargs["language"] = normalized_language
        if return_timestamps:
            generate_kwargs["return_timestamps"] = True
        if word_timestamps:
            generate_kwargs["word_timestamps"] = True

        result = pipe.generate(raw_speech.tolist(), **generate_kwargs)
        result_payload = _extract_result_payload(result)
        result_payload["audio_path"] = str(audio_path)
        result_payload["input"] = input_meta
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
        elif isinstance(exc, RuntimeError) and "No audio input device" in str(exc):
            run_payload["error_code"] = "audio_input_device_unavailable"
        elif isinstance(exc, FileNotFoundError):
            run_payload["error_code"] = "model_or_audio_path_missing"
        else:
            run_payload["error_code"] = "asr_genai_failed"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "result_payload": None,
            "ok": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OpenVINO GenAI Whisper ASR demo (Whisper v3 Turbo): audio file or microphone -> text artifact."
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("models/whisper-large-v3-turbo-ov"),
        help="Path to converted OpenVINO Whisper model directory.",
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
        "--device",
        type=str,
        default="NPU",
        choices=("CPU", "GPU", "NPU"),
        help="OpenVINO device for WhisperPipeline (default: NPU).",
    )
    parser.add_argument(
        "--language",
        type=str,
        default=None,
        help="Optional language token or short code. Example: en or <|en|>.",
    )
    parser.add_argument(
        "--task",
        type=str,
        default="transcribe",
        choices=("transcribe", "translate"),
        help="Whisper task (default: transcribe).",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=128,
        help="Max new tokens for Whisper generation (default: 128).",
    )
    parser.add_argument(
        "--return-timestamps",
        action="store_true",
        help="Return segment timestamps in transcription artifact.",
    )
    parser.add_argument(
        "--word-timestamps",
        action="store_true",
        help="Return word timestamps in transcription artifact.",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_asr_demo_whisper_genai(
        model_dir=args.model_dir,
        audio_in=args.audio_in,
        record_seconds=args.record_seconds,
        sample_rate=args.sample_rate,
        device=args.device,
        language=args.language,
        task=args.task,
        max_new_tokens=args.max_new_tokens,
        return_timestamps=args.return_timestamps,
        word_timestamps=args.word_timestamps,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[asr_whisper_genai_demo] run_dir: {run_dir}")
    print(f"[asr_whisper_genai_demo] run_json: {run_dir / 'run.json'}")
    print(f"[asr_whisper_genai_demo] transcription_json: {run_dir / 'transcription.json'}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
