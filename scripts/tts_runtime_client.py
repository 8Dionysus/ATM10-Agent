from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-tts-client")
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
        raise RuntimeError(f"HTTP {exc.code} from TTS runtime: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot connect to TTS runtime at {url}: {exc.reason}") from exc


def _request_ndjson(
    *,
    method: str,
    url: str,
    payload: Mapping[str, Any] | None,
    timeout_sec: float = 120.0,
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
        raise RuntimeError(f"HTTP {exc.code} from TTS runtime: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot connect to TTS runtime at {url}: {exc.reason}") from exc
    return events


def _extract_first_chunk_audio(response_payload: Mapping[str, Any]) -> bytes | None:
    result = response_payload.get("result")
    if not isinstance(result, dict):
        return None
    chunks = result.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        return None
    first = chunks[0]
    if not isinstance(first, dict):
        return None
    audio_b64 = first.get("audio_wav_b64")
    if not isinstance(audio_b64, str) or not audio_b64.strip():
        return None
    try:
        return base64.b64decode(audio_b64, validate=True)
    except Exception:
        return None


def run_tts_runtime_client(
    *,
    service_url: str,
    mode: str,
    runs_dir: Path = Path("runs"),
    text: str | None = None,
    language: str = "en",
    speaker: str | None = None,
    service_voice: bool = False,
    chunk_chars: int | None = None,
    timeout_sec: float = 120.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)
    run_dir = _create_run_dir(runs_dir, now)
    run_json_path = run_dir / "run.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "tts_runtime_client",
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
            response = _request_json(method="GET", url=f"{base_url}/health", payload=None, timeout_sec=timeout_sec)
            response_path = run_dir / "health_response.json"
            _write_json(response_path, response)
            run_payload["status"] = "ok"
            run_payload["paths"]["response_json"] = str(response_path)
            _write_json(run_json_path, run_payload)
            return {"run_dir": run_dir, "run_payload": run_payload, "response_payload": response, "ok": True}

        if mode == "tts":
            if text is None or not text.strip():
                raise ValueError("--text is required for tts mode.")
            request_payload: dict[str, Any] = {
                "text": text,
                "language": language,
                "speaker": speaker,
                "service_voice": bool(service_voice),
            }
            if isinstance(chunk_chars, int) and chunk_chars > 0:
                request_payload["chunk_chars"] = int(chunk_chars)
            response = _request_json(method="POST", url=f"{base_url}/tts", payload=request_payload, timeout_sec=timeout_sec)
            response_path = run_dir / "tts_response.json"
            _write_json(response_path, response)
            maybe_audio = _extract_first_chunk_audio(response)
            if maybe_audio is not None:
                audio_out = run_dir / "audio_out_first_chunk.wav"
                audio_out.write_bytes(maybe_audio)
                run_payload["paths"]["audio_out_wav"] = str(audio_out)
            run_payload["status"] = "ok"
            run_payload["paths"]["response_json"] = str(response_path)
            _write_json(run_json_path, run_payload)
            return {"run_dir": run_dir, "run_payload": run_payload, "response_payload": response, "ok": True}

        if mode == "tts-stream":
            if text is None or not text.strip():
                raise ValueError("--text is required for tts-stream mode.")
            request_payload = {
                "text": text,
                "language": language,
                "speaker": speaker,
                "service_voice": bool(service_voice),
            }
            if isinstance(chunk_chars, int) and chunk_chars > 0:
                request_payload["chunk_chars"] = int(chunk_chars)
            events = _request_ndjson(
                method="POST",
                url=f"{base_url}/tts_stream",
                payload=request_payload,
                timeout_sec=timeout_sec,
            )
            events_path = run_dir / "tts_stream_events.jsonl"
            with events_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            run_payload["status"] = "ok"
            run_payload["paths"]["stream_events_jsonl"] = str(events_path)
            run_payload["stream"] = {
                "num_events": len(events),
                "num_audio_chunks": sum(1 for item in events if item.get("event") == "audio_chunk"),
            }
            _write_json(run_json_path, run_payload)
            return {"run_dir": run_dir, "run_payload": run_payload, "response_payload": events, "ok": True}

        raise ValueError(f"Unsupported mode: {mode}")
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error_code"] = "tts_runtime_client_failed"
        run_payload["error"] = str(exc)
        _write_json(run_json_path, run_payload)
        return {"run_dir": run_dir, "run_payload": run_payload, "response_payload": None, "ok": False}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CLI client for tts_runtime_service.")
    parser.add_argument(
        "--service-url",
        default="http://127.0.0.1:8780",
        help="TTS runtime base URL (default: http://127.0.0.1:8780).",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    parser.add_argument("--timeout-sec", type=float, default=120.0, help="HTTP timeout in seconds.")

    subparsers = parser.add_subparsers(dest="mode", required=True)
    subparsers.add_parser("health", help="Check runtime health.")

    tts_parser = subparsers.add_parser("tts", help="Synthesize full response.")
    tts_parser.add_argument("--text", type=str, required=True, help="Text to synthesize.")
    tts_parser.add_argument("--language", type=str, default="en", help="Language code (default: en).")
    tts_parser.add_argument("--speaker", type=str, default=None, help="Optional speaker id/name.")
    tts_parser.add_argument("--service-voice", action="store_true", help="Use service voice routing.")
    tts_parser.add_argument("--chunk-chars", type=int, default=None, help="Optional chunk size override.")

    stream_parser = subparsers.add_parser("tts-stream", help="Stream synthesis events.")
    stream_parser.add_argument("--text", type=str, required=True, help="Text to synthesize.")
    stream_parser.add_argument("--language", type=str, default="en", help="Language code (default: en).")
    stream_parser.add_argument("--speaker", type=str, default=None, help="Optional speaker id/name.")
    stream_parser.add_argument("--service-voice", action="store_true", help="Use service voice routing.")
    stream_parser.add_argument("--chunk-chars", type=int, default=None, help="Optional chunk size override.")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_tts_runtime_client(
        service_url=args.service_url,
        mode=args.mode,
        runs_dir=args.runs_dir,
        text=getattr(args, "text", None),
        language=getattr(args, "language", "en"),
        speaker=getattr(args, "speaker", None),
        service_voice=bool(getattr(args, "service_voice", False)),
        chunk_chars=getattr(args, "chunk_chars", None),
        timeout_sec=float(getattr(args, "timeout_sec", 120.0)),
    )
    run_dir = result["run_dir"]
    print(f"[tts_runtime_client] run_dir: {run_dir}")
    print(f"[tts_runtime_client] run_json: {run_dir / 'run.json'}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

