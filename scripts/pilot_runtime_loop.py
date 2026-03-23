from __future__ import annotations

import argparse
import base64
import ctypes
import json
import shutil
import sys
import time
import wave
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.grounded_reply_openvino import (  # noqa: E402
    DEFAULT_GROUNDED_REPLY_MODEL_DIR,
    DeterministicGroundedReplyStub,
    OpenVINOGroundedReplyClient,
)
from src.agent_core.io_voice import (  # noqa: E402
    VoiceRuntimeUnavailableError,
    play_audio,
    write_wav_pcm16,
)
from src.agent_core.vlm_openvino import DEFAULT_OPENVINO_VLM_MODEL_DIR, OpenVINOVLMClient  # noqa: E402
from src.agent_core.vlm_stub import DeterministicStubVLM  # noqa: E402

PILOT_RUNTIME_SCHEMA = "pilot_runtime_v1"
PILOT_RUNTIME_STATUS_SCHEMA = "pilot_runtime_status_v1"
PILOT_TURN_SCHEMA = "pilot_turn_v1"
SERVICE_TOKEN_HEADER = "X-ATM10-Token"

DEFAULT_GATEWAY_URL = "http://127.0.0.1:8770"
DEFAULT_VOICE_RUNTIME_URL = "http://127.0.0.1:8765"
DEFAULT_TTS_RUNTIME_URL = "http://127.0.0.1:8780"
DEFAULT_PILOT_HOTKEY = "F8"
DEFAULT_POLL_INTERVAL_SEC = 0.05
DEFAULT_PILOT_SAMPLE_RATE = 16000
DEFAULT_PILOT_VLM_PROMPT = (
    "Return only JSON with keys summary (string) and next_steps (array of short strings). "
    "Describe the actionable ATM10 context visible on screen."
)
DEFAULT_PILOT_GATEWAY_TOPK = 5
DEFAULT_PILOT_GATEWAY_CANDIDATE_K = 10
DEFAULT_PILOT_MAX_ENTITIES_PER_DOC = 128


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "file not found"
    except json.JSONDecodeError as exc:
        return None, f"failed to parse JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "JSON root must be object"
    return payload, None


def _create_run_dir(root: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-pilot-runtime")
    run_dir = root / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir
    suffix = 1
    while True:
        candidate = root / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def _create_turn_dir(runtime_run_dir: Path, now: datetime) -> Path:
    turns_root = runtime_run_dir / "turns"
    base_name = now.strftime("%Y%m%d_%H%M%S-pilot-turn")
    turn_dir = turns_root / base_name
    if not turn_dir.exists():
        turn_dir.mkdir(parents=True, exist_ok=False)
        return turn_dir
    suffix = 1
    while True:
        candidate = turns_root / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def parse_capture_region_value(raw_value: str | None) -> tuple[int, int, int, int] | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    if not normalized:
        return None
    pieces = [item.strip() for item in normalized.split(",")]
    if len(pieces) != 4:
        raise ValueError("capture region must use x,y,w,h format.")
    try:
        x, y, width, height = (int(item) for item in pieces)
    except ValueError as exc:
        raise ValueError("capture region values must be integers.") from exc
    if width <= 0 or height <= 0:
        raise ValueError("capture region width and height must be > 0.")
    return x, y, width, height


def format_capture_region(region: tuple[int, int, int, int] | None) -> list[int] | None:
    if region is None:
        return None
    return [int(value) for value in region]


def normalize_pilot_hotkey(raw_value: str) -> str:
    normalized = str(raw_value).strip().upper()
    if not normalized or not normalized.startswith("F"):
        raise ValueError("pilot hotkey must be an Fx key such as F8.")
    suffix = normalized[1:]
    if not suffix.isdigit():
        raise ValueError("pilot hotkey must be an Fx key such as F8.")
    index = int(suffix)
    if index < 1 or index > 24:
        raise ValueError("pilot hotkey must be between F1 and F24.")
    return f"F{index}"


def hotkey_virtual_key(hotkey: str) -> int:
    normalized = normalize_pilot_hotkey(hotkey)
    return 0x70 + (int(normalized[1:]) - 1)


def pilot_runtime_latest_status_path(runs_dir: Path) -> Path:
    return Path(runs_dir) / "pilot_runtime_status_latest.json"


def _auth_headers(service_token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if isinstance(service_token, str) and service_token.strip():
        headers[SERVICE_TOKEN_HEADER] = service_token.strip()
    return headers


def _request_json(
    *,
    method: str,
    url: str,
    payload: Mapping[str, Any] | None,
    timeout_sec: float = 120.0,
    service_token: str | None = None,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url=url,
        method=method,
        headers=_auth_headers(service_token),
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
        raise RuntimeError(f"Cannot connect to service at {url}: {exc.reason}") from exc


def _request_ndjson(
    *,
    method: str,
    url: str,
    payload: Mapping[str, Any] | None,
    timeout_sec: float = 300.0,
    service_token: str | None = None,
) -> list[dict[str, Any]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url=url,
        method=method,
        headers=_auth_headers(service_token),
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
        raise RuntimeError(f"HTTP {exc.code} from service: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot connect to service at {url}: {exc.reason}") from exc
    return events


def _load_wav_bytes_mono(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()
        frames = wav_file.readframes(wav_file.getnframes())
    if sample_width != 2:
        raise ValueError("Only 16-bit PCM WAV chunks are supported.")
    waveform = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        waveform = waveform.reshape(-1, channels).mean(axis=1)
    return waveform.reshape(-1), int(sample_rate)


def _decode_tts_chunk_audio(chunk_payload: Mapping[str, Any]) -> tuple[np.ndarray, int]:
    audio_b64 = str(chunk_payload.get("audio_wav_b64", "")).strip()
    if not audio_b64:
        raise ValueError("audio_wav_b64 is missing.")
    return _load_wav_bytes_mono(base64.b64decode(audio_b64))


def _play_waveform_if_enabled(
    *,
    waveform: np.ndarray,
    sample_rate: int,
    playback_enabled: bool,
) -> str | None:
    if not playback_enabled:
        return None
    try:
        play_audio(waveform=waveform, sample_rate=sample_rate)
    except Exception as exc:
        return str(exc)
    return None


def _degraded_prefix(degraded_flags: list[str]) -> str:
    normalized = [str(item).strip() for item in degraded_flags if str(item).strip()]
    if not normalized:
        return ""
    return f"Pilot degraded mode ({', '.join(sorted(dict.fromkeys(normalized)))}). "


def build_fallback_answer(
    *,
    transcript: str,
    visual_summary: str | None,
    citations: list[Mapping[str, Any]],
    degraded_flags: list[str],
    stage_errors: Mapping[str, str],
) -> str:
    parts = [_degraded_prefix(degraded_flags).strip() or "Pilot degraded mode."]
    if transcript.strip():
        parts.append(f"I heard: {transcript.strip()}.")
    else:
        parts.append("I could not recover a usable transcript from the microphone input.")
    if isinstance(visual_summary, str) and visual_summary.strip():
        parts.append(f"Visible context: {visual_summary.strip()}.")
    titles = [str(item.get("title", "")).strip() for item in citations if str(item.get("title", "")).strip()]
    if titles:
        parts.append(f"Grounding sources: {', '.join(titles[:3])}.")
    if stage_errors:
        rendered_errors = ", ".join(f"{name}={message}" for name, message in sorted(stage_errors.items()))
        parts.append(f"Unavailable components: {rendered_errors}.")
    return " ".join(part for part in parts if part).strip()


def _coerce_turn_status(*, degraded_flags: list[str], stage_errors: Mapping[str, str], answer_text: str) -> str:
    if stage_errors and not answer_text.strip():
        return "error"
    if degraded_flags or stage_errors:
        return "degraded"
    return "ok"


def _service_names_from_flags(degraded_flags: list[str], stage_errors: Mapping[str, str]) -> list[str]:
    services: list[str] = []
    for flag in degraded_flags:
        normalized = str(flag).strip().lower()
        if not normalized:
            continue
        if normalized.startswith("capture") or normalized.startswith("vision"):
            services.append("capture")
        elif normalized.startswith("vlm"):
            services.append("vlm")
        elif normalized.startswith("hybrid") or normalized.startswith("retrieval"):
            services.append("gateway")
        elif normalized.startswith("tts"):
            services.append("tts_runtime_service")
        elif normalized.startswith("voice") or normalized.startswith("asr"):
            services.append("voice_runtime_service")
    for stage_name in stage_errors:
        if stage_name == "capture":
            services.append("capture")
        elif stage_name == "vision":
            services.append("vlm")
        elif stage_name == "hybrid":
            services.append("gateway")
        elif stage_name == "tts":
            services.append("tts_runtime_service")
        elif stage_name == "asr":
            services.append("voice_runtime_service")
        elif stage_name == "grounded_reply":
            services.append("text_core")
    return sorted(dict.fromkeys(services))


def enumerate_display_monitors() -> list[tuple[int, int, int, int]]:
    if sys.platform != "win32":
        raise RuntimeError("monitor enumeration is only supported on Windows")

    from ctypes import wintypes

    monitors: list[tuple[int, int, int, int]] = []

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    monitor_enum_proc = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    def _callback(_monitor: int, _hdc: int, rect_ptr: Any, _data: int) -> int:
        rect = rect_ptr.contents
        monitors.append((int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)))
        return 1

    callback = monitor_enum_proc(_callback)
    ctypes.windll.user32.EnumDisplayMonitors(0, 0, callback, 0)
    return monitors


def _resolve_capture_bbox(
    *,
    monitor_index: int | None,
    region: tuple[int, int, int, int] | None,
) -> tuple[int, int, int, int] | None:
    if region is not None:
        x, y, width, height = region
        return x, y, x + width, y + height
    if monitor_index is None:
        return None
    monitors = enumerate_display_monitors()
    if monitor_index < 0 or monitor_index >= len(monitors):
        raise ValueError(f"capture monitor index {monitor_index} is out of range for {len(monitors)} monitor(s).")
    return monitors[monitor_index]


def capture_screen_image(
    *,
    output_path: Path,
    monitor_index: int | None = None,
    region: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    if sys.platform != "win32":
        raise RuntimeError("live screen capture is currently implemented for Windows only.")
    try:
        from PIL import ImageGrab
    except Exception as exc:  # pragma: no cover - dependency presence
        raise RuntimeError("Pillow ImageGrab is required for live screen capture.") from exc

    bbox = _resolve_capture_bbox(monitor_index=monitor_index, region=region)
    image = ImageGrab.grab(bbox=bbox, all_screens=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return {
        "capture_mode": "region" if region is not None else ("monitor" if monitor_index is not None else "desktop"),
        "monitor_index": monitor_index,
        "region": format_capture_region(region),
        "bbox": list(bbox) if bbox is not None else None,
        "width": int(image.width),
        "height": int(image.height),
        "screenshot_path": str(output_path),
    }


def call_voice_asr(
    *,
    voice_runtime_url: str,
    audio_path: Path,
    service_token: str | None = None,
) -> dict[str, Any]:
    response = _request_json(
        method="POST",
        url=f"{voice_runtime_url.rstrip('/')}/asr",
        payload={"audio_path": str(audio_path)},
        service_token=service_token,
    )
    if not bool(response.get("ok")):
        raise RuntimeError(str(response.get("error", "voice runtime ASR request failed")))
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("voice runtime ASR response is missing result payload")
    return result


def call_gateway_hybrid_query(
    *,
    gateway_url: str,
    query: str,
    service_token: str | None = None,
    topk: int = DEFAULT_PILOT_GATEWAY_TOPK,
    candidate_k: int = DEFAULT_PILOT_GATEWAY_CANDIDATE_K,
    max_entities_per_doc: int = DEFAULT_PILOT_MAX_ENTITIES_PER_DOC,
) -> dict[str, Any]:
    response = _request_json(
        method="POST",
        url=f"{gateway_url.rstrip('/')}/v1/gateway",
        payload={
            "schema_version": "gateway_request_v1",
            "operation": "hybrid_query",
            "payload": {
                "profile": "combo_a",
                "query": query,
                "topk": int(topk),
                "candidate_k": int(candidate_k),
                "reranker": "none",
                "max_entities_per_doc": int(max_entities_per_doc),
            },
        },
        service_token=service_token,
    )
    if str(response.get("status", "")).strip().lower() != "ok":
        raise RuntimeError(str(response.get("error", "gateway hybrid_query failed")))
    result_payload = response.get("result")
    result_payload = result_payload if isinstance(result_payload, dict) else {}
    artifacts = response.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    child_runs = artifacts.get("child_runs")
    child_runs = child_runs if isinstance(child_runs, dict) else {}
    hybrid_run_dir_value = child_runs.get("hybrid_query")
    hybrid_run_dir = Path(str(hybrid_run_dir_value)) if hybrid_run_dir_value else None
    hybrid_results_payload: dict[str, Any] | None = None
    hybrid_results_json: Path | None = None
    if hybrid_run_dir is not None:
        candidate = hybrid_run_dir / "hybrid_query_results.json"
        loaded_payload, _load_error = _load_json_object(candidate)
        if loaded_payload is not None:
            hybrid_results_payload = loaded_payload
            hybrid_results_json = candidate
    return {
        "response_payload": response,
        "result_payload": result_payload,
        "hybrid_results_payload": hybrid_results_payload,
        "hybrid_results_json": None if hybrid_results_json is None else str(hybrid_results_json),
        "hybrid_run_dir": None if hybrid_run_dir is None else str(hybrid_run_dir),
    }


def synthesize_with_tts_runtime(
    *,
    tts_runtime_url: str,
    text: str,
    turn_dir: Path,
    service_token: str | None = None,
    playback_enabled: bool = True,
) -> dict[str, Any]:
    tts_json_path = turn_dir / "tts_response.json"
    tts_stream_events_path = turn_dir / "tts_stream_events.jsonl"
    tts_audio_path = turn_dir / "tts_audio_out.wav"

    try:
        events = _request_ndjson(
            method="POST",
            url=f"{tts_runtime_url.rstrip('/')}/tts_stream",
            payload={"text": text, "language": "en"},
            service_token=service_token,
        )
        collected_waveforms: list[np.ndarray] = []
        sample_rate: int | None = None
        playback_error: str | None = None
        for event in events:
            _append_jsonl(tts_stream_events_path, event)
            event_name = str(event.get("event", "")).strip().lower()
            if event_name == "error":
                raise RuntimeError(str(event.get("error", "tts_stream returned error event")))
            if event_name != "audio_chunk":
                continue
            waveform, chunk_sample_rate = _decode_tts_chunk_audio(event)
            if sample_rate is None:
                sample_rate = chunk_sample_rate
            elif sample_rate != chunk_sample_rate:
                raise RuntimeError("tts_stream returned inconsistent sample rates across chunks")
            collected_waveforms.append(waveform)
            if playback_error is None:
                playback_error = _play_waveform_if_enabled(
                    waveform=waveform,
                    sample_rate=chunk_sample_rate,
                    playback_enabled=playback_enabled,
                )
        completed_event = next(
            (item for item in reversed(events) if str(item.get("event", "")).strip().lower() == "completed"),
            None,
        )
        if completed_event is None:
            raise RuntimeError("tts_stream did not emit a completed event")
        if not collected_waveforms or sample_rate is None:
            raise RuntimeError("tts_stream completed without audio chunks")
        write_wav_pcm16(
            path=tts_audio_path,
            waveform=np.concatenate(collected_waveforms),
            sample_rate=sample_rate,
        )
        payload = {
            "status": "ok" if playback_error is None else "degraded",
            "mode": "tts_stream",
            "streaming_mode": "stream",
            "fallback_used": False,
            "fallback_reason": None,
            "chunk_count": sum(1 for item in events if item.get("event") == "audio_chunk"),
            "events_count": len(events),
            "audio_out_wav": str(tts_audio_path),
            "stream_events_jsonl": str(tts_stream_events_path),
            "playback_error": playback_error,
            "completed_event": completed_event,
        }
        _write_json(tts_json_path, payload)
        return payload
    except Exception as stream_exc:
        response = _request_json(
            method="POST",
            url=f"{tts_runtime_url.rstrip('/')}/tts",
            payload={"text": text, "language": "en"},
            service_token=service_token,
        )
        if not bool(response.get("ok")):
            raise RuntimeError(
                f"tts_stream failed ({stream_exc}) and /tts fallback also failed: {response.get('error')}"
            ) from stream_exc
        result = response.get("result")
        result = result if isinstance(result, dict) else {}
        chunks = result.get("chunks")
        chunks = chunks if isinstance(chunks, list) else []
        if not chunks:
            raise RuntimeError(f"tts_stream failed ({stream_exc}) and /tts fallback returned no audio")
        collected_waveforms: list[np.ndarray] = []
        sample_rate: int | None = None
        playback_error: str | None = None
        for chunk in chunks:
            chunk = chunk if isinstance(chunk, dict) else {}
            waveform, chunk_sample_rate = _decode_tts_chunk_audio(chunk)
            if sample_rate is None:
                sample_rate = chunk_sample_rate
            elif sample_rate != chunk_sample_rate:
                raise RuntimeError("tts fallback returned inconsistent sample rates across chunks")
            collected_waveforms.append(waveform)
            if playback_error is None:
                playback_error = _play_waveform_if_enabled(
                    waveform=waveform,
                    sample_rate=chunk_sample_rate,
                    playback_enabled=playback_enabled,
                )
        assert sample_rate is not None
        write_wav_pcm16(
            path=tts_audio_path,
            waveform=np.concatenate(collected_waveforms),
            sample_rate=sample_rate,
        )
        payload = {
            "status": "ok" if playback_error is None else "degraded",
            "mode": "tts",
            "streaming_mode": "fallback_full_response",
            "fallback_used": True,
            "fallback_reason": str(stream_exc),
            "chunk_count": len(chunks),
            "events_count": 0,
            "audio_out_wav": str(tts_audio_path),
            "stream_events_jsonl": str(tts_stream_events_path) if tts_stream_events_path.exists() else None,
            "playback_error": playback_error,
            "completed_event": None,
        }
        _write_json(tts_json_path, payload)
        return payload


def _summarize_hybrid_payload(
    gateway_result: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(gateway_result, Mapping):
        return {"planner_status": "not_available", "degraded": True, "warnings": []}, []
    hybrid_results = gateway_result.get("hybrid_results_payload")
    hybrid_results = hybrid_results if isinstance(hybrid_results, Mapping) else {}
    result_payload = gateway_result.get("result_payload")
    result_payload = result_payload if isinstance(result_payload, Mapping) else {}
    merged_results = hybrid_results.get("merged_results")
    merged_results = merged_results if isinstance(merged_results, list) else []
    summary = {
        "backend": result_payload.get("backend"),
        "profile": result_payload.get("profile"),
        "planner_mode": hybrid_results.get("planner_mode", result_payload.get("planner_mode")),
        "planner_status": hybrid_results.get("planner_status", result_payload.get("planner_status")),
        "degraded": bool(hybrid_results.get("degraded", result_payload.get("degraded"))),
        "warnings": [
            str(item)
            for item in hybrid_results.get("warnings", [])
            if str(item).strip()
        ]
        if isinstance(hybrid_results.get("warnings"), list)
        else [],
        "results_count": hybrid_results.get("results_count", result_payload.get("results_count")),
        "retrieval_results_count": hybrid_results.get(
            "retrieval_results_count",
            result_payload.get("retrieval_results_count"),
        ),
        "kag_results_count": hybrid_results.get("kag_results_count", result_payload.get("kag_results_count")),
        "hybrid_results_json": gateway_result.get("hybrid_results_json"),
        "hybrid_run_dir": gateway_result.get("hybrid_run_dir"),
    }
    citations: list[dict[str, Any]] = []
    for item in merged_results:
        if isinstance(item, dict):
            citations.append(dict(item))
    return summary, citations


def _status_payload(
    *,
    runtime_run_dir: Path,
    latest_status_path: Path,
    state: str,
    hotkey: str,
    gateway_url: str | None,
    voice_runtime_url: str | None,
    tts_runtime_url: str | None,
    capture_monitor: int | None,
    capture_region: tuple[int, int, int, int] | None,
    vlm_model_dir: Path,
    text_model_dir: Path,
    degraded_services: list[str],
    last_turn_payload: Mapping[str, Any] | None = None,
    last_error: str | None = None,
    status: str = "running",
) -> dict[str, Any]:
    latency_summary: dict[str, Any] | None = None
    last_turn_id = None
    last_turn_started_at_utc = None
    last_turn_completed_at_utc = None
    last_turn_json = None
    if isinstance(last_turn_payload, Mapping):
        latency_payload = last_turn_payload.get("latency")
        latency_payload = latency_payload if isinstance(latency_payload, Mapping) else {}
        latency_summary = dict(latency_payload)
        last_turn_id = last_turn_payload.get("turn_id")
        last_turn_started_at_utc = last_turn_payload.get("timestamp_utc")
        last_turn_completed_at_utc = last_turn_payload.get("completed_at_utc")
        paths_payload = last_turn_payload.get("paths")
        paths_payload = paths_payload if isinstance(paths_payload, Mapping) else {}
        last_turn_json = paths_payload.get("turn_json")

    return {
        "schema_version": PILOT_RUNTIME_STATUS_SCHEMA,
        "timestamp_utc": _utc_now(),
        "status": status,
        "state": state,
        "hotkey": hotkey,
        "effective_config": {
            "gateway_url": gateway_url,
            "voice_runtime_url": voice_runtime_url,
            "tts_runtime_url": tts_runtime_url,
            "capture_monitor": capture_monitor,
            "capture_region": format_capture_region(capture_region),
            "vlm_model_dir": str(vlm_model_dir),
            "text_model_dir": str(text_model_dir),
        },
        "degraded_services": degraded_services,
        "last_error": last_error,
        "last_turn_id": last_turn_id,
        "last_turn_started_at_utc": last_turn_started_at_utc,
        "last_turn_completed_at_utc": last_turn_completed_at_utc,
        "latency_summary": latency_summary,
        "paths": {
            "run_dir": str(runtime_run_dir),
            "status_json": str(runtime_run_dir / "pilot_runtime_status.json"),
            "latest_status_json": str(latest_status_path),
            "last_turn_json": last_turn_json,
        },
    }


def _write_runtime_status(
    *,
    runtime_run_dir: Path,
    latest_status_path: Path,
    payload: Mapping[str, Any],
) -> None:
    runtime_status_path = runtime_run_dir / "pilot_runtime_status.json"
    _write_json(runtime_status_path, payload)
    _write_json(latest_status_path, payload)


def load_latest_pilot_runtime_status(runs_dir: Path) -> tuple[dict[str, Any] | None, list[str]]:
    latest_status = pilot_runtime_latest_status_path(runs_dir)
    warnings: list[str] = []
    payload, load_error = _load_json_object(latest_status)
    if payload is None:
        if load_error not in {None, "file not found"}:
            warnings.append(f"{latest_status}: skipped ({load_error})")
        return None, warnings
    if str(payload.get("schema_version", "")).strip() != PILOT_RUNTIME_STATUS_SCHEMA:
        warnings.append(
            f"{latest_status}: skipped (schema_version={payload.get('schema_version')!r} "
            f"expected={PILOT_RUNTIME_STATUS_SCHEMA!r})"
        )
        return None, warnings
    return payload, warnings


@dataclass
class PilotRuntimeStatusHandle:
    runtime_run_dir: Path
    latest_status_path: Path
    hotkey: str
    gateway_url: str | None
    voice_runtime_url: str | None
    tts_runtime_url: str | None
    capture_monitor: int | None
    capture_region: tuple[int, int, int, int] | None
    vlm_model_dir: Path
    text_model_dir: Path
    state: str = "idle"
    last_turn_payload: dict[str, Any] | None = None
    last_error: str | None = None
    degraded_services: list[str] | None = None
    status: str = "running"

    def publish(self) -> dict[str, Any]:
        payload = _status_payload(
            runtime_run_dir=self.runtime_run_dir,
            latest_status_path=self.latest_status_path,
            state=self.state,
            hotkey=self.hotkey,
            gateway_url=self.gateway_url,
            voice_runtime_url=self.voice_runtime_url,
            tts_runtime_url=self.tts_runtime_url,
            capture_monitor=self.capture_monitor,
            capture_region=self.capture_region,
            vlm_model_dir=self.vlm_model_dir,
            text_model_dir=self.text_model_dir,
            degraded_services=list(self.degraded_services or []),
            last_turn_payload=self.last_turn_payload,
            last_error=self.last_error,
            status=self.status,
        )
        _write_runtime_status(
            runtime_run_dir=self.runtime_run_dir,
            latest_status_path=self.latest_status_path,
            payload=payload,
        )
        return payload

    def transition(
        self,
        *,
        state: str,
        degraded_services: list[str] | None = None,
        last_error: str | None = None,
        last_turn_payload: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        self.state = state
        if degraded_services is not None:
            self.degraded_services = list(degraded_services)
        self.last_error = last_error
        if last_turn_payload is not None:
            self.last_turn_payload = last_turn_payload
        if status is not None:
            self.status = status
        return self.publish()


class PollingHotkey:
    def __init__(self, hotkey: str) -> None:
        if sys.platform != "win32":
            raise RuntimeError("pilot hotkey polling is only supported on Windows")
        self._hotkey = normalize_pilot_hotkey(hotkey)
        self._virtual_key = hotkey_virtual_key(self._hotkey)
        self._was_down = False

    def poll_transition(self) -> str | None:
        state = bool(ctypes.windll.user32.GetAsyncKeyState(self._virtual_key) & 0x8000)
        transition: str | None = None
        if state and not self._was_down:
            transition = "down"
        elif self._was_down and not state:
            transition = "up"
        self._was_down = state
        return transition


class PushToTalkRecorder:
    def __init__(self, *, sample_rate: int = DEFAULT_PILOT_SAMPLE_RATE) -> None:
        self._sample_rate = int(sample_rate)
        self._input_device_index: int | None = None
        self._input_device_name: str | None = None
        self._chunks: list[np.ndarray] = []
        self._stream: Any = None
        self._started_at = 0.0

    def _resolve_sd(self) -> Any:
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover - dependency presence
            raise VoiceRuntimeUnavailableError(
                "Recording requires sounddevice. Install dependency: sounddevice."
            ) from exc
        return sd

    def start(self) -> dict[str, Any]:
        if self._stream is not None:
            raise RuntimeError("push-to-talk recorder is already active")
        sd = self._resolve_sd()
        devices = sd.query_devices()
        default_device = sd.default.device
        input_index = None
        if isinstance(default_device, (list, tuple)) and default_device:
            if int(default_device[0]) >= 0:
                input_index = int(default_device[0])
        elif isinstance(default_device, int) and default_device >= 0:
            input_index = int(default_device)
        if input_index is None:
            for index, item in enumerate(devices):
                if int(item.get("max_input_channels", 0)) > 0:
                    input_index = index
                    break
        if input_index is None:
            raise RuntimeError("No audio input device with input channels is available.")

        self._input_device_index = int(input_index)
        self._input_device_name = str(devices[self._input_device_index].get("name", f"device_{input_index}"))
        self._chunks = []

        def _callback(indata: Any, frames: int, _time_info: Any, status: Any) -> None:
            _ = frames
            if getattr(status, "input_overflow", False):
                return
            self._chunks.append(np.asarray(indata, dtype=np.float32).reshape(-1))

        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            device=self._input_device_index,
            callback=_callback,
        )
        self._stream.start()
        self._started_at = perf_counter()
        return {
            "input_device_index": self._input_device_index,
            "input_device_name": self._input_device_name,
            "sample_rate": self._sample_rate,
            "started_at_utc": _utc_now(),
        }

    def stop_to_wav(self, *, output_path: Path) -> dict[str, Any]:
        if self._stream is None:
            raise RuntimeError("push-to-talk recorder is not active")
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
        waveform = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
        self._chunks = []
        duration_sec = perf_counter() - self._started_at
        if waveform.size == 0:
            raise RuntimeError("No audio frames were captured during push-to-talk.")
        write_wav_pcm16(path=output_path, waveform=waveform, sample_rate=self._sample_rate)
        return {
            "mode": "push_to_talk_recorded_microphone",
            "input_device_index": self._input_device_index,
            "input_device_name": self._input_device_name,
            "sample_rate": self._sample_rate,
            "duration_sec": float(duration_sec),
            "num_samples": int(waveform.shape[0]),
            "audio_path": str(output_path),
        }

    def discard(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
            self._chunks = []


def run_pilot_turn(
    *,
    runtime_run_dir: Path,
    audio_input_path: Path,
    audio_input_meta: Mapping[str, Any] | None,
    hotkey: str,
    capture_monitor: int | None,
    capture_region: tuple[int, int, int, int] | None,
    gateway_url: str | None,
    voice_runtime_url: str | None,
    tts_runtime_url: str | None,
    vlm_client: Any,
    grounded_reply_client: Any,
    service_token: str | None = None,
    playback_enabled: bool = True,
    capture_func: Callable[..., dict[str, Any]] = capture_screen_image,
    asr_func: Callable[..., dict[str, Any]] = call_voice_asr,
    hybrid_query_func: Callable[..., dict[str, Any]] = call_gateway_hybrid_query,
    tts_func: Callable[..., dict[str, Any]] = synthesize_with_tts_runtime,
    now: datetime | None = None,
    status_callback: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    effective_now = now or datetime.now(timezone.utc)
    turn_dir = _create_turn_dir(runtime_run_dir, effective_now)
    turn_json_path = turn_dir / "pilot_turn.json"
    copied_audio_path = turn_dir / "audio_input.wav"
    shutil.copyfile(audio_input_path, copied_audio_path)

    base_payload: dict[str, Any] = {
        "schema_version": PILOT_TURN_SCHEMA,
        "turn_id": turn_dir.name,
        "timestamp_utc": effective_now.astimezone(timezone.utc).isoformat(),
        "status": "started",
        "hotkey": hotkey,
        "request": {"hotkey": hotkey},
        "audio": dict(audio_input_meta or {}),
        "capture": {
            "monitor_index": capture_monitor,
            "region": format_capture_region(capture_region),
            "screenshot_path": None,
            "error": None,
        },
        "vision": {"summary": None, "next_steps": [], "error": None},
        "hybrid": {"planner_status": None, "degraded": None, "warnings": [], "citations": [], "error": None},
        "grounded_reply": {"answer_text": None, "cited_entities": [], "error": None},
        "tts": {"status": "not_started", "error": None},
        "degraded_flags": [],
        "degraded_services": [],
        "latency": {},
        "paths": {
            "turn_dir": str(turn_dir),
            "turn_json": str(turn_json_path),
            "audio_input_wav": str(copied_audio_path),
            "screenshot_png": str(turn_dir / "screenshot.png"),
            "tts_audio_wav": str(turn_dir / "tts_audio_out.wav"),
            "tts_stream_events_jsonl": str(turn_dir / "tts_stream_events.jsonl"),
        },
    }
    _write_json(turn_json_path, base_payload)

    degraded_flags: list[str] = []
    stage_errors: dict[str, str] = {}
    t0 = perf_counter()
    stage_started = t0

    try:
        if status_callback is not None:
            status_callback(state="thinking")

        screenshot_path = Path(base_payload["paths"]["screenshot_png"])
        capture_payload: dict[str, Any] | None = None
        try:
            capture_payload = capture_func(
                output_path=screenshot_path,
                monitor_index=capture_monitor,
                region=capture_region,
            )
            base_payload["capture"] = {
                **base_payload["capture"],
                **capture_payload,
                "error": None,
            }
        except Exception as exc:
            stage_errors["capture"] = str(exc)
            degraded_flags.append("capture_failed")
            degraded_flags.append("vision_unavailable")
            base_payload["capture"]["error"] = str(exc)

        base_payload["latency"]["capture_sec"] = round(perf_counter() - stage_started, 6)

        stage_started = perf_counter()
        transcript = ""
        language = ""
        if voice_runtime_url is None:
            stage_errors["asr"] = "voice runtime URL is not configured"
            degraded_flags.append("voice_runtime_unconfigured")
        else:
            try:
                asr_payload = asr_func(
                    voice_runtime_url=voice_runtime_url,
                    audio_path=copied_audio_path,
                    service_token=service_token,
                )
                transcript = str(asr_payload.get("text", "")).strip()
                language = str(asr_payload.get("language", "")).strip()
            except Exception as exc:
                stage_errors["asr"] = str(exc)
                degraded_flags.append("asr_failed")
        if not transcript:
            degraded_flags.append("transcript_empty")
        base_payload["request"]["transcript"] = transcript
        base_payload["request"]["language"] = language
        base_payload["latency"]["asr_sec"] = round(perf_counter() - stage_started, 6)

        stage_started = perf_counter()
        visual_summary = ""
        vision_payload: dict[str, Any] | None = None
        if capture_payload is not None and vlm_client is not None:
            try:
                vision_payload = vlm_client.analyze_image(
                    image_path=screenshot_path,
                    prompt=DEFAULT_PILOT_VLM_PROMPT,
                )
                visual_summary = str(vision_payload.get("summary", "")).strip()
                base_payload["vision"] = {
                    **(vision_payload if isinstance(vision_payload, dict) else {}),
                    "error": None,
                }
            except Exception as exc:
                stage_errors["vision"] = str(exc)
                degraded_flags.append("vlm_failed")
                base_payload["vision"]["error"] = str(exc)
        elif capture_payload is not None:
            stage_errors["vision"] = "local vision provider is unavailable"
            degraded_flags.append("vision_unavailable")
            base_payload["vision"]["error"] = stage_errors["vision"]
        base_payload["latency"]["vision_sec"] = round(perf_counter() - stage_started, 6)

        stage_started = perf_counter()
        gateway_result: dict[str, Any] | None = None
        if gateway_url is None:
            stage_errors["hybrid"] = "gateway URL is not configured"
            degraded_flags.append("hybrid_unconfigured")
        elif not transcript:
            stage_errors["hybrid"] = "hybrid_query skipped because transcript is empty"
            degraded_flags.append("hybrid_skipped_no_transcript")
        else:
            try:
                gateway_result = hybrid_query_func(
                    gateway_url=gateway_url,
                    query=transcript,
                    service_token=service_token,
                )
            except Exception as exc:
                stage_errors["hybrid"] = str(exc)
                degraded_flags.append("hybrid_query_failed")
        hybrid_summary, citations = _summarize_hybrid_payload(gateway_result)
        if str(hybrid_summary.get("planner_status", "")).strip() == "retrieval_only_fallback":
            degraded_flags.append("retrieval_only_fallback")
        base_payload["hybrid"] = {
            **hybrid_summary,
            "citations": citations,
            "error": stage_errors.get("hybrid"),
        }
        base_payload["latency"]["hybrid_sec"] = round(perf_counter() - stage_started, 6)

        stage_started = perf_counter()
        grounded_reply_payload: dict[str, Any] | None = None
        if grounded_reply_client is not None:
            try:
                grounded_reply_payload = grounded_reply_client.generate_reply(
                    transcript=transcript,
                    visual_summary=visual_summary,
                    citations=citations,
                    hybrid_summary=hybrid_summary,
                    degraded_flags=list(sorted(dict.fromkeys(degraded_flags))),
                )
            except Exception as exc:
                stage_errors["grounded_reply"] = str(exc)
                degraded_flags.append("grounded_reply_failed")
        if grounded_reply_payload is None:
            grounded_reply_payload = {
                "provider": "deterministic_fallback_v1",
                "model": "fallback",
                "device": "local",
                "prompt": "",
                "answer_text": build_fallback_answer(
                    transcript=transcript,
                    visual_summary=visual_summary,
                    citations=citations,
                    degraded_flags=list(sorted(dict.fromkeys(degraded_flags))),
                    stage_errors=stage_errors,
                ),
                "cited_entities": [
                    str(item.get("title", "")).strip()
                    for item in citations[:3]
                    if str(item.get("title", "")).strip()
                ],
                "degraded_flags": list(sorted(dict.fromkeys(degraded_flags))),
                "raw_response_text": "",
            }
        answer_text = str(grounded_reply_payload.get("answer_text", "")).strip()
        current_degraded_flags = list(sorted(dict.fromkeys(degraded_flags)))
        if current_degraded_flags:
            prefix = _degraded_prefix(current_degraded_flags)
            if answer_text and not answer_text.startswith(prefix):
                answer_text = f"{prefix}{answer_text}".strip()
            elif not answer_text:
                answer_text = build_fallback_answer(
                    transcript=transcript,
                    visual_summary=visual_summary,
                    citations=citations,
                    degraded_flags=current_degraded_flags,
                    stage_errors=stage_errors,
                )
        grounded_reply_payload["answer_text"] = answer_text
        base_payload["grounded_reply"] = {
            **grounded_reply_payload,
            "error": stage_errors.get("grounded_reply"),
        }
        base_payload["answer_text"] = answer_text
        base_payload["cited_entities"] = list(grounded_reply_payload.get("cited_entities", []))
        base_payload["citations"] = citations
        base_payload["latency"]["grounded_reply_sec"] = round(perf_counter() - stage_started, 6)

        if status_callback is not None:
            status_callback(state="speaking")

        stage_started = perf_counter()
        tts_payload: dict[str, Any]
        if tts_runtime_url is None:
            stage_errors["tts"] = "tts runtime URL is not configured"
            degraded_flags.append("tts_runtime_unconfigured")
            tts_payload = {"status": "not_started", "error": stage_errors["tts"]}
        else:
            try:
                tts_payload = tts_func(
                    tts_runtime_url=tts_runtime_url,
                    text=answer_text,
                    turn_dir=turn_dir,
                    service_token=service_token,
                    playback_enabled=playback_enabled,
                )
                if tts_payload.get("fallback_used"):
                    degraded_flags.append("tts_stream_fallback")
                if str(tts_payload.get("status", "")).strip().lower() == "degraded":
                    degraded_flags.append("tts_playback_degraded")
            except Exception as exc:
                stage_errors["tts"] = str(exc)
                degraded_flags.append("tts_failed")
                tts_payload = {"status": "error", "error": str(exc)}
        base_payload["tts"] = tts_payload
        base_payload["latency"]["tts_sec"] = round(perf_counter() - stage_started, 6)

        unique_degraded_flags = list(sorted(dict.fromkeys(flag for flag in degraded_flags if str(flag).strip())))
        base_payload["degraded_flags"] = unique_degraded_flags
        base_payload["degraded_services"] = _service_names_from_flags(unique_degraded_flags, stage_errors)
        base_payload["errors"] = stage_errors
        base_payload["status"] = _coerce_turn_status(
            degraded_flags=unique_degraded_flags,
            stage_errors=stage_errors,
            answer_text=answer_text,
        )
        base_payload["completed_at_utc"] = _utc_now()
        base_payload["latency"]["total_sec"] = round(perf_counter() - t0, 6)
        _write_json(turn_json_path, base_payload)
        return {
            "ok": base_payload["status"] in {"ok", "degraded"},
            "turn_dir": turn_dir,
            "turn_payload": base_payload,
        }
    except Exception as exc:
        base_payload["status"] = "error"
        base_payload["error"] = str(exc)
        base_payload["completed_at_utc"] = _utc_now()
        base_payload["latency"]["total_sec"] = round(perf_counter() - t0, 6)
        _write_json(turn_json_path, base_payload)
        return {
            "ok": False,
            "turn_dir": turn_dir,
            "turn_payload": base_payload,
        }


def _build_provider(
    *,
    provider_name: str,
    model_dir: Path,
    device: str,
    provider_kind: str,
) -> Any:
    normalized_provider = str(provider_name).strip().lower()
    if provider_kind == "vlm":
        if normalized_provider == "stub":
            return DeterministicStubVLM()
        if normalized_provider == "openvino":
            return OpenVINOVLMClient.from_pretrained(model_dir=model_dir, device=device)
        raise ValueError("pilot VLM provider must be one of: openvino, stub.")
    if normalized_provider == "stub":
        return DeterministicGroundedReplyStub()
    if normalized_provider == "openvino":
        return OpenVINOGroundedReplyClient.from_pretrained(model_dir=model_dir, device=device)
    raise ValueError("pilot text provider must be one of: openvino, stub.")


def run_pilot_runtime_loop(
    *,
    runs_dir: Path,
    gateway_url: str | None,
    voice_runtime_url: str | None,
    tts_runtime_url: str | None,
    hotkey: str,
    capture_monitor: int | None,
    capture_region: tuple[int, int, int, int] | None,
    pilot_vlm_model_dir: Path,
    pilot_text_model_dir: Path,
    pilot_vlm_device: str,
    pilot_text_device: str,
    pilot_vlm_provider: str = "openvino",
    pilot_text_provider: str = "openvino",
    sample_rate: int = DEFAULT_PILOT_SAMPLE_RATE,
    poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC,
    service_token: str | None = None,
    playback_enabled: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    effective_now = now or datetime.now(timezone.utc)
    runtime_run_dir = _create_run_dir(runs_dir, effective_now)
    latest_status_path = pilot_runtime_latest_status_path(runs_dir)
    run_json_path = runtime_run_dir / "run.json"

    run_payload: dict[str, Any] = {
        "schema_version": PILOT_RUNTIME_SCHEMA,
        "timestamp_utc": effective_now.astimezone(timezone.utc).isoformat(),
        "mode": "pilot_runtime_loop",
        "status": "running",
        "paths": {
            "run_dir": str(runtime_run_dir),
            "run_json": str(run_json_path),
            "status_json": str(runtime_run_dir / "pilot_runtime_status.json"),
            "latest_status_json": str(latest_status_path),
        },
        "config": {
            "gateway_url": gateway_url,
            "voice_runtime_url": voice_runtime_url,
            "tts_runtime_url": tts_runtime_url,
            "hotkey": hotkey,
            "capture_monitor": capture_monitor,
            "capture_region": format_capture_region(capture_region),
            "pilot_vlm_model_dir": str(pilot_vlm_model_dir),
            "pilot_text_model_dir": str(pilot_text_model_dir),
            "pilot_vlm_device": pilot_vlm_device,
            "pilot_text_device": pilot_text_device,
            "pilot_vlm_provider": pilot_vlm_provider,
            "pilot_text_provider": pilot_text_provider,
            "sample_rate": int(sample_rate),
            "poll_interval_sec": float(poll_interval_sec),
            "playback_enabled": bool(playback_enabled),
        },
        "provider_init": {},
        "last_turn": None,
        "error": None,
    }
    _write_json(run_json_path, run_payload)

    degraded_services: list[str] = []
    vlm_client: Any = None
    grounded_reply_client: Any = None

    try:
        vlm_client = _build_provider(
            provider_name=pilot_vlm_provider,
            model_dir=pilot_vlm_model_dir,
            device=pilot_vlm_device,
            provider_kind="vlm",
        )
        run_payload["provider_init"]["vlm"] = {"status": "ok", "provider": pilot_vlm_provider}
    except Exception as exc:
        degraded_services.append("vlm")
        run_payload["provider_init"]["vlm"] = {"status": "error", "provider": pilot_vlm_provider, "error": str(exc)}

    try:
        grounded_reply_client = _build_provider(
            provider_name=pilot_text_provider,
            model_dir=pilot_text_model_dir,
            device=pilot_text_device,
            provider_kind="text",
        )
        run_payload["provider_init"]["text"] = {"status": "ok", "provider": pilot_text_provider}
    except Exception as exc:
        degraded_services.append("text_core")
        run_payload["provider_init"]["text"] = {
            "status": "error",
            "provider": pilot_text_provider,
            "error": str(exc),
        }

    if gateway_url is None:
        degraded_services.append("gateway")
    if voice_runtime_url is None:
        degraded_services.append("voice_runtime_service")
    if tts_runtime_url is None:
        degraded_services.append("tts_runtime_service")

    status_handle = PilotRuntimeStatusHandle(
        runtime_run_dir=runtime_run_dir,
        latest_status_path=latest_status_path,
        hotkey=hotkey,
        gateway_url=gateway_url,
        voice_runtime_url=voice_runtime_url,
        tts_runtime_url=tts_runtime_url,
        capture_monitor=capture_monitor,
        capture_region=capture_region,
        vlm_model_dir=pilot_vlm_model_dir,
        text_model_dir=pilot_text_model_dir,
        degraded_services=sorted(dict.fromkeys(degraded_services)),
    )
    status_handle.publish()
    _write_json(run_json_path, run_payload)

    hotkey_watcher = PollingHotkey(hotkey)
    recorder = PushToTalkRecorder(sample_rate=sample_rate)
    temp_audio_path = runtime_run_dir / "live_recording.wav"
    active_recording = False

    try:
        while True:
            transition = hotkey_watcher.poll_transition()
            if transition == "down" and not active_recording:
                try:
                    recorder.start()
                    active_recording = True
                    status_handle.transition(state="listening", last_error=None)
                except Exception as exc:
                    status_handle.transition(
                        state="idle",
                        last_error=str(exc),
                        degraded_services=sorted(
                            dict.fromkeys([*(status_handle.degraded_services or []), "voice_runtime_service"])
                        ),
                        status="degraded",
                    )
            elif transition == "up" and active_recording:
                active_recording = False
                try:
                    audio_meta = recorder.stop_to_wav(output_path=temp_audio_path)
                    status_handle.transition(state="thinking", last_error=None)
                    turn_result = run_pilot_turn(
                        runtime_run_dir=runtime_run_dir,
                        audio_input_path=temp_audio_path,
                        audio_input_meta=audio_meta,
                        hotkey=hotkey,
                        capture_monitor=capture_monitor,
                        capture_region=capture_region,
                        gateway_url=gateway_url,
                        voice_runtime_url=voice_runtime_url,
                        tts_runtime_url=tts_runtime_url,
                        vlm_client=vlm_client,
                        grounded_reply_client=grounded_reply_client,
                        service_token=service_token,
                        playback_enabled=playback_enabled,
                        status_callback=lambda **kwargs: status_handle.transition(
                            state=str(kwargs.get("state", status_handle.state)),
                            degraded_services=status_handle.degraded_services,
                            last_error=status_handle.last_error,
                        ),
                    )
                    turn_payload = turn_result["turn_payload"]
                    run_payload["last_turn"] = {
                        "turn_id": turn_payload.get("turn_id"),
                        "status": turn_payload.get("status"),
                        "turn_json": turn_payload.get("paths", {}).get("turn_json"),
                    }
                    run_payload["error"] = None
                    _write_json(run_json_path, run_payload)
                    status_handle.transition(
                        state="idle",
                        degraded_services=sorted(
                            dict.fromkeys(
                                [*(status_handle.degraded_services or []), *turn_payload.get("degraded_services", [])]
                            )
                        ),
                        last_error=turn_payload.get("error"),
                        last_turn_payload=turn_payload,
                        status="degraded" if turn_payload.get("status") == "degraded" else "running",
                    )
                except Exception as exc:
                    run_payload["error"] = str(exc)
                    _write_json(run_json_path, run_payload)
                    status_handle.transition(
                        state="idle",
                        last_error=str(exc),
                        degraded_services=sorted(
                            dict.fromkeys([*(status_handle.degraded_services or []), "voice_runtime_service"])
                        ),
                        status="degraded",
                    )
            time.sleep(poll_interval_sec)
    except KeyboardInterrupt:
        if active_recording:
            recorder.discard()
        run_payload["status"] = "stopped"
        _write_json(run_json_path, run_payload)
        status_handle.transition(state="idle", status="stopped")
        return {"run_dir": runtime_run_dir, "run_payload": run_payload, "ok": True}
    except Exception as exc:
        if active_recording:
            recorder.discard()
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_json(run_json_path, run_payload)
        status_handle.transition(state="idle", last_error=str(exc), status="error")
        return {"run_dir": runtime_run_dir, "run_payload": run_payload, "ok": False}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local pilot runtime loop: push-to-talk -> ASR -> vision -> hybrid -> reply -> TTS.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs") / "pilot-runtime", help="Pilot runtime artifact root.")
    parser.add_argument("--gateway-url", type=str, default=DEFAULT_GATEWAY_URL, help="Gateway base URL.")
    parser.add_argument("--voice-runtime-url", type=str, default=DEFAULT_VOICE_RUNTIME_URL, help="Voice runtime base URL.")
    parser.add_argument("--tts-runtime-url", type=str, default=DEFAULT_TTS_RUNTIME_URL, help="TTS runtime base URL.")
    parser.add_argument("--pilot-hotkey", type=str, default=DEFAULT_PILOT_HOTKEY, help="Push-to-talk hotkey (Fx only).")
    parser.add_argument("--capture-monitor", type=int, default=None, help="Windows monitor index for live capture.")
    parser.add_argument(
        "--capture-region",
        type=str,
        default=None,
        help="Optional capture region formatted as x,y,w,h.",
    )
    parser.add_argument(
        "--pilot-vlm-model-dir",
        type=Path,
        default=DEFAULT_OPENVINO_VLM_MODEL_DIR,
        help=f"Local OpenVINO VLM model dir (default: {DEFAULT_OPENVINO_VLM_MODEL_DIR}).",
    )
    parser.add_argument(
        "--pilot-text-model-dir",
        type=Path,
        default=DEFAULT_GROUNDED_REPLY_MODEL_DIR,
        help=f"Local OpenVINO grounded reply model dir (default: {DEFAULT_GROUNDED_REPLY_MODEL_DIR}).",
    )
    parser.add_argument("--pilot-vlm-device", type=str, default="GPU", help="OpenVINO device for pilot VLM.")
    parser.add_argument("--pilot-text-device", type=str, default="NPU", help="OpenVINO device for grounded reply model.")
    parser.add_argument(
        "--pilot-vlm-provider",
        choices=("openvino", "stub"),
        default="openvino",
        help="Pilot VLM provider (default: openvino).",
    )
    parser.add_argument(
        "--pilot-text-provider",
        choices=("openvino", "stub"),
        default="openvino",
        help="Pilot grounded-reply provider (default: openvino).",
    )
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_PILOT_SAMPLE_RATE, help="Microphone sample rate.")
    parser.add_argument(
        "--poll-interval-sec",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SEC,
        help="Hotkey polling interval in seconds.",
    )
    parser.add_argument(
        "--disable-tts-playback",
        action="store_true",
        help="Write TTS artifacts without local playback.",
    )
    parser.add_argument(
        "--service-token",
        type=str,
        default=None,
        help="Optional shared service token for gateway/voice/TTS requests.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        hotkey = normalize_pilot_hotkey(args.pilot_hotkey)
        capture_region = parse_capture_region_value(args.capture_region)
    except ValueError as exc:
        print(f"[pilot_runtime_loop] invalid arguments: {exc}")
        return 2

    result = run_pilot_runtime_loop(
        runs_dir=args.runs_dir,
        gateway_url=args.gateway_url,
        voice_runtime_url=args.voice_runtime_url,
        tts_runtime_url=args.tts_runtime_url,
        hotkey=hotkey,
        capture_monitor=args.capture_monitor,
        capture_region=capture_region,
        pilot_vlm_model_dir=args.pilot_vlm_model_dir,
        pilot_text_model_dir=args.pilot_text_model_dir,
        pilot_vlm_device=args.pilot_vlm_device,
        pilot_text_device=args.pilot_text_device,
        pilot_vlm_provider=args.pilot_vlm_provider,
        pilot_text_provider=args.pilot_text_provider,
        sample_rate=args.sample_rate,
        poll_interval_sec=args.poll_interval_sec,
        service_token=args.service_token,
        playback_enabled=not args.disable_tts_playback,
    )
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
