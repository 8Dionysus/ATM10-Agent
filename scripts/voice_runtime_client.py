from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.io_voice import VoiceRuntimeUnavailableError, record_audio_to_wav


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-voice-client")
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


def _request_json(
    *,
    method: str,
    url: str,
    payload: Mapping[str, Any] | None,
    timeout_sec: float = 120.0,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url=url,
        method=method,
        headers={"Content-Type": "application/json"},
        data=data,
    )
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"error": body}
        raise RuntimeError(f"HTTP {exc.code} from service: {parsed}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot connect to voice service at {url}: {exc.reason}") from exc


def _request_ndjson(
    *,
    method: str,
    url: str,
    payload: Mapping[str, Any] | None,
    timeout_sec: float = 300.0,
) -> list[dict[str, Any]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url=url,
        method=method,
        headers={"Content-Type": "application/json"},
        data=data,
    )
    events: list[dict[str, Any]] = []
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    events.append(parsed)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"error": body}
        raise RuntimeError(f"HTTP {exc.code} from service: {parsed}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot connect to voice service at {url}: {exc.reason}") from exc
    return events


def _prepare_asr_audio_input(
    *,
    run_dir: Path,
    audio_in: Path | None,
    record_seconds: float,
    sample_rate: int,
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


def run_voice_runtime_client(
    *,
    service_url: str,
    mode: str,
    runs_dir: Path,
    audio_in: Path | None = None,
    record_seconds: float = 0.0,
    sample_rate: int = 16000,
    context: str = "",
    language: str | None = None,
    text: str | None = None,
    speaker: str | None = None,
    instruct: str | None = None,
    out_wav: Path | None = None,
    tts_runtime: str = "ovms",
    ovms_tts_url: str | None = None,
    ovms_tts_model: str | None = None,
    chunk_ms: int = 200,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)
    run_dir = _create_run_dir(runs_dir, now)
    run_json_path = run_dir / "run.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "voice_runtime_client",
        "status": "started",
        "request_mode": mode,
        "service_url": service_url.rstrip("/"),
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        base_url = service_url.rstrip("/")
        if mode == "health":
            response = _request_json(method="GET", url=f"{base_url}/health", payload=None)
            response_path = run_dir / "health_response.json"
            _write_json(response_path, response)
            run_payload["status"] = "ok"
            run_payload["paths"]["response_json"] = str(response_path)
            _write_json(run_json_path, run_payload)
            return {"run_dir": run_dir, "run_payload": run_payload, "response_payload": response, "ok": True}

        if mode == "asr":
            audio_path, input_meta = _prepare_asr_audio_input(
                run_dir=run_dir,
                audio_in=audio_in,
                record_seconds=record_seconds,
                sample_rate=sample_rate,
            )
            payload = {
                "audio_path": str(audio_path.resolve()),
                "context": context,
                "language": language,
            }
            response = _request_json(method="POST", url=f"{base_url}/asr", payload=payload)
            response_path = run_dir / "asr_response.json"
            _write_json(response_path, response)
            run_payload["status"] = "ok"
            run_payload["input"] = input_meta
            run_payload["paths"]["response_json"] = str(response_path)
            _write_json(run_json_path, run_payload)
            return {"run_dir": run_dir, "run_payload": run_payload, "response_payload": response, "ok": True}

        if mode == "tts":
            if text is None or not text.strip():
                raise ValueError("--text is required for tts mode.")
            output_path = out_wav or (run_dir / "audio_out.wav")
            payload = {
                "text": text,
                "speaker": speaker,
                "language": language or "Auto",
                "instruct": instruct,
                "runtime": tts_runtime,
                "out_wav_path": output_path.name,
            }
            if ovms_tts_url:
                payload["ovms_tts_url"] = ovms_tts_url
            if ovms_tts_model:
                payload["ovms_tts_model"] = ovms_tts_model
            response = _request_json(method="POST", url=f"{base_url}/tts", payload=payload)
            response_path = run_dir / "tts_response.json"
            _write_json(response_path, response)
            response_result = response.get("result") if isinstance(response, dict) else None
            service_audio_out = (
                response_result.get("audio_out_wav")
                if isinstance(response_result, dict) and isinstance(response_result.get("audio_out_wav"), str)
                else None
            )
            run_payload["status"] = "ok"
            run_payload["paths"]["response_json"] = str(response_path)
            run_payload["paths"]["requested_audio_name"] = output_path.name
            run_payload["paths"]["audio_out_wav"] = service_audio_out or output_path.name
            _write_json(run_json_path, run_payload)
            return {"run_dir": run_dir, "run_payload": run_payload, "response_payload": response, "ok": True}

        if mode == "tts-stream":
            if text is None or not text.strip():
                raise ValueError("--text is required for tts-stream mode.")
            output_path = out_wav or (run_dir / "audio_out.wav")
            payload = {
                "text": text,
                "speaker": speaker,
                "language": language or "Auto",
                "instruct": instruct,
                "runtime": tts_runtime,
                "out_wav_path": output_path.name,
                "chunk_ms": int(chunk_ms),
            }
            if ovms_tts_url:
                payload["ovms_tts_url"] = ovms_tts_url
            if ovms_tts_model:
                payload["ovms_tts_model"] = ovms_tts_model
            events = _request_ndjson(method="POST", url=f"{base_url}/tts_stream", payload=payload)
            events_path = run_dir / "tts_stream_events.jsonl"
            with events_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")

            completed_event = next((item for item in events if item.get("event") == "completed"), None)
            error_event = next((item for item in events if item.get("event") == "error"), None)

            run_payload["paths"]["stream_events_jsonl"] = str(events_path)
            run_payload["paths"]["requested_audio_name"] = output_path.name
            run_payload["stream"] = {
                "chunk_ms": int(chunk_ms),
                "num_events": len(events),
                "num_audio_chunks": sum(1 for item in events if item.get("event") == "audio_chunk"),
            }
            if completed_event is not None:
                service_audio_out = completed_event.get("audio_out_wav")
                run_payload["paths"]["audio_out_wav"] = (
                    str(service_audio_out) if isinstance(service_audio_out, str) else output_path.name
                )
                run_payload["stream"]["first_chunk_latency_sec"] = completed_event.get("first_chunk_latency_sec")
                run_payload["stream"]["total_synthesis_sec"] = completed_event.get("total_synthesis_sec")
                run_payload["stream"]["rtf"] = completed_event.get("rtf")
                run_payload["stream"]["streaming_mode"] = completed_event.get("streaming_mode")
                run_payload["status"] = "ok"
                _write_json(run_json_path, run_payload)
                return {
                    "run_dir": run_dir,
                    "run_payload": run_payload,
                    "response_payload": completed_event,
                    "ok": True,
                }

            run_payload["status"] = "error"
            run_payload["error_code"] = "voice_stream_failed"
            run_payload["paths"]["audio_out_wav"] = output_path.name
            run_payload["error"] = (
                str(error_event.get("error"))
                if isinstance(error_event, dict) and error_event.get("error")
                else "Streaming request completed without 'completed' event."
            )
            _write_json(run_json_path, run_payload)
            return {
                "run_dir": run_dir,
                "run_payload": run_payload,
                "response_payload": error_event,
                "ok": False,
            }

        raise ValueError(f"Unsupported mode: {mode}")
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, VoiceRuntimeUnavailableError):
            run_payload["error_code"] = "voice_runtime_missing_dependency"
        elif isinstance(exc, RuntimeError) and "Cannot connect to voice service" in str(exc):
            run_payload["error_code"] = "voice_service_unreachable"
        else:
            run_payload["error_code"] = "voice_client_failed"
        _write_json(run_json_path, run_payload)
        return {"run_dir": run_dir, "run_payload": run_payload, "response_payload": None, "ok": False}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fast CLI client for long-lived voice runtime service.")
    parser.add_argument(
        "--service-url",
        default="http://127.0.0.1:8765",
        help="Voice service base URL (default: http://127.0.0.1:8765).",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    subparsers.add_parser("health", help="Check service health.")

    asr_parser = subparsers.add_parser("asr", help="Send ASR request to service.")
    asr_parser.add_argument("--audio-in", type=Path, default=None, help="Input WAV/Audio file path.")
    asr_parser.add_argument(
        "--record-seconds",
        type=float,
        default=0.0,
        help="Record microphone audio before request (seconds).",
    )
    asr_parser.add_argument("--sample-rate", type=int, default=16000, help="Sample rate for recording mode.")
    asr_parser.add_argument("--context", type=str, default="", help="Optional ASR context.")
    asr_parser.add_argument("--language", type=str, default=None, help="Optional forced language.")

    tts_parser = subparsers.add_parser("tts", help="Send TTS request to service.")
    tts_parser.add_argument("--text", type=str, required=True, help="Text to synthesize.")
    tts_parser.add_argument("--speaker", type=str, default=None, help="Optional speaker id/name.")
    tts_parser.add_argument("--language", type=str, default="Auto", help="Language (default: Auto).")
    tts_parser.add_argument("--instruct", type=str, default=None, help="Optional style instruction.")
    tts_parser.add_argument("--out-wav", type=Path, default=None, help="Optional output WAV path.")
    tts_parser.add_argument(
        "--tts-runtime",
        choices=("auto", "qwen3", "ovms", "fast_fallback"),
        default="ovms",
        help="TTS runtime mode (default: ovms; fast_fallback is alias).",
    )
    tts_parser.add_argument(
        "--ovms-tts-url",
        type=str,
        default=None,
        help="Optional OVMS TTS endpoint override for this request.",
    )
    tts_parser.add_argument(
        "--ovms-tts-model",
        type=str,
        default=None,
        help="Optional OVMS TTS model id override for this request.",
    )

    tts_stream_parser = subparsers.add_parser("tts-stream", help="Stream TTS chunks and write stream metrics.")
    tts_stream_parser.add_argument("--text", type=str, required=True, help="Text to synthesize.")
    tts_stream_parser.add_argument("--speaker", type=str, default=None, help="Optional speaker id/name.")
    tts_stream_parser.add_argument("--language", type=str, default="Auto", help="Language (default: Auto).")
    tts_stream_parser.add_argument("--instruct", type=str, default=None, help="Optional style instruction.")
    tts_stream_parser.add_argument("--out-wav", type=Path, default=None, help="Optional output WAV path.")
    tts_stream_parser.add_argument(
        "--tts-runtime",
        choices=("auto", "qwen3", "ovms", "fast_fallback"),
        default="ovms",
        help="TTS runtime mode (default: ovms; fast_fallback is alias).",
    )
    tts_stream_parser.add_argument(
        "--ovms-tts-url",
        type=str,
        default=None,
        help="Optional OVMS TTS endpoint override for this request.",
    )
    tts_stream_parser.add_argument(
        "--ovms-tts-model",
        type=str,
        default=None,
        help="Optional OVMS TTS model id override for this request.",
    )
    tts_stream_parser.add_argument(
        "--chunk-ms",
        type=int,
        default=200,
        help="Stream chunk duration in milliseconds (default: 200).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_voice_runtime_client(
        service_url=args.service_url,
        mode=args.mode,
        runs_dir=args.runs_dir,
        audio_in=getattr(args, "audio_in", None),
        record_seconds=getattr(args, "record_seconds", 0.0),
        sample_rate=getattr(args, "sample_rate", 16000),
        context=getattr(args, "context", ""),
        language=getattr(args, "language", None),
        text=getattr(args, "text", None),
        speaker=getattr(args, "speaker", None),
        instruct=getattr(args, "instruct", None),
        out_wav=getattr(args, "out_wav", None),
        tts_runtime=getattr(args, "tts_runtime", "ovms"),
        ovms_tts_url=getattr(args, "ovms_tts_url", None),
        ovms_tts_model=getattr(args, "ovms_tts_model", None),
        chunk_ms=getattr(args, "chunk_ms", 200),
    )
    run_dir = result["run_dir"]
    print(f"[voice_runtime_client] run_dir: {run_dir}")
    print(f"[voice_runtime_client] run_json: {run_dir / 'run.json'}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
