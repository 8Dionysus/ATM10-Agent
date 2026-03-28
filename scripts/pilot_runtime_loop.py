from __future__ import annotations

import argparse
import base64
import ctypes
import json
import re
import shutil
import sys
import time
import threading
import wave
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.grounded_reply_openvino import (  # noqa: E402
    DeterministicGroundedReplyStub,
    OpenVINOGroundedReplyClient,
    sanitize_grounded_reply_answer_text,
)
from src.agent_core.host_profiles import (  # noqa: E402
    DEFAULT_HOST_PROFILE_ID,
    get_host_profile,
    host_profile_payload,
    list_host_profile_ids,
)
from src.agent_core.atm10_session_probe import (  # noqa: E402
    ATM10_SESSION_PROBE_SCHEMA,
    find_best_atm10_window,
    probe_atm10_session,
)
from src.agent_core.io_voice import (  # noqa: E402
    VoiceRuntimeUnavailableError,
    play_audio,
    write_wav_pcm16,
)
from src.agent_core.live_hud_state import (  # noqa: E402
    LIVE_HUD_STATE_SCHEMA,
    build_live_hud_state,
)
from src.agent_core.vlm_openvino import OpenVINOVLMClient, sanitize_vlm_summary_text  # noqa: E402
from src.agent_core.vlm_stub import DeterministicStubVLM  # noqa: E402
from scripts.operator_return_recovery import (  # noqa: E402
    SAFE_STOP_AFTER_DEFAULT,
    advance_return_loop_state,
    append_return_event,
    build_return_event,
    compose_anchor_ref,
    reset_return_loop_state,
    return_paths,
)

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
DEFAULT_HOST_PROFILE = get_host_profile(DEFAULT_HOST_PROFILE_ID)
DEFAULT_PILOT_VLM_PROMPT = (
    "Return only JSON with keys summary (string) and next_steps (array of short strings). "
    "Describe only concrete visible scene and UI state from the screenshot. "
    "Prefer menu state, visible buttons, biome or structures, and readable labels over generic game identification. "
    "Do not answer only that this is Minecraft or ATM10 unless that text itself is the key visible detail. "
    "Keep summary to one short sentence under 140 characters. "
    "Default summary language is Russian unless English is explicitly requested. "
    "Leave next_steps empty unless one immediate ATM10 action is obvious."
)
DEFAULT_PILOT_VLM_MAX_NEW_TOKENS = DEFAULT_HOST_PROFILE.pilot_vlm_max_new_tokens
DEFAULT_PILOT_TEXT_MAX_NEW_TOKENS = DEFAULT_HOST_PROFILE.pilot_text_max_new_tokens
DEFAULT_PILOT_VLM_DEVICE = DEFAULT_HOST_PROFILE.pilot_vlm_device
DEFAULT_PILOT_TEXT_DEVICE = DEFAULT_HOST_PROFILE.pilot_text_device
DEFAULT_PILOT_VISION_MAX_EDGE = 1280
DEFAULT_PILOT_ASR_LANGUAGE = DEFAULT_HOST_PROFILE.voice_asr_language
DEFAULT_PILOT_ASR_MAX_NEW_TOKENS = DEFAULT_HOST_PROFILE.voice_asr_max_new_tokens
DEFAULT_PILOT_GATEWAY_TOPK = DEFAULT_HOST_PROFILE.pilot_gateway_topk
DEFAULT_PILOT_GATEWAY_CANDIDATE_K = DEFAULT_HOST_PROFILE.pilot_gateway_candidate_k
DEFAULT_PILOT_MAX_ENTITIES_PER_DOC = DEFAULT_HOST_PROFILE.pilot_max_entities_per_doc
DEFAULT_PILOT_HYBRID_TIMEOUT_SEC = DEFAULT_HOST_PROFILE.pilot_hybrid_timeout_sec
DEFAULT_PILOT_TESSERACT_BIN = "tesseract"
_OPTIONAL_SERVICE_URL_SENTINELS = {"", "none", "null", "disabled", "off"}
_MICROPHONE_POSITIVE_HINTS = (
    "microphone",
    "mic",
    "микрофон",
    "набор микрофонов",
    "headset",
    "гарнитур",
)
_MICROPHONE_NEGATIVE_HINTS = (
    "stereo mix",
    "stereo input",
    "стерео микшер",
    "loopback",
    "переназначение",
    "remap",
    "output",
    "speaker",
    "динамик",
    "headphones",
    "monitor",
)
_LOW_SIGNAL_ASCII_FILLERS = (
    "thank you",
    "thanks",
    "thank you.",
    "thanks.",
    "ok",
    "okay",
)
_LOW_SIGNAL_RUSSIAN_FILLERS = (
    "продолжение следует",
)
_VISUAL_OBSERVATION_REQUEST_HINTS = (
    "что ты видишь",
    "что сейчас видишь",
    "что видишь сейчас",
    "что на экране",
    "что ты видишь на экране",
    "сейчас что-то видишь",
    "видишь что-нибудь",
    "видишь что нибудь",
    "что-нибудь видишь",
    "что нибудь видишь",
    "видно что",
    "опиши экран",
    "опиши что видишь",
    "что видно",
    "видишь пейзаж",
    "what do you see",
    "what do you see on the screen",
    "what's on the screen",
    "what is on the screen",
    "describe the screen",
    "describe what you see",
)
_VISUAL_OBSERVATION_VERB_HINTS = (
    "видишь",
    "видно",
    "на экране",
    "экран",
    "what do you see",
    "see",
    "screen",
)
_VISUAL_OBSERVATION_QUERY_HINTS = (
    "что",
    "что-то",
    "что то",
    "что-нибудь",
    "что нибудь",
    "what",
    "anything",
    "something",
)
_SHORT_SCREEN_GROUNDED_REQUEST_HINTS = (
    "на экране",
    "экран",
    "сейчас",
    "тут",
    "здесь",
    "меню",
    "окно",
    "видишь",
    "видно",
    "screen",
    "menu",
)
_SHORT_SCREEN_GROUNDED_QUERY_PREFIXES = (
    "что",
    "где",
    "какой",
    "какая",
    "какое",
    "это",
    "эта",
    "этот",
    "есть",
    "видишь",
    "видно",
    "what",
    "where",
    "which",
    "is",
)
_SHORT_SCREEN_GROUNDED_BLOCKER_TOKENS = {
    "как",
    "почему",
    "зачем",
    "рецепт",
    "recipe",
    "craft",
    "quest",
    "квест",
}
_SHORT_SCREEN_GROUNDED_BLOCKER_PHRASES = (
    "что делать",
    "что мне делать",
    "подскажи как",
    "где взять",
    "где найти",
    "как сделать",
    "как открыть",
    "как пройти",
)
_LOW_SIGNAL_PEAK_THRESHOLD = 0.01
_LOW_SIGNAL_RMS_THRESHOLD = 0.003
_LOW_SIGNAL_NONTRIVIAL_ABS_THRESHOLD = 0.02
_ASR_NORMALIZATION_TARGET_PEAK = 0.25
_ASR_NORMALIZATION_MAX_GAIN = 64.0
_LOW_SIGNAL_MIN_AUDIO_SEC = 0.12
_PREFETCH_VISION_COMPARE_EDGE = 48
_PREFETCH_VISION_REUSE_MAX_MEAN_ABS_DIFF = 0.015
_DXCAM_BACKEND = "dxgi"
_DXCAM_OUTPUT_COLOR = "BGRA"
_DXCAM_PROCESSOR_BACKEND = "numpy"
_DXCAM_CAMERA_CACHE: dict[tuple[int, str], Any] = {}
_DXCAM_CAMERA_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _normalize_host_profile_payload(host_profile: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(host_profile, Mapping):
        return None
    return dict(host_profile)


def _resolve_runtime_host_profile_payload(host_profile: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized = _normalize_host_profile_payload(host_profile)
    if normalized is not None:
        return normalized
    return host_profile_payload(DEFAULT_HOST_PROFILE_ID)


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


def capture_target_kind(
    *,
    capture_monitor: int | None,
    capture_region: tuple[int, int, int, int] | None,
    capture_payload: Mapping[str, Any] | None = None,
) -> str:
    if isinstance(capture_payload, Mapping):
        capture_mode = str(capture_payload.get("capture_mode", "")).strip().lower()
        if capture_mode in {"monitor", "region", "desktop", "window"}:
            return capture_mode
    if capture_region is not None:
        return "region"
    if capture_monitor is not None:
        return "monitor"
    return "desktop"


def _normalize_window_bounds(
    window_bounds: Mapping[str, Any] | Sequence[int] | None,
) -> list[int] | None:
    if isinstance(window_bounds, Mapping):
        try:
            left = int(window_bounds.get("left"))
            top = int(window_bounds.get("top"))
            right = int(window_bounds.get("right"))
            bottom = int(window_bounds.get("bottom"))
        except Exception:
            return None
        return [left, top, right, bottom]
    if isinstance(window_bounds, Sequence) and not isinstance(window_bounds, (str, bytes, bytearray)):
        if len(window_bounds) != 4:
            return None
        try:
            return [int(item) for item in window_bounds]
        except Exception:
            return None
    return None


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


def _optional_service_url(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    if normalized.lower() in _OPTIONAL_SERVICE_URL_SENTINELS:
        return None
    return normalized


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


def _is_tts_silence_fallback_engine(engine_name: str) -> bool:
    return str(engine_name).strip().lower() == "silence_fallback"


def _contains_cyrillic(text: str) -> bool:
    return any("\u0400" <= char <= "\u04FF" for char in str(text or ""))


def _infer_tts_language(*, text: str, preferred_language: str | None = None) -> str:
    normalized_preferred = str(preferred_language or "").strip().lower()
    if normalized_preferred:
        return normalized_preferred
    if _contains_cyrillic(text):
        return "ru"
    return "en"


def _infer_reply_language(*, transcript: str, transcript_language: str | None = None) -> str:
    normalized_language = str(transcript_language or "").strip().lower()
    if normalized_language.startswith("en"):
        return "en"
    if normalized_language.startswith("ru"):
        return "ru"
    if _contains_cyrillic(transcript):
        return "ru"
    return "ru"


def _build_pilot_vlm_prompt(*, preferred_language: str | None) -> str:
    normalized_language = str(preferred_language or "").strip().lower()
    if normalized_language.startswith("en"):
        language_instruction = "Write summary in English."
    else:
        language_instruction = "Write summary in Russian."
    return f"{DEFAULT_PILOT_VLM_PROMPT} {language_instruction}"


def _normalize_text_whitespace(text: str) -> str:
    return " ".join(str(text or "").replace("\r", " ").replace("\n", " ").split())


def _looks_like_visual_observation_request(transcript: str) -> bool:
    normalized = _normalize_text_whitespace(transcript).lower()
    if not normalized:
        return False
    if any(hint in normalized for hint in _VISUAL_OBSERVATION_REQUEST_HINTS):
        return True
    simplified = normalized.replace("-", " ")
    has_visual_marker = any(hint in simplified for hint in _VISUAL_OBSERVATION_VERB_HINTS)
    has_query_marker = any(hint in simplified for hint in _VISUAL_OBSERVATION_QUERY_HINTS)
    return has_visual_marker and has_query_marker


def _looks_like_short_screen_grounded_request(transcript: str) -> bool:
    normalized = _normalize_text_whitespace(transcript).lower()
    if not normalized or _looks_like_visual_observation_request(normalized):
        return False
    simplified = normalized.replace("-", " ")
    tokens = re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", simplified)
    if not tokens or len(tokens) > 8 or len(simplified) > 72:
        return False
    lowered_tokens = {token.lower() for token in tokens}
    if lowered_tokens & _SHORT_SCREEN_GROUNDED_BLOCKER_TOKENS:
        return False
    if any(phrase in simplified for phrase in _SHORT_SCREEN_GROUNDED_BLOCKER_PHRASES):
        return False
    if not any(hint in simplified for hint in _SHORT_SCREEN_GROUNDED_REQUEST_HINTS):
        return False
    return "?" in transcript or len(tokens) <= 4 or any(
        simplified.startswith(prefix) for prefix in _SHORT_SCREEN_GROUNDED_QUERY_PREFIXES
    )


def _load_wav_path_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()
        frames = wav_file.readframes(wav_file.getnframes())
    if sample_width != 2:
        raise ValueError("Only 16-bit PCM WAV files are supported for pilot ASR preprocessing.")
    waveform = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        waveform = waveform.reshape(-1, channels).mean(axis=1)
    return waveform.reshape(-1), int(sample_rate)


def _analyze_audio_signal(
    *,
    waveform: np.ndarray,
    sample_rate: int,
) -> dict[str, Any]:
    mono = np.asarray(waveform, dtype=np.float32).reshape(-1)
    abs_waveform = np.abs(mono)
    if abs_waveform.size == 0:
        peak_abs = 0.0
        rms = 0.0
        mean_abs = 0.0
        p95_abs = 0.0
        nontrivial_ratio = 0.0
    else:
        peak_abs = float(abs_waveform.max())
        rms = float(np.sqrt(np.mean(np.square(mono))))
        mean_abs = float(abs_waveform.mean())
        p95_abs = float(np.quantile(abs_waveform, 0.95))
        nontrivial_ratio = float(np.mean(abs_waveform >= _LOW_SIGNAL_NONTRIVIAL_ABS_THRESHOLD))
    low_signal = bool(peak_abs < _LOW_SIGNAL_PEAK_THRESHOLD and rms < _LOW_SIGNAL_RMS_THRESHOLD)
    return {
        "status": "low_signal" if low_signal else "ok",
        "sample_rate": int(sample_rate),
        "num_samples": int(mono.shape[0]),
        "duration_sec": round(float(mono.shape[0]) / float(sample_rate), 6) if sample_rate > 0 else 0.0,
        "peak_abs": round(peak_abs, 6),
        "rms": round(rms, 6),
        "mean_abs": round(mean_abs, 6),
        "p95_abs": round(p95_abs, 6),
        "nontrivial_ratio": round(nontrivial_ratio, 6),
    }


def _prepare_asr_audio_input(
    *,
    audio_path: Path,
    turn_dir: Path,
) -> dict[str, Any]:
    waveform, sample_rate = _load_wav_path_mono(audio_path)
    raw_signal = _analyze_audio_signal(waveform=waveform, sample_rate=sample_rate)
    centered_waveform = waveform - float(np.mean(waveform)) if waveform.size else waveform
    peak_abs = max(float(raw_signal.get("peak_abs", 0.0) or 0.0), 0.0)
    gain_applied = 1.0
    prepared_path = audio_path
    preprocess_mode = "copy"

    if peak_abs > 0.0 and peak_abs < _ASR_NORMALIZATION_TARGET_PEAK:
        gain_applied = min(_ASR_NORMALIZATION_TARGET_PEAK / peak_abs, _ASR_NORMALIZATION_MAX_GAIN)
        if gain_applied > 1.05:
            prepared_path = turn_dir / "audio_input_asr.wav"
            amplified_waveform = np.clip(centered_waveform * gain_applied, -1.0, 1.0)
            write_wav_pcm16(path=prepared_path, waveform=amplified_waveform, sample_rate=sample_rate)
            preprocess_mode = "normalized_gain"

    if prepared_path == audio_path:
        prepared_signal = dict(raw_signal)
    else:
        prepared_waveform, prepared_sample_rate = _load_wav_path_mono(prepared_path)
        prepared_signal = _analyze_audio_signal(waveform=prepared_waveform, sample_rate=prepared_sample_rate)

    return {
        "audio_path": prepared_path,
        "signal": {
            "status": str(raw_signal.get("status", "ok")),
            "raw": raw_signal,
            "asr_input": prepared_signal,
        },
        "asr_preprocess": {
            "status": "ok",
            "mode": preprocess_mode,
            "gain_applied": round(float(gain_applied), 4),
        },
    }


def _run_asr_stage(
    *,
    voice_runtime_url: str | None,
    asr_audio_path: Path,
    expected_asr_language: str | None,
    service_token: str | None,
    asr_func: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    stage_started = perf_counter()
    transcript = ""
    language = ""
    error: str | None = None
    degraded_flags: list[str] = []
    if voice_runtime_url is None:
        error = "voice runtime URL is not configured"
        degraded_flags.append("voice_runtime_unconfigured")
    else:
        try:
            asr_payload = asr_func(
                voice_runtime_url=voice_runtime_url,
                audio_path=asr_audio_path,
                language=expected_asr_language,
                service_token=service_token,
            )
            transcript = str(asr_payload.get("text", "")).strip()
            language = str(asr_payload.get("language", "")).strip()
        except Exception as exc:
            error = str(exc)
            degraded_flags.append("asr_failed")
    return {
        "transcript": transcript,
        "language": language,
        "error": error,
        "degraded_flags": degraded_flags,
        "latency_sec": round(perf_counter() - stage_started, 6),
    }


def _run_vision_stage(
    *,
    screenshot_path: Path,
    capture_payload: Mapping[str, Any] | None,
    vision_input_path: Path,
    preferred_language: str | None,
    vlm_client: Any,
) -> dict[str, Any]:
    stage_started = perf_counter()
    input_image_payload: dict[str, Any] | None = None
    visual_summary = ""
    vision_payload: dict[str, Any] | None = None
    error: str | None = None
    degraded_flags: list[str] = []
    vision_image_path = screenshot_path

    if capture_payload is not None and vlm_client is not None:
        try:
            input_image_payload = prepare_vision_input_image(
                source_path=screenshot_path,
                output_path=vision_input_path,
            )
            vision_image_path = Path(str(input_image_payload.get("image_path", screenshot_path)))
        except Exception as exc:
            input_image_payload = {
                "image_path": str(screenshot_path),
                "source_path": str(screenshot_path),
                "width": capture_payload.get("width"),
                "height": capture_payload.get("height"),
                "raw_width": capture_payload.get("raw_width", capture_payload.get("width")),
                "raw_height": capture_payload.get("raw_height", capture_payload.get("height")),
                "resized_from": None,
                "max_edge": DEFAULT_PILOT_VISION_MAX_EDGE,
                "error": str(exc),
            }
        try:
            vision_payload = vlm_client.analyze_image(
                image_path=vision_image_path,
                prompt=_build_pilot_vlm_prompt(preferred_language=preferred_language),
            )
            visual_summary = sanitize_vlm_summary_text(str(vision_payload.get("summary", "")))
            vision_payload["summary"] = visual_summary
        except Exception as exc:
            error = str(exc)
            degraded_flags.append("vlm_failed")
    elif capture_payload is not None:
        error = "local vision provider is unavailable"
        degraded_flags.append("vision_unavailable")

    return {
        "input_image": input_image_payload,
        "vision_payload": vision_payload,
        "visual_summary": visual_summary,
        "error": error,
        "degraded_flags": degraded_flags,
        "latency_sec": round(perf_counter() - stage_started, 6),
        "source": "live_capture_v1",
    }


def _compare_capture_frames(
    *,
    reference_path: Path,
    candidate_path: Path,
    compare_edge: int = _PREFETCH_VISION_COMPARE_EDGE,
    max_mean_abs_diff: float = _PREFETCH_VISION_REUSE_MAX_MEAN_ABS_DIFF,
) -> dict[str, Any]:
    if reference_path.read_bytes() == candidate_path.read_bytes():
        return {
            "status": "ok",
            "mode": "byte_identical",
            "compare_edge": 0,
            "mean_abs_diff": 0.0,
            "max_mean_abs_diff": float(max_mean_abs_diff),
            "reusable": True,
        }
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - dependency presence
        raise RuntimeError("Pillow is required to compare prefetched capture frames.") from exc

    safe_edge = max(8, int(compare_edge))
    with Image.open(reference_path) as ref_image:
        ref_array = np.asarray(
            ref_image.convert("L").resize((safe_edge, safe_edge), getattr(Image, "Resampling", Image).BILINEAR),
            dtype=np.float32,
        )
    with Image.open(candidate_path) as candidate_image:
        candidate_array = np.asarray(
            candidate_image.convert("L").resize((safe_edge, safe_edge), getattr(Image, "Resampling", Image).BILINEAR),
            dtype=np.float32,
        )
    mean_abs_diff = float(np.mean(np.abs(ref_array - candidate_array)) / 255.0)
    return {
        "status": "ok",
        "mode": "grayscale_mean_abs_diff",
        "compare_edge": safe_edge,
        "mean_abs_diff": round(mean_abs_diff, 6),
        "max_mean_abs_diff": float(max_mean_abs_diff),
        "reusable": mean_abs_diff <= float(max_mean_abs_diff),
    }


def _resolve_prefetched_vision_result(
    *,
    prefetched_future: Future[dict[str, Any]],
    screenshot_path: Path,
    capture_payload: Mapping[str, Any] | None,
    vision_input_path: Path,
    preferred_language: str | None,
    vlm_client: Any,
) -> dict[str, Any]:
    stage_started = perf_counter()

    def _fallback_live(prefetch_error: str) -> dict[str, Any]:
        live_result = _run_vision_stage(
            screenshot_path=screenshot_path,
            capture_payload=capture_payload,
            vision_input_path=vision_input_path,
            preferred_language=preferred_language,
            vlm_client=vlm_client,
        )
        live_result["degraded_flags"] = list(
            sorted(dict.fromkeys([*live_result.get("degraded_flags", []), "prefetched_vision_failed"]))
        )
        live_result["prefetch_error"] = prefetch_error
        return live_result

    try:
        prefetched_result = prefetched_future.result()
    except Exception as exc:
        return _fallback_live(str(exc))

    if not isinstance(prefetched_result, Mapping):
        return _fallback_live("prefetched vision result is not a mapping")

    capture_mapping = capture_payload if isinstance(capture_payload, Mapping) else {}
    input_image_payload: dict[str, Any] | None = None
    if capture_payload is not None:
        try:
            input_image_payload = prepare_vision_input_image(
                source_path=screenshot_path,
                output_path=vision_input_path,
            )
        except Exception as exc:
            input_image_payload = {
                "image_path": str(screenshot_path),
                "source_path": str(screenshot_path),
                "width": capture_mapping.get("width"),
                "height": capture_mapping.get("height"),
                "raw_width": capture_mapping.get("raw_width", capture_mapping.get("width")),
                "raw_height": capture_mapping.get("raw_height", capture_mapping.get("height")),
                "resized_from": None,
                "max_edge": DEFAULT_PILOT_VISION_MAX_EDGE,
                "error": str(exc),
            }

    vision_payload = prefetched_result.get("vision_payload")
    vision_payload = dict(vision_payload) if isinstance(vision_payload, Mapping) else None
    if isinstance(vision_payload, dict):
        vision_payload["summary"] = sanitize_vlm_summary_text(str(vision_payload.get("summary", "")))
        vision_payload["source"] = "prefetched_reuse_v1"

    degraded_flags = [
        str(item) for item in prefetched_result.get("degraded_flags", []) if str(item).strip()
    ]
    return {
        "input_image": input_image_payload,
        "vision_payload": vision_payload,
        "visual_summary": sanitize_vlm_summary_text(str(prefetched_result.get("visual_summary", ""))),
        "error": None if prefetched_result.get("error") is None else str(prefetched_result.get("error")),
        "degraded_flags": degraded_flags,
        "latency_sec": round(perf_counter() - stage_started, 6),
        "source": "prefetched_reuse_v1",
    }


def _write_silence_fallback_audio(
    *,
    output_path: Path,
    sample_rate: int,
    duration_sec: float = 0.45,
    capture_error: str | None = None,
    input_device_index: int | None = None,
    input_device_name: str | None = None,
    capture_diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    safe_duration_sec = max(0.2, float(duration_sec))
    sample_count = max(1, int(float(sample_rate) * safe_duration_sec))
    waveform = np.zeros(sample_count, dtype=np.float32)
    write_wav_pcm16(path=output_path, waveform=waveform, sample_rate=sample_rate)
    return {
        "mode": "push_to_talk_silence_fallback",
        "input_device_index": input_device_index,
        "input_device_name": input_device_name,
        "sample_rate": int(sample_rate),
        "duration_sec": round(sample_count / float(sample_rate), 6),
        "num_samples": int(sample_count),
        "audio_path": str(output_path),
        "capture_error": capture_error,
        "capture_diagnostics": dict(capture_diagnostics) if isinstance(capture_diagnostics, Mapping) else None,
    }


def _evaluate_transcript_quality(
    *,
    transcript: str,
    transcript_language: str | None,
    expected_language: str | None,
    audio_signal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_transcript = _normalize_text_whitespace(transcript)
    normalized_detected_language = str(transcript_language or "").strip().lower()
    normalized_expected_language = str(expected_language or "").strip().lower()
    reason_codes: list[str] = []
    if not normalized_transcript:
        reason_codes.append("empty")
    elif not any(char.isalnum() for char in normalized_transcript):
        reason_codes.append("punctuation_only")

    expected_russian = normalized_expected_language.startswith("ru")
    ascii_only = normalized_transcript.isascii()
    lowered = normalized_transcript.lower().replace("…", "...").strip(" \t\r\n.!?,;:")
    alpha_words = [
        word
        for word in re.split(r"\s+", lowered)
        if any(char.isalpha() for char in word)
    ]
    if expected_russian and normalized_transcript and ascii_only:
        if lowered in _LOW_SIGNAL_ASCII_FILLERS:
            reason_codes.append("ascii_filler")
        elif len(alpha_words) <= 2:
            reason_codes.append("short_ascii_when_russian_expected")

    if expected_russian and any(phrase in lowered for phrase in _LOW_SIGNAL_RUSSIAN_FILLERS):
        reason_codes.append("known_low_signal_phrase")

    if normalized_transcript and len(normalized_transcript) <= 2 and not any(char.isdigit() for char in normalized_transcript):
        reason_codes.append("too_short")

    signal_mapping = audio_signal if isinstance(audio_signal, Mapping) else {}
    raw_signal = signal_mapping.get("raw")
    raw_signal = raw_signal if isinstance(raw_signal, Mapping) else signal_mapping
    audio_signal_status = str(raw_signal.get("status", "")).strip().lower()
    if audio_signal_status == "low_signal" and (
        not normalized_transcript
        or "punctuation_only" in reason_codes
        or "too_short" in reason_codes
        or "ascii_filler" in reason_codes
        or "short_ascii_when_russian_expected" in reason_codes
        or "known_low_signal_phrase" in reason_codes
    ):
        reason_codes.append("audio_signal_low")

    unique_reason_codes = list(dict.fromkeys(reason_codes))
    status = "low_signal" if unique_reason_codes else "ok"
    return {
        "status": status,
        "reason_codes": unique_reason_codes,
        "expected_language": normalized_expected_language or None,
        "detected_language": normalized_detected_language or None,
        "audio_signal_status": audio_signal_status or None,
        "transcript_used": status == "ok",
    }


def _is_audio_signal_too_short_for_asr(audio_signal: Mapping[str, Any] | None) -> bool:
    signal_mapping = audio_signal if isinstance(audio_signal, Mapping) else {}
    raw_signal = signal_mapping.get("raw")
    raw_signal = raw_signal if isinstance(raw_signal, Mapping) else signal_mapping
    sample_rate = int(raw_signal.get("sample_rate", 0) or 0)
    num_samples = int(raw_signal.get("num_samples", 0) or 0)
    duration_sec = float(raw_signal.get("duration_sec", 0.0) or 0.0)
    if sample_rate > 0 and num_samples > 0:
        return num_samples < int(sample_rate * _LOW_SIGNAL_MIN_AUDIO_SEC)
    return duration_sec > 0.0 and duration_sec < _LOW_SIGNAL_MIN_AUDIO_SEC


def build_low_signal_retry_answer(*, preferred_language: str | None = None) -> str:
    normalized_language = _infer_reply_language(
        transcript="",
        transcript_language=preferred_language,
    )
    if normalized_language == "en":
        return "I didn't catch that, hold F8 while speaking and repeat briefly."
    return "Не расслышал, удерживай F8 пока говоришь и повтори коротко."


def _compose_local_context_summary(
    *,
    visual_summary: str,
    session_payload: Mapping[str, Any] | None,
    hud_payload: Mapping[str, Any] | None,
) -> str:
    parts: list[str] = []
    normalized_visual_summary = _normalize_text_whitespace(visual_summary)
    if normalized_visual_summary:
        parts.append(normalized_visual_summary)
    hud_mapping = hud_payload if isinstance(hud_payload, Mapping) else {}
    hud_preview = _normalize_text_whitespace(str(hud_mapping.get("text_preview", "")))
    if hud_preview:
        parts.append(f"HUD: {hud_preview}")
    else:
        context_tags = hud_mapping.get("context_tags")
        if isinstance(context_tags, list):
            normalized_tags = [str(item).strip() for item in context_tags[:3] if str(item).strip()]
            if normalized_tags:
                parts.append(f"HUD tags: {', '.join(normalized_tags)}")
    session_mapping = session_payload if isinstance(session_payload, Mapping) else {}
    window_title = _normalize_text_whitespace(str(session_mapping.get("window_title", "")))
    if window_title and not parts:
        parts.append(f"Window: {window_title}")
    combined = "; ".join(part for part in parts if part).strip()
    return combined[:280].rstrip()


def _finalize_spoken_answer_text(answer_text: str) -> tuple[str, list[str]]:
    normalized = _normalize_text_whitespace(answer_text)
    if not normalized:
        return "", []
    flags: list[str] = []
    sentence_match = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)
    if sentence_match:
        first_sentence = sentence_match[0].strip()
        if first_sentence and first_sentence != normalized:
            normalized = first_sentence
            flags.append("spoken_answer_sentence_capped")
    if len(normalized) <= 140:
        return normalized, list(dict.fromkeys(flags))
    truncated = normalized[:137].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    truncated = truncated.rstrip(" ,;:.!?")
    return f"{truncated}...", list(dict.fromkeys([*flags, "spoken_answer_truncated"]))


def _compact_direct_observation_text(text: str, *, max_chars: int = 96) -> str:
    normalized = _normalize_text_whitespace(sanitize_vlm_summary_text(text))
    if not normalized:
        return ""
    for marker in ("; HUD:", "; HUD tags:", "; Window:", " HUD:", " HUD tags:", " Window:"):
        if marker in normalized:
            normalized = normalized.split(marker, 1)[0].rstrip(" ;,")
    sentence_match = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)
    if sentence_match:
        normalized = sentence_match[0].strip()
    if len(normalized) <= max_chars:
        return normalized
    truncated = normalized[: max_chars - 3].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return f"{truncated.rstrip(' ,;:.!?')}..."


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


def build_visual_observation_answer(
    *,
    visual_summary: str | None,
    preferred_language: str | None = None,
) -> str:
    normalized_visual_summary = _compact_direct_observation_text(str(visual_summary or ""))
    if not normalized_visual_summary:
        return ""
    normalized_language = _infer_reply_language(
        transcript="",
        transcript_language=preferred_language,
    )
    if normalized_language == "ru" and _contains_cyrillic(normalized_visual_summary):
        return normalized_visual_summary
    if normalized_language == "en" and not _contains_cyrillic(normalized_visual_summary):
        return normalized_visual_summary
    if normalized_language == "ru":
        return f"На экране: {normalized_visual_summary}"
    return f"On screen: {normalized_visual_summary}"


def build_fallback_answer(
    *,
    transcript: str,
    visual_summary: str | None,
    citations: list[Mapping[str, Any]],
    degraded_flags: list[str],
    stage_errors: Mapping[str, str],
    preferred_language: str | None = None,
) -> str:
    titles = [str(item.get("title", "")).strip() for item in citations if str(item.get("title", "")).strip()]
    normalized_language = _infer_reply_language(
        transcript=transcript,
        transcript_language=preferred_language,
    )
    normalized_visual_summary = _normalize_text_whitespace(str(visual_summary or ""))
    if normalized_language == "ru":
        if normalized_visual_summary:
            return f"Вижу следующее: {normalized_visual_summary}"
        if titles:
            return f"Пока могу опереться на {', '.join(titles[:2])}; повтори запрос короче."
        if stage_errors:
            return "Повтори запрос коротко, чтобы я дал точную подсказку."
        return "Скажи короткий запрос, и я отвечу по текущему экрану."
    if normalized_visual_summary:
        return f"I can see this: {normalized_visual_summary}"
    if titles:
        return f"I can ground on {', '.join(titles[:2])}; please repeat the request more briefly."
    if stage_errors:
        return "Please repeat the request briefly so I can answer precisely."
    return "Say a short request and I will answer from the current screen."


def _emit_turn_console_summary(turn_payload: Mapping[str, Any]) -> None:
    turn_id = str(turn_payload.get("turn_id", "")).strip() or "<unknown>"
    status = str(turn_payload.get("status", "")).strip() or "unknown"
    transcript = str(turn_payload.get("request", {}).get("transcript", "")).strip()
    answer_text = str(turn_payload.get("answer_text", "")).strip()
    session = turn_payload.get("session")
    session = session if isinstance(session, Mapping) else {}
    tts = turn_payload.get("tts")
    tts = tts if isinstance(tts, Mapping) else {}
    transcript_quality = turn_payload.get("transcript_quality")
    transcript_quality = transcript_quality if isinstance(transcript_quality, Mapping) else {}
    reply_mode = str(turn_payload.get("reply_mode", "")).strip() or "unknown"
    session_title = str(session.get("window_title", "")).strip() or "<window-unknown>"
    atm10_probable = bool(session.get("atm10_probable"))
    tts_status = str(tts.get("status", "")).strip() or "unknown"
    print(
        f"[pilot_runtime] turn={turn_id} status={status} "
        f"atm10_probable={str(atm10_probable).lower()} tts={tts_status} "
        f"reply_mode={reply_mode} transcript_quality={transcript_quality.get('status', 'unknown')} "
        f"window={session_title}"
    )
    if transcript:
        print(f"[pilot_runtime] transcript: {transcript}")
    if answer_text:
        print(f"[pilot_runtime] answer: {answer_text}")


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
        if (
            normalized.startswith("capture")
            or normalized.startswith("vision")
            or normalized.startswith("session")
            or normalized.startswith("hud")
        ):
            services.append("capture")
        elif normalized.startswith("vlm"):
            services.append("vlm")
        elif normalized.startswith("hybrid") or normalized.startswith("retrieval"):
            services.append("gateway")
        elif normalized.startswith("tts"):
            services.append("tts_runtime_service")
        elif normalized.startswith("voice") or normalized.startswith("asr"):
            services.append("voice_runtime_service")
        elif normalized.startswith("transcript"):
            services.append("voice_runtime_service")
        elif normalized.startswith("grounded_reply"):
            services.append("text_core")
    for stage_name in stage_errors:
        if stage_name == "capture":
            services.append("capture")
        elif stage_name == "session":
            services.append("capture")
        elif stage_name == "hud_state":
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


def _dxcam_monitor_target(
    *,
    monitor_index: int | None,
    region: tuple[int, int, int, int] | None,
) -> tuple[int, tuple[int, int, int, int], tuple[int, int, int, int]]:
    monitors = enumerate_display_monitors()
    capture_bbox = _resolve_capture_bbox(monitor_index=monitor_index, region=region)
    if capture_bbox is None:
        raise RuntimeError("DXcam capture requires an explicit monitor or region.")
    if monitor_index is not None:
        if monitor_index < 0 or monitor_index >= len(monitors):
            raise ValueError(f"capture monitor index {monitor_index} is out of range for {len(monitors)} monitor(s).")
        monitor_bbox = monitors[monitor_index]
        monitor_left, monitor_top, monitor_right, monitor_bottom = monitor_bbox
        capture_left, capture_top, capture_right, capture_bottom = capture_bbox
        if not (
            capture_left >= monitor_left
            and capture_top >= monitor_top
            and capture_right <= monitor_right
            and capture_bottom <= monitor_bottom
        ):
            raise RuntimeError("capture target must fit inside the selected monitor for DXcam capture.")
        return monitor_index, monitor_bbox, capture_bbox
    left, top, right, bottom = capture_bbox
    for output_index, monitor_bbox in enumerate(monitors):
        monitor_left, monitor_top, monitor_right, monitor_bottom = monitor_bbox
        if (
            left >= monitor_left
            and top >= monitor_top
            and right <= monitor_right
            and bottom <= monitor_bottom
        ):
            return output_index, monitor_bbox, capture_bbox
    raise RuntimeError("capture region must fit inside one monitor for DXcam capture.")


def _get_dxcam_camera(*, output_idx: int) -> Any:
    cache_key = (int(output_idx), _DXCAM_BACKEND)
    with _DXCAM_CAMERA_LOCK:
        camera = _DXCAM_CAMERA_CACHE.get(cache_key)
        if camera is not None:
            return camera
        try:
            import dxcam
        except Exception as exc:  # pragma: no cover - dependency presence
            raise RuntimeError("DXcam is required for low-latency monitor capture.") from exc
        camera = dxcam.create(
            output_idx=int(output_idx),
            output_color=_DXCAM_OUTPUT_COLOR,
            processor_backend=_DXCAM_PROCESSOR_BACKEND,
            backend=_DXCAM_BACKEND,
            max_buffer_len=1,
        )
        if camera is None:
            raise RuntimeError(f"DXcam could not create a capture device for monitor {output_idx}.")
        _DXCAM_CAMERA_CACHE[cache_key] = camera
        return camera


def _capture_with_dxcam(
    *,
    monitor_index: int | None,
    region: tuple[int, int, int, int] | None,
) -> tuple[Any, dict[str, Any]]:
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - dependency presence
        raise RuntimeError("Pillow is required to serialize DXcam captures.") from exc

    output_index, monitor_bbox, capture_bbox = _dxcam_monitor_target(
        monitor_index=monitor_index,
        region=region,
    )
    monitor_left, monitor_top, monitor_right, monitor_bottom = monitor_bbox
    logical_monitor_width = int(monitor_right - monitor_left)
    logical_monitor_height = int(monitor_bottom - monitor_top)
    if logical_monitor_width <= 0 or logical_monitor_height <= 0:
        raise RuntimeError("capture monitor has invalid logical bounds.")

    camera = _get_dxcam_camera(output_idx=output_index)
    native_width = int(getattr(camera, "width", 0) or 0)
    native_height = int(getattr(camera, "height", 0) or 0)
    if native_width <= 0 or native_height <= 0:
        raise RuntimeError("DXcam reported invalid native monitor dimensions.")

    native_region: tuple[int, int, int, int] | None = None
    expected_width = logical_monitor_width
    expected_height = logical_monitor_height
    if region is not None:
        capture_left, capture_top, capture_right, capture_bottom = capture_bbox
        rel_left = capture_left - monitor_left
        rel_top = capture_top - monitor_top
        rel_right = capture_right - monitor_left
        rel_bottom = capture_bottom - monitor_top
        scale_x = native_width / float(logical_monitor_width)
        scale_y = native_height / float(logical_monitor_height)
        native_left = max(0, min(native_width, int(np.floor(rel_left * scale_x))))
        native_top = max(0, min(native_height, int(np.floor(rel_top * scale_y))))
        native_right = max(native_left + 1, min(native_width, int(np.ceil(rel_right * scale_x))))
        native_bottom = max(native_top + 1, min(native_height, int(np.ceil(rel_bottom * scale_y))))
        native_region = (native_left, native_top, native_right, native_bottom)
        expected_width = int(capture_right - capture_left)
        expected_height = int(capture_bottom - capture_top)

    frame = camera.grab(region=native_region, new_frame_only=False)
    if frame is None:
        raise RuntimeError("DXcam returned no frame.")
    if getattr(frame, "ndim", 0) != 3 or int(frame.shape[2]) < 3:
        raise RuntimeError("DXcam returned an unexpected frame shape.")

    rgb_frame = np.ascontiguousarray(frame[:, :, [2, 1, 0]])
    image = Image.fromarray(rgb_frame, mode="RGB")
    capture_mode = "region" if region is not None else "monitor"
    return image, {
        "capture_mode": capture_mode,
        "capture_backend": f"dxcam_{_DXCAM_BACKEND}",
        "monitor_index": monitor_index,
        "resolved_monitor_index": int(output_index),
        "region": format_capture_region(region),
        "bbox": list(capture_bbox),
        "expected_width": int(expected_width),
        "expected_height": int(expected_height),
        "native_region": list(native_region) if native_region is not None else None,
        "native_width": native_width,
        "native_height": native_height,
    }


def _capture_with_pillow(
    *,
    monitor_index: int | None,
    region: tuple[int, int, int, int] | None,
    window_handle: int | None,
    window_title: str | None,
    window_bounds: Mapping[str, Any] | Sequence[int] | None,
) -> tuple[Any, dict[str, Any]]:
    try:
        from PIL import ImageGrab
    except Exception as exc:  # pragma: no cover - dependency presence
        raise RuntimeError("Pillow ImageGrab is required for live screen capture.") from exc

    normalized_window_bounds = _normalize_window_bounds(window_bounds)
    use_window_capture = window_handle is not None and region is None
    if use_window_capture:
        bbox = tuple(normalized_window_bounds) if normalized_window_bounds is not None else None
        image = ImageGrab.grab(window=int(window_handle))
        return image, {
            "capture_mode": "window",
            "capture_backend": "pillow_imagegrab_window",
            "monitor_index": monitor_index,
            "resolved_monitor_index": monitor_index,
            "region": format_capture_region(region),
            "bbox": list(bbox) if bbox is not None else None,
            "window_handle": int(window_handle),
            "window_title": str(window_title).strip() if window_title is not None else None,
            "window_bounds": normalized_window_bounds,
        }

    bbox = _resolve_capture_bbox(monitor_index=monitor_index, region=region)
    image = ImageGrab.grab(bbox=bbox, all_screens=True)
    capture_mode = "region" if region is not None else ("monitor" if monitor_index is not None else "desktop")
    return image, {
        "capture_mode": capture_mode,
        "capture_backend": "pillow_imagegrab_desktop",
        "monitor_index": monitor_index,
        "resolved_monitor_index": monitor_index,
        "region": format_capture_region(region),
        "bbox": list(bbox) if bbox is not None else None,
        "window_handle": None,
        "window_title": None,
        "window_bounds": None,
    }


def capture_screen_image(
    *,
    output_path: Path,
    monitor_index: int | None = None,
    region: tuple[int, int, int, int] | None = None,
    window_handle: int | None = None,
    window_title: str | None = None,
    window_bounds: Mapping[str, Any] | Sequence[int] | None = None,
) -> dict[str, Any]:
    if sys.platform != "win32":
        raise RuntimeError("live screen capture is currently implemented for Windows only.")
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - dependency presence
        raise RuntimeError("Pillow is required for live screen capture.") from exc

    normalized_window_bounds = _normalize_window_bounds(window_bounds)
    use_window_capture = window_handle is not None and region is None
    backend_errors: list[dict[str, str]] = []

    image: Any
    payload: dict[str, Any]
    if use_window_capture:
        image, payload = _capture_with_pillow(
            monitor_index=monitor_index,
            region=region,
            window_handle=window_handle,
            window_title=window_title,
            window_bounds=window_bounds,
        )
    elif monitor_index is not None or region is not None:
        try:
            image, payload = _capture_with_dxcam(
                monitor_index=monitor_index,
                region=region,
            )
        except Exception as exc:
            backend_errors.append({"backend": f"dxcam_{_DXCAM_BACKEND}", "error": str(exc)})
            image, payload = _capture_with_pillow(
                monitor_index=monitor_index,
                region=region,
                window_handle=None,
                window_title=None,
                window_bounds=None,
            )
    else:
        image, payload = _capture_with_pillow(
            monitor_index=monitor_index,
            region=region,
            window_handle=None,
            window_title=None,
            window_bounds=None,
        )

    raw_width = int(image.width)
    raw_height = int(image.height)
    resized_from: list[int] | None = None
    expected_width = None
    expected_height = None
    if use_window_capture and normalized_window_bounds is not None:
        expected_width = max(0, int(normalized_window_bounds[2]) - int(normalized_window_bounds[0]))
        expected_height = max(0, int(normalized_window_bounds[3]) - int(normalized_window_bounds[1]))
    elif payload.get("expected_width") is not None and payload.get("expected_height") is not None:
        expected_width = max(0, int(payload["expected_width"]))
        expected_height = max(0, int(payload["expected_height"]))
    if (
        expected_width is not None
        and expected_height is not None
        and expected_width > 0
        and expected_height > 0
        and (raw_width != expected_width or raw_height != expected_height)
    ):
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize((expected_width, expected_height), resampling)
        resized_from = [raw_width, raw_height]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    response_payload = {
        **payload,
        "width": int(image.width),
        "height": int(image.height),
        "raw_width": raw_width,
        "raw_height": raw_height,
        "resized_from": resized_from,
        "screenshot_path": str(output_path),
    }
    response_payload.pop("expected_width", None)
    response_payload.pop("expected_height", None)
    if backend_errors:
        response_payload["backend_errors"] = backend_errors
    return response_payload


def prepare_vision_input_image(
    *,
    source_path: Path,
    output_path: Path,
    max_edge: int = DEFAULT_PILOT_VISION_MAX_EDGE,
) -> dict[str, Any]:
    if max_edge <= 0:
        raise ValueError("vision max_edge must be positive")
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - dependency presence
        raise RuntimeError("Pillow is required to prepare vision input images.") from exc

    with Image.open(source_path) as opened_image:
        raw_width = int(opened_image.width)
        raw_height = int(opened_image.height)
        prepared_image = opened_image.copy()

    resized_from: list[int] | None = None
    if max(raw_width, raw_height) > int(max_edge):
        scale = float(max_edge) / float(max(raw_width, raw_height))
        target_width = max(1, int(round(raw_width * scale)))
        target_height = max(1, int(round(raw_height * scale)))
        if target_width != raw_width or target_height != raw_height:
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            prepared_image = prepared_image.resize((target_width, target_height), resampling)
            resized_from = [raw_width, raw_height]

    prepared_path = source_path
    if resized_from is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        prepared_image.save(output_path)
        prepared_path = output_path

    return {
        "image_path": str(prepared_path),
        "source_path": str(source_path),
        "width": int(prepared_image.width),
        "height": int(prepared_image.height),
        "raw_width": raw_width,
        "raw_height": raw_height,
        "resized_from": resized_from,
        "max_edge": int(max_edge),
    }


def call_voice_asr(
    *,
    voice_runtime_url: str,
    audio_path: Path,
    language: str | None = None,
    service_token: str | None = None,
) -> dict[str, Any]:
    response = _request_json(
        method="POST",
        url=f"{voice_runtime_url.rstrip('/')}/asr",
        payload={
            "audio_path": str(audio_path),
            **({"language": str(language).strip()} if isinstance(language, str) and language.strip() else {}),
        },
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
    timeout_sec: float = DEFAULT_PILOT_HYBRID_TIMEOUT_SEC,
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
        timeout_sec=timeout_sec,
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
    language: str | None = None,
    turn_dir: Path,
    service_token: str | None = None,
    playback_enabled: bool = True,
) -> dict[str, Any]:
    tts_json_path = turn_dir / "tts_response.json"
    tts_stream_events_path = turn_dir / "tts_stream_events.jsonl"
    tts_audio_path = turn_dir / "tts_audio_out.wav"
    tts_language = _infer_tts_language(text=text, preferred_language=language)

    try:
        events = _request_ndjson(
            method="POST",
            url=f"{tts_runtime_url.rstrip('/')}/tts_stream",
            payload={"text": text, "language": tts_language},
            service_token=service_token,
        )
        collected_waveforms: list[np.ndarray] = []
        chunk_engines: list[str] = []
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
            chunk_engines.append(str(event.get("engine", "")).strip())
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
        silence_fallback_used = any(_is_tts_silence_fallback_engine(name) for name in chunk_engines)
        write_wav_pcm16(
            path=tts_audio_path,
            waveform=np.concatenate(collected_waveforms),
            sample_rate=sample_rate,
        )
        payload = {
            "status": "ok" if playback_error is None and not silence_fallback_used else "degraded",
            "mode": "tts_stream",
            "streaming_mode": "stream",
            "fallback_used": silence_fallback_used,
            "fallback_reason": "silence_fallback_audio" if silence_fallback_used else None,
            "chunk_count": sum(1 for item in events if item.get("event") == "audio_chunk"),
            "events_count": len(events),
            "chunk_engines": chunk_engines,
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
            payload={"text": text, "language": tts_language},
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
        chunk_engines: list[str] = []
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
            chunk_engines.append(str(chunk.get("engine", "")).strip())
            if playback_error is None:
                playback_error = _play_waveform_if_enabled(
                    waveform=waveform,
                    sample_rate=chunk_sample_rate,
                    playback_enabled=playback_enabled,
                )
        assert sample_rate is not None
        silence_fallback_used = any(_is_tts_silence_fallback_engine(name) for name in chunk_engines)
        write_wav_pcm16(
            path=tts_audio_path,
            waveform=np.concatenate(collected_waveforms),
            sample_rate=sample_rate,
        )
        fallback_reasons = [str(stream_exc)]
        if silence_fallback_used:
            fallback_reasons.append("silence_fallback_audio")
        payload = {
            "status": "ok" if playback_error is None and not silence_fallback_used else "degraded",
            "mode": "tts",
            "streaming_mode": "fallback_full_response",
            "fallback_used": True,
            "fallback_reason": "; ".join(reason for reason in fallback_reasons if reason),
            "chunk_count": len(chunks),
            "events_count": 0,
            "chunk_engines": chunk_engines,
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


def _write_warmup_image(path: Path) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (56, 56), color=(18, 24, 28))
    for x in range(14, 42):
        for y in range(14, 42):
            image.putpixel((x, y), (90, 160, 120))
    image.save(path, format="PNG")
    return path


def _warmup_vlm_provider(
    *,
    vlm_client: Any,
    runtime_run_dir: Path,
) -> dict[str, Any]:
    warmup_image_path = _write_warmup_image(runtime_run_dir / "tmp" / "pilot_vlm_warmup.png")
    started = perf_counter()
    result = vlm_client.analyze_image(
        image_path=warmup_image_path,
        prompt=_build_pilot_vlm_prompt(preferred_language="ru"),
    )
    latency_sec = round(perf_counter() - started, 6)
    return {
        "requested": True,
        "ok": True,
        "latency_sec": latency_sec,
        "image_path": str(warmup_image_path),
        "result_preview": _normalize_text_whitespace(str(result.get("summary", "")))[:140],
    }


def _warmup_grounded_reply_provider(
    *,
    grounded_reply_client: Any,
) -> dict[str, Any]:
    started = perf_counter()
    result = grounded_reply_client.generate_reply(
        transcript="Что на экране",
        visual_summary="Темная пещера и интерфейс ATM10.",
        citations=[],
        hybrid_summary={"planner_status": "warmup_local_only"},
        degraded_flags=[],
        preferred_language="ru",
    )
    latency_sec = round(perf_counter() - started, 6)
    return {
        "requested": True,
        "ok": True,
        "latency_sec": latency_sec,
        "result_preview": _normalize_text_whitespace(str(result.get("answer_text", "")))[:140],
    }


def _status_payload(
    *,
    runtime_run_dir: Path,
    latest_status_path: Path,
    host_profile: Mapping[str, Any] | None,
    state: str,
    hotkey: str,
    gateway_url: str | None,
    voice_runtime_url: str | None,
    tts_runtime_url: str | None,
    input_device_index: int | None,
    asr_language: str | None,
    asr_max_new_tokens: int,
    asr_warmup_requested: bool,
    capture_monitor: int | None,
    capture_region: tuple[int, int, int, int] | None,
    vlm_model_dir: Path,
    text_model_dir: Path,
    vlm_provider: str,
    text_provider: str,
    pilot_vlm_max_new_tokens: int,
    pilot_text_max_new_tokens: int,
    pilot_hybrid_timeout_sec: float,
    provider_init: Mapping[str, Any] | None,
    degraded_services: list[str],
    last_turn_payload: Mapping[str, Any] | None = None,
    last_return_event: Mapping[str, Any] | None = None,
    return_loop_state: Mapping[str, Any] | None = None,
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
    normalized_host_profile = _normalize_host_profile_payload(host_profile)

    return {
        "schema_version": PILOT_RUNTIME_STATUS_SCHEMA,
        "timestamp_utc": _utc_now(),
        "status": status,
        "state": state,
        "hotkey": hotkey,
        "host_profile": normalized_host_profile,
        "effective_config": {
            "host_profile_id": normalized_host_profile.get("id") if isinstance(normalized_host_profile, Mapping) else None,
            "gateway_url": gateway_url,
            "voice_runtime_url": voice_runtime_url,
            "tts_runtime_url": tts_runtime_url,
            "input_device_index": input_device_index,
            "asr_language": asr_language,
            "asr_max_new_tokens": int(asr_max_new_tokens),
            "asr_warmup": {"requested": bool(asr_warmup_requested)},
            "capture_monitor": capture_monitor,
            "capture_region": format_capture_region(capture_region),
            "vlm_model_dir": str(vlm_model_dir),
            "text_model_dir": str(text_model_dir),
            "vlm_provider": vlm_provider,
            "text_provider": text_provider,
            "pilot_vlm_max_new_tokens": int(pilot_vlm_max_new_tokens),
            "pilot_text_max_new_tokens": int(pilot_text_max_new_tokens),
            "pilot_hybrid_timeout_sec": float(pilot_hybrid_timeout_sec),
        },
        "provider_init": dict(provider_init or {}),
        "degraded_services": degraded_services,
        "last_return_event": dict(last_return_event or {}) if isinstance(last_return_event, Mapping) else None,
        "return_loop_state": dict(return_loop_state or {}) if isinstance(return_loop_state, Mapping) else None,
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
    host_profile: dict[str, Any] | None
    hotkey: str
    gateway_url: str | None
    voice_runtime_url: str | None
    tts_runtime_url: str | None
    input_device_index: int | None
    asr_language: str | None
    asr_max_new_tokens: int
    asr_warmup_requested: bool
    capture_monitor: int | None
    capture_region: tuple[int, int, int, int] | None
    vlm_model_dir: Path
    text_model_dir: Path
    vlm_provider: str
    text_provider: str
    pilot_vlm_max_new_tokens: int
    pilot_text_max_new_tokens: int
    pilot_hybrid_timeout_sec: float
    provider_init: dict[str, Any] | None = None
    state: str = "idle"
    last_turn_payload: dict[str, Any] | None = None
    last_return_event: dict[str, Any] | None = None
    return_loop_state: dict[str, Any] | None = None
    last_error: str | None = None
    degraded_services: list[str] | None = None
    status: str = "running"

    def publish(self) -> dict[str, Any]:
        payload = _status_payload(
            runtime_run_dir=self.runtime_run_dir,
            latest_status_path=self.latest_status_path,
            host_profile=self.host_profile,
            state=self.state,
            hotkey=self.hotkey,
            gateway_url=self.gateway_url,
            voice_runtime_url=self.voice_runtime_url,
            tts_runtime_url=self.tts_runtime_url,
            input_device_index=self.input_device_index,
            asr_language=self.asr_language,
            asr_max_new_tokens=self.asr_max_new_tokens,
            asr_warmup_requested=self.asr_warmup_requested,
            capture_monitor=self.capture_monitor,
            capture_region=self.capture_region,
            vlm_model_dir=self.vlm_model_dir,
            text_model_dir=self.text_model_dir,
            vlm_provider=self.vlm_provider,
            text_provider=self.text_provider,
            pilot_vlm_max_new_tokens=self.pilot_vlm_max_new_tokens,
            pilot_text_max_new_tokens=self.pilot_text_max_new_tokens,
            pilot_hybrid_timeout_sec=self.pilot_hybrid_timeout_sec,
            provider_init=dict(self.provider_init or {}),
            degraded_services=list(self.degraded_services or []),
            last_turn_payload=self.last_turn_payload,
            last_return_event=self.last_return_event,
            return_loop_state=self.return_loop_state,
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
        last_return_event: dict[str, Any] | None = None,
        return_loop_state: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        self.state = state
        if degraded_services is not None:
            self.degraded_services = list(degraded_services)
        self.last_error = last_error
        if last_turn_payload is not None:
            self.last_turn_payload = last_turn_payload
        if last_return_event is not None:
            self.last_return_event = dict(last_return_event)
        if return_loop_state is not None:
            self.return_loop_state = dict(return_loop_state)
        if status is not None:
            self.status = status
        return self.publish()


def _pilot_return_anchor_refs(
    *,
    runs_dir: Path,
    turn_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    paths_payload = turn_payload.get("paths")
    paths_payload = paths_payload if isinstance(paths_payload, Mapping) else {}
    refs = [
        compose_anchor_ref(
            artifact_kind="pilot_runtime_status",
            ref=str(pilot_runtime_latest_status_path(runs_dir)),
            label="pilot runtime latest status",
        ),
        compose_anchor_ref(
            artifact_kind="pilot_turn",
            ref=str(paths_payload.get("turn_json", "")).strip(),
            label="latest pilot turn",
        ),
    ]
    canonical_root = Path(runs_dir).parent
    canonical_refs = [
        (
            "gateway_http_combo_a_smoke",
            canonical_root / "ci-smoke-gateway-http-combo-a" / "gateway_http_smoke_summary.json",
            "gateway HTTP Combo A smoke",
        ),
        (
            "cross_service_suite_combo_a_smoke",
            canonical_root / "nightly-combo-a-cross-service-suite" / "cross_service_benchmark_suite.json",
            "cross-service Combo A suite",
        ),
        (
            "combo_a_operating_cycle",
            canonical_root / "nightly-combo-a-operating-cycle" / "operating_cycle_summary.json",
            "Combo A operating cycle",
        ),
    ]
    for artifact_kind, path, label in canonical_refs:
        if path.exists():
            refs.append(
                compose_anchor_ref(
                    artifact_kind=artifact_kind,
                    ref=str(path),
                    label=label,
                    required=False,
                )
            )
    return refs


def _pilot_return_reason_code(turn_payload: Mapping[str, Any]) -> str | None:
    degraded_flags = {
        str(item).strip()
        for item in turn_payload.get("degraded_flags", [])
        if str(item).strip()
    }
    transcript_quality = turn_payload.get("transcript_quality")
    transcript_quality = transcript_quality if isinstance(transcript_quality, Mapping) else {}
    transcript_quality_status = str(transcript_quality.get("status", "")).strip().lower()
    grounding_flags = {
        "retrieval_only_fallback",
        "hybrid_degraded",
        "hybrid_query_failed",
        "hybrid_fast_fail",
        "grounded_reply_failed",
        "grounded_reply_unavailable",
        "grounded_reply_answer_fallback",
    }
    if degraded_flags & grounding_flags:
        return "pilot_grounding_degraded"
    if transcript_quality_status == "low_signal" and (
        "transcript_low_signal" in degraded_flags
        or "hybrid_skipped_low_signal" in degraded_flags
        or "transcript_empty" in degraded_flags
    ):
        return "pilot_transcript_low_signal"
    return None


def _maybe_emit_pilot_return_event(
    *,
    runs_dir: Path,
    turn_payload: Mapping[str, Any],
    loop_state: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    reason_code = _pilot_return_reason_code(turn_payload)
    if reason_code is None:
        return reset_return_loop_state(suppress_first_occurrence=True), None
    next_loop_state, should_emit, emitted_count, event_status = advance_return_loop_state(
        loop_state,
        reason_code=reason_code,
        suppress_first_occurrence=True,
        safe_stop_after=SAFE_STOP_AFTER_DEFAULT,
    )
    if not should_emit:
        return next_loop_state, None
    transcript_quality = turn_payload.get("transcript_quality")
    transcript_quality = transcript_quality if isinstance(transcript_quality, Mapping) else {}
    event_payload = build_return_event(
        reason_code=reason_code,
        anchor_refs=_pilot_return_anchor_refs(runs_dir=runs_dir, turn_payload=turn_payload),
        status=event_status,
        loop_count=emitted_count,
        safe_stop_after=SAFE_STOP_AFTER_DEFAULT,
        details={
            "turn_id": turn_payload.get("turn_id"),
            "reply_mode": turn_payload.get("reply_mode"),
            "degraded_flags": [
                str(item) for item in turn_payload.get("degraded_flags", []) if str(item).strip()
            ],
            "transcript_quality_status": transcript_quality.get("status"),
        },
    )
    append_return_event(runs_dir, event_payload)
    return next_loop_state, event_payload


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
    def __init__(
        self,
        *,
        sample_rate: int = DEFAULT_PILOT_SAMPLE_RATE,
        preferred_input_device_index: int | None = None,
    ) -> None:
        self._sample_rate = int(sample_rate)
        self._preferred_input_device_index = preferred_input_device_index
        self._input_device_index: int | None = None
        self._input_device_name: str | None = None
        self._input_device_channels: int = 1
        self._record_channels: int = 1
        self._selected_channel_index: int | None = None
        self._selected_channel_rms: float | None = None
        self._captured_channel_rms: list[float] = []
        self._chunks: list[np.ndarray] = []
        self._stream: Any = None
        self._started_at = 0.0
        self._callback_count = 0
        self._callback_frames = 0
        self._overflow_count = 0
        self._first_callback_at: float | None = None
        self._last_callback_at: float | None = None

    def _resolve_sd(self) -> Any:
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover - dependency presence
            raise VoiceRuntimeUnavailableError(
                "Recording requires sounddevice. Install dependency: sounddevice."
            ) from exc
        return sd

    @staticmethod
    def _candidate_device_score(device_name: str) -> int:
        normalized = str(device_name).strip().lower()
        score = 0
        if any(hint in normalized for hint in _MICROPHONE_POSITIVE_HINTS):
            score += 10
        if any(hint in normalized for hint in _MICROPHONE_NEGATIVE_HINTS):
            score -= 20
        return score

    @classmethod
    def select_input_device_index(
        cls,
        *,
        devices: Sequence[Mapping[str, Any]],
        default_device: Any,
        preferred_input_device_index: int | None = None,
    ) -> int:
        input_candidates = [
            index for index, item in enumerate(devices) if int(item.get("max_input_channels", 0) or 0) > 0
        ]
        if not input_candidates:
            raise RuntimeError("No audio input device with input channels is available.")

        if preferred_input_device_index is not None:
            if preferred_input_device_index not in input_candidates:
                raise RuntimeError(
                    f"Configured input device index {preferred_input_device_index} is not a valid audio input device."
                )
            return int(preferred_input_device_index)

        default_input_index: int | None = None
        if isinstance(default_device, (list, tuple)) and default_device:
            candidate = int(default_device[0])
            if candidate in input_candidates:
                default_input_index = candidate
        elif isinstance(default_device, int) and default_device in input_candidates:
            default_input_index = int(default_device)

        scored_candidates: list[tuple[int, int, int]] = []
        for index in input_candidates:
            item = devices[index]
            score = cls._candidate_device_score(str(item.get("name", f"device_{index}")))
            if default_input_index == index:
                score += 5
            scored_candidates.append((score, int(item.get("max_input_channels", 0) or 0), -index))

        best_position = max(range(len(scored_candidates)), key=scored_candidates.__getitem__)
        best_score = scored_candidates[best_position][0]
        if best_score <= 0 and default_input_index is not None:
            return int(default_input_index)
        return int(input_candidates[best_position])

    def start(self) -> dict[str, Any]:
        if self._stream is not None:
            raise RuntimeError("push-to-talk recorder is already active")
        sd = self._resolve_sd()
        devices = sd.query_devices()
        default_device = sd.default.device
        input_index = self.select_input_device_index(
            devices=devices,
            default_device=default_device,
            preferred_input_device_index=self._preferred_input_device_index,
        )

        self._input_device_index = int(input_index)
        self._input_device_name = str(devices[self._input_device_index].get("name", f"device_{input_index}"))
        max_input_channels = int(devices[self._input_device_index].get("max_input_channels", 0) or 0)
        self._input_device_channels = max(1, max_input_channels)
        self._record_channels = max(1, min(self._input_device_channels, 4))
        self._selected_channel_index = None
        self._selected_channel_rms = None
        self._captured_channel_rms = []
        self._chunks = []
        self._callback_count = 0
        self._callback_frames = 0
        self._overflow_count = 0
        self._first_callback_at = None
        self._last_callback_at = None

        def _callback(indata: Any, frames: int, _time_info: Any, status: Any) -> None:
            callback_now = perf_counter()
            if getattr(status, "input_overflow", False):
                self._overflow_count += 1
                return
            chunk = np.asarray(indata, dtype=np.float32)
            if chunk.ndim == 1:
                chunk = chunk.reshape(-1, 1)
            elif chunk.ndim != 2:
                chunk = chunk.reshape(chunk.shape[0], -1)
            if self._first_callback_at is None:
                self._first_callback_at = callback_now
            self._last_callback_at = callback_now
            self._callback_count += 1
            self._callback_frames += int(chunk.shape[0] if chunk.ndim >= 1 else frames)
            self._chunks.append(np.array(chunk, dtype=np.float32, copy=True))

        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=self._record_channels,
            dtype="float32",
            device=self._input_device_index,
            callback=_callback,
        )
        self._stream.start()
        self._started_at = perf_counter()
        return {
            "input_device_index": self._input_device_index,
            "input_device_name": self._input_device_name,
            "input_device_channels": self._input_device_channels,
            "record_channels": self._record_channels,
            "sample_rate": self._sample_rate,
            "started_at_utc": _utc_now(),
        }

    def capture_diagnostics(self, *, duration_sec: float, total_frames: int) -> dict[str, Any]:
        first_callback_offset_sec = (
            round(self._first_callback_at - self._started_at, 6)
            if self._first_callback_at is not None and self._started_at > 0.0
            else None
        )
        last_callback_offset_sec = (
            round(self._last_callback_at - self._started_at, 6)
            if self._last_callback_at is not None and self._started_at > 0.0
            else None
        )
        return {
            "callback_count": int(self._callback_count),
            "callback_frames": int(self._callback_frames),
            "total_frames": int(total_frames),
            "overflow_count": int(self._overflow_count),
            "first_callback_offset_sec": first_callback_offset_sec,
            "last_callback_offset_sec": last_callback_offset_sec,
            "duration_sec": round(float(duration_sec), 6),
        }

    @staticmethod
    def _collapse_to_mono(waveform: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
        samples = np.asarray(waveform, dtype=np.float32)
        if samples.ndim == 1:
            samples = samples.reshape(-1, 1)
        elif samples.ndim != 2:
            samples = samples.reshape(samples.shape[0], -1)
        if samples.shape[0] == 0:
            return np.zeros(0, dtype=np.float32), {
                "channels": int(samples.shape[1]) if samples.ndim == 2 else 0,
                "selected_channel_index": None,
                "selected_channel_rms": None,
                "channel_rms": [],
            }

        channel_rms = np.sqrt(np.mean(np.square(samples), axis=0, dtype=np.float64))
        selected_channel_index = int(np.argmax(channel_rms))
        mono = np.asarray(samples[:, selected_channel_index], dtype=np.float32).reshape(-1)
        return mono, {
            "channels": int(samples.shape[1]),
            "selected_channel_index": selected_channel_index,
            "selected_channel_rms": float(channel_rms[selected_channel_index]),
            "channel_rms": [float(value) for value in channel_rms.tolist()],
        }

    def stop_to_wav(self, *, output_path: Path) -> dict[str, Any]:
        if self._stream is None:
            raise RuntimeError("push-to-talk recorder is not active")
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
        waveform = (
            np.concatenate(self._chunks, axis=0)
            if self._chunks
            else np.zeros((0, max(1, int(self._record_channels))), dtype=np.float32)
        )
        self._chunks = []
        duration_sec = perf_counter() - self._started_at
        mono_waveform, channel_meta = self._collapse_to_mono(waveform)
        capture_diagnostics = self.capture_diagnostics(
            duration_sec=duration_sec,
            total_frames=int(waveform.shape[0]),
        )
        if mono_waveform.size == 0:
            raise RuntimeError("No audio frames were captured during push-to-talk.")
        self._selected_channel_index = channel_meta["selected_channel_index"]
        self._selected_channel_rms = channel_meta["selected_channel_rms"]
        self._captured_channel_rms = list(channel_meta["channel_rms"])
        write_wav_pcm16(path=output_path, waveform=mono_waveform, sample_rate=self._sample_rate)
        return {
            "mode": "push_to_talk_recorded_microphone",
            "input_device_index": self._input_device_index,
            "input_device_name": self._input_device_name,
            "input_device_channels": self._input_device_channels,
            "record_channels": self._record_channels,
            "selected_channel_index": self._selected_channel_index,
            "selected_channel_rms": self._selected_channel_rms,
            "channel_rms": self._captured_channel_rms,
            "sample_rate": self._sample_rate,
            "duration_sec": float(duration_sec),
            "num_samples": int(mono_waveform.shape[0]),
            "audio_path": str(output_path),
            "capture_diagnostics": capture_diagnostics,
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
            self._selected_channel_index = None
            self._selected_channel_rms = None
            self._captured_channel_rms = []
            self._callback_count = 0
            self._callback_frames = 0
            self._overflow_count = 0
            self._first_callback_at = None
            self._last_callback_at = None


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
    expected_asr_language: str | None = DEFAULT_PILOT_ASR_LANGUAGE,
    pilot_hybrid_timeout_sec: float = DEFAULT_PILOT_HYBRID_TIMEOUT_SEC,
    pilot_gateway_topk: int = DEFAULT_PILOT_GATEWAY_TOPK,
    pilot_gateway_candidate_k: int = DEFAULT_PILOT_GATEWAY_CANDIDATE_K,
    pilot_max_entities_per_doc: int = DEFAULT_PILOT_MAX_ENTITIES_PER_DOC,
    hud_hook_json: Path | None = None,
    tesseract_bin: str = DEFAULT_PILOT_TESSERACT_BIN,
    service_token: str | None = None,
    playback_enabled: bool = True,
    capture_func: Callable[..., dict[str, Any]] = capture_screen_image,
    session_probe_func: Callable[..., dict[str, Any]] = probe_atm10_session,
    live_hud_state_func: Callable[..., dict[str, Any]] = build_live_hud_state,
    asr_func: Callable[..., dict[str, Any]] = call_voice_asr,
    hybrid_query_func: Callable[..., dict[str, Any]] = call_gateway_hybrid_query,
    tts_func: Callable[..., dict[str, Any]] = synthesize_with_tts_runtime,
    pre_captured_screenshot_path: Path | None = None,
    pre_captured_capture_payload: Mapping[str, Any] | None = None,
    pre_captured_capture_error: str | None = None,
    pre_captured_vision_future: Future[dict[str, Any]] | None = None,
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
        "request": {
            "hotkey": hotkey,
            "hud_hook_json": None if hud_hook_json is None else str(hud_hook_json),
        },
        "audio": {
            **dict(audio_input_meta or {}),
            "signal": {"status": "not_started", "raw": None, "asr_input": None},
            "asr_preprocess": {"status": "not_started", "mode": None, "gain_applied": 1.0},
        },
        "capture": {
            "monitor_index": capture_monitor,
            "region": format_capture_region(capture_region),
            "screenshot_path": None,
            "capture_backend": None,
            "window_handle": None,
            "window_title": None,
            "window_bounds": None,
            "prefetched_frame_match": None,
            "error": None,
        },
        "session": {
            "schema_version": ATM10_SESSION_PROBE_SCHEMA,
            "status": "not_started",
            "window_found": False,
            "process_name": None,
            "window_title": None,
            "foreground": False,
            "window_bounds": None,
            "capture_target_kind": capture_target_kind(
                capture_monitor=capture_monitor,
                capture_region=capture_region,
            ),
            "capture_bbox": None,
            "capture_intersects_window": None,
            "atm10_probable": False,
            "reason_codes": [],
        },
        "hud_state": {
            "schema_version": LIVE_HUD_STATE_SCHEMA,
            "status": "not_started",
            "sources": {},
            "hud_lines": [],
            "quest_updates": [],
            "player_state": {},
            "context_tags": [],
            "text_preview": "",
            "hud_line_count": 0,
            "quest_update_count": 0,
            "has_player_state": False,
            "reason_codes": [],
        },
        "vision": {"summary": None, "next_steps": [], "input_image": None, "error": None},
        "hybrid": {"planner_status": None, "degraded": None, "warnings": [], "citations": [], "error": None},
        "grounded_reply": {"answer_text": None, "cited_entities": [], "answer_language": None, "error": None},
        "tts": {"status": "not_started", "error": None},
        "transcript_quality": {
            "status": "not_started",
            "reason_codes": [],
            "expected_language": str(expected_asr_language or "").strip().lower() or None,
            "detected_language": None,
            "audio_signal_status": None,
            "transcript_used": False,
        },
        "reply_mode": "not_started",
        "answer_language": None,
        "degraded_flags": [],
        "degraded_services": [],
        "latency": {},
        "paths": {
            "turn_dir": str(turn_dir),
            "turn_json": str(turn_json_path),
            "audio_input_wav": str(copied_audio_path),
            "audio_asr_wav": str(copied_audio_path),
            "screenshot_png": str(turn_dir / "screenshot.png"),
            "vision_input_png": str(turn_dir / "vision_input.png"),
            "session_probe_json": str(turn_dir / "session_probe.json"),
            "live_hud_state_json": str(turn_dir / "live_hud_state.json"),
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
        capture_attempt_errors: list[dict[str, str]] = []
        prefetched_payload = (
            dict(pre_captured_capture_payload)
            if isinstance(pre_captured_capture_payload, Mapping)
            else None
        )
        prefetched_path = Path(pre_captured_screenshot_path) if pre_captured_screenshot_path is not None else None
        if isinstance(pre_captured_capture_error, str) and pre_captured_capture_error.strip():
            base_payload["capture"]["prefetch_error"] = pre_captured_capture_error.strip()
        if prefetched_path is not None and prefetched_path.is_file():
            base_payload["capture"]["prefetched_screenshot_path"] = str(prefetched_path)
        window_capture_candidate: dict[str, Any] | None = None
        if capture_region is None:
            try:
                candidate = find_best_atm10_window()
            except Exception as exc:
                base_payload["capture"]["window_candidate_error"] = str(exc)
            else:
                if isinstance(candidate, Mapping) and bool(candidate.get("foreground")):
                    window_capture_candidate = dict(candidate)
                elif isinstance(candidate, Mapping):
                    base_payload["capture"]["window_candidate_skipped"] = "atm10_window_not_foreground"
        capture_attempts: list[dict[str, Any]] = [{"attempt_name": "desktop", "kwargs": {}}]
        if window_capture_candidate is not None:
            capture_attempts.append(
                {
                    "attempt_name": "atm10_window",
                    "kwargs": {
                        "window_handle": int(window_capture_candidate.get("hwnd", 0)),
                        "window_title": str(window_capture_candidate.get("window_title", "")).strip() or None,
                        "window_bounds": window_capture_candidate.get("window_bounds"),
                    },
                }
            )

        last_capture_error: Exception | None = None
        for attempt in capture_attempts:
            attempt_name = str(attempt.get("attempt_name", "capture")).strip() or "capture"
            attempt_kwargs = attempt.get("kwargs")
            attempt_kwargs = dict(attempt_kwargs) if isinstance(attempt_kwargs, Mapping) else {}
            try:
                capture_payload = capture_func(
                    output_path=screenshot_path,
                    monitor_index=capture_monitor,
                    region=capture_region,
                    **attempt_kwargs,
                )
                capture_payload = dict(capture_payload)
                capture_payload["capture_source"] = "hotkey_up_capture"
                if capture_attempt_errors:
                    capture_payload["attempt_errors"] = list(capture_attempt_errors)
                base_payload["capture"] = {
                    **base_payload["capture"],
                    **capture_payload,
                    "error": None,
                }
                break
            except Exception as exc:
                last_capture_error = exc
                capture_attempt_errors.append({"attempt": attempt_name, "error": str(exc)})
        if capture_payload is None:
            if (
                prefetched_payload is not None
                and prefetched_path is not None
                and prefetched_path.is_file()
            ):
                shutil.copyfile(prefetched_path, screenshot_path)
                prefetched_payload["screenshot_path"] = str(screenshot_path)
                prefetched_payload["capture_source"] = "hotkey_down_prefetch_fallback"
                prefetched_payload["prefetch_fallback_reason"] = (
                    str(last_capture_error) if last_capture_error is not None else "live capture failed"
                )
                capture_payload = dict(prefetched_payload)
                if capture_attempt_errors:
                    capture_payload["attempt_errors"] = list(capture_attempt_errors)
                base_payload["capture"] = {
                    **base_payload["capture"],
                    **capture_payload,
                    "error": None,
                }
            else:
                error_text = str(last_capture_error) if last_capture_error is not None else "live capture failed"
                stage_errors["capture"] = error_text
                degraded_flags.append("capture_failed")
                degraded_flags.append("vision_unavailable")
                base_payload["capture"]["error"] = error_text
                if capture_attempt_errors:
                    base_payload["capture"]["attempt_errors"] = list(capture_attempt_errors)

        base_payload["latency"]["capture_sec"] = round(perf_counter() - stage_started, 6)

        stage_started = perf_counter()
        session_probe_path = Path(base_payload["paths"]["session_probe_json"])
        session_capture_kind = capture_target_kind(
            capture_monitor=capture_monitor,
            capture_region=capture_region,
            capture_payload=capture_payload,
        )
        session_capture_bbox = (
            capture_payload.get("bbox")
            if isinstance(capture_payload, Mapping)
            else None
        )
        try:
            session_payload = session_probe_func(
                capture_target_kind=session_capture_kind,
                capture_bbox=session_capture_bbox,
                now=effective_now,
            )
            base_payload["session"] = dict(session_payload)
            _write_json(session_probe_path, session_payload)
            if not bool(session_payload.get("atm10_probable")):
                degraded_flags.append("session_target_not_confirmed")
        except Exception as exc:
            stage_errors["session"] = str(exc)
            degraded_flags.append("session_probe_failed")
            error_payload = {
                "schema_version": ATM10_SESSION_PROBE_SCHEMA,
                "checked_at_utc": _utc_now(),
                "status": "error",
                "window_found": False,
                "process_name": None,
                "window_title": None,
                "foreground": False,
                "window_bounds": None,
                "capture_target_kind": session_capture_kind,
                "capture_bbox": session_capture_bbox,
                "capture_intersects_window": None,
                "atm10_probable": False,
                "reason_codes": ["session_probe_failed"],
                "error": str(exc),
            }
            base_payload["session"] = error_payload
            _write_json(session_probe_path, error_payload)
        base_payload["latency"]["session_sec"] = round(perf_counter() - stage_started, 6)

        stage_started = perf_counter()
        live_hud_state_path = Path(base_payload["paths"]["live_hud_state_json"])
        try:
            hud_payload = live_hud_state_func(
                screenshot_path=screenshot_path,
                hook_json=hud_hook_json,
                tesseract_bin=tesseract_bin,
                now=effective_now,
            )
            base_payload["hud_state"] = dict(hud_payload)
            _write_json(live_hud_state_path, hud_payload)
            if str(hud_payload.get("status", "")).strip().lower() == "error":
                degraded_flags.append("hud_state_error")
        except Exception as exc:
            stage_errors["hud_state"] = str(exc)
            degraded_flags.append("hud_state_unavailable")
            error_payload = {
                "schema_version": LIVE_HUD_STATE_SCHEMA,
                "checked_at_utc": _utc_now(),
                "status": "error",
                "screenshot_path": str(screenshot_path),
                "sources": {},
                "hud_lines": [],
                "quest_updates": [],
                "player_state": {},
                "context_tags": [],
                "text_preview": "",
                "hud_line_count": 0,
                "quest_update_count": 0,
                "has_player_state": False,
                "reason_codes": ["hud_state_unavailable"],
                "error": str(exc),
            }
            base_payload["hud_state"] = error_payload
            _write_json(live_hud_state_path, error_payload)
        base_payload["latency"]["hud_state_sec"] = round(perf_counter() - stage_started, 6)

        asr_stage_started = perf_counter()
        asr_audio_path = copied_audio_path
        try:
            prepared_audio = _prepare_asr_audio_input(audio_path=copied_audio_path, turn_dir=turn_dir)
            base_payload["audio"]["signal"] = prepared_audio["signal"]
            base_payload["audio"]["asr_preprocess"] = prepared_audio["asr_preprocess"]
            asr_audio_path = Path(str(prepared_audio["audio_path"]))
            base_payload["paths"]["audio_asr_wav"] = str(asr_audio_path)
        except Exception as exc:
            degraded_flags.append("audio_signal_analysis_failed")
            base_payload["audio"]["signal"] = {
                "status": "error",
                "raw": None,
                "asr_input": None,
                "error": str(exc),
            }
            base_payload["audio"]["asr_preprocess"] = {
                "status": "error",
                "mode": "copy",
                "gain_applied": 1.0,
                "error": str(exc),
            }

        provisional_vision_language = _infer_reply_language(
            transcript="",
            transcript_language=expected_asr_language,
        )
        vision_input_path = Path(base_payload["paths"]["vision_input_png"])
        short_audio_for_asr = _is_audio_signal_too_short_for_asr(base_payload["audio"].get("signal"))
        reuse_prefetched_vision = False
        if (
            not short_audio_for_asr
            and
            pre_captured_vision_future is not None
            and prefetched_path is not None
            and prefetched_path.is_file()
            and capture_payload is not None
            and screenshot_path.is_file()
        ):
            try:
                if str(base_payload["capture"].get("capture_source", "")).strip() == "hotkey_down_prefetch_fallback":
                    base_payload["capture"]["prefetched_frame_match"] = {
                        "status": "ok",
                        "mode": "prefetch_capture_fallback",
                        "compare_edge": 0,
                        "mean_abs_diff": 0.0,
                        "max_mean_abs_diff": float(_PREFETCH_VISION_REUSE_MAX_MEAN_ABS_DIFF),
                        "reusable": True,
                    }
                else:
                    base_payload["capture"]["prefetched_frame_match"] = _compare_capture_frames(
                        reference_path=prefetched_path,
                        candidate_path=screenshot_path,
                    )
                reuse_prefetched_vision = bool(base_payload["capture"]["prefetched_frame_match"].get("reusable"))
            except Exception as exc:
                base_payload["capture"]["prefetched_frame_match_error"] = str(exc)
        live_vision_executor: ThreadPoolExecutor | None = None
        live_vision_future: Future[dict[str, Any]] | None = None
        if not short_audio_for_asr and not reuse_prefetched_vision:
            live_vision_executor = ThreadPoolExecutor(max_workers=1)
            live_vision_future = live_vision_executor.submit(
                _run_vision_stage,
                screenshot_path=screenshot_path,
                capture_payload=capture_payload,
                vision_input_path=vision_input_path,
                preferred_language=provisional_vision_language,
                vlm_client=vlm_client,
            )
        if short_audio_for_asr:
            transcript = ""
            language = ""
            transcript_quality = {
                "status": "low_signal",
                "reason_codes": ["audio_too_short", "audio_signal_low", "empty"],
                "expected_language": str(expected_asr_language or "").strip().lower() or None,
                "detected_language": None,
                "audio_signal_status": str(base_payload["audio"].get("signal", {}).get("raw", {}).get("status", "")).strip().lower() or None,
                "transcript_used": False,
            }
            degraded_flags.append("transcript_low_signal")
            degraded_flags.append("transcript_empty")
            base_payload["latency"]["asr_sec"] = 0.0
        else:
            asr_result = _run_asr_stage(
                voice_runtime_url=voice_runtime_url,
                asr_audio_path=asr_audio_path,
                expected_asr_language=expected_asr_language,
                service_token=service_token,
                asr_func=asr_func,
            )
            transcript = str(asr_result.get("transcript", "")).strip()
            language = str(asr_result.get("language", "")).strip()
            if asr_result.get("error"):
                stage_errors["asr"] = str(asr_result["error"])
            degraded_flags.extend([str(item) for item in asr_result.get("degraded_flags", []) if str(item).strip()])

            transcript_quality = _evaluate_transcript_quality(
                transcript=transcript,
                transcript_language=language,
                expected_language=expected_asr_language,
                audio_signal=base_payload["audio"].get("signal"),
            )
            if transcript_quality["status"] != "ok":
                degraded_flags.append("transcript_low_signal")
            if "empty" in transcript_quality["reason_codes"]:
                degraded_flags.append("transcript_empty")
            base_payload["latency"]["asr_sec"] = round(perf_counter() - asr_stage_started, 6)

        base_payload["request"]["transcript"] = transcript
        base_payload["request"]["language"] = language
        base_payload["transcript_quality"] = transcript_quality

        transcript_for_answer = transcript if bool(base_payload["transcript_quality"].get("transcript_used")) else ""
        preferred_language_hint = language if transcript_for_answer else (expected_asr_language or language)
        preferred_reply_language = _infer_reply_language(
            transcript=transcript_for_answer,
            transcript_language=preferred_language_hint,
        )
        visual_observation_request = bool(transcript_for_answer) and _looks_like_visual_observation_request(
            transcript_for_answer
        )
        short_screen_grounded_request = bool(transcript_for_answer) and _looks_like_short_screen_grounded_request(
            transcript_for_answer
        )

        if short_audio_for_asr:
            vision_result = {
                "input_image": None,
                "vision_payload": None,
                "visual_summary": "",
                "error": None,
                "degraded_flags": [],
                "latency_sec": 0.0,
                "source": "skipped_low_signal_v1",
            }
        elif reuse_prefetched_vision and pre_captured_vision_future is not None:
            vision_result = _resolve_prefetched_vision_result(
                prefetched_future=pre_captured_vision_future,
                screenshot_path=screenshot_path,
                capture_payload=capture_payload,
                vision_input_path=vision_input_path,
                preferred_language=provisional_vision_language,
                vlm_client=vlm_client,
            )
        elif live_vision_future is not None:
            try:
                vision_result = live_vision_future.result()
            except Exception as exc:
                vision_result = {
                    "input_image": None,
                    "vision_payload": None,
                    "visual_summary": "",
                    "error": str(exc),
                    "degraded_flags": ["vlm_failed"],
                    "latency_sec": 0.0,
                    "source": "live_capture_v1",
                }
        else:
            vision_result = _run_vision_stage(
                screenshot_path=screenshot_path,
                capture_payload=capture_payload,
                vision_input_path=vision_input_path,
                preferred_language=provisional_vision_language,
                vlm_client=vlm_client,
            )
        if live_vision_executor is not None:
            live_vision_executor.shutdown(wait=True)

        visual_summary = str(vision_result.get("visual_summary", "")).strip()
        vision_payload = vision_result.get("vision_payload")
        input_image_payload = vision_result.get("input_image")
        vision_source = str(vision_result.get("source", "")).strip() or None
        if isinstance(input_image_payload, Mapping):
            base_payload["vision"]["input_image"] = dict(input_image_payload)
        if vision_result.get("error"):
            stage_errors["vision"] = str(vision_result["error"])
            base_payload["vision"]["error"] = str(vision_result["error"])
            if vision_source:
                base_payload["vision"]["source"] = vision_source
        elif isinstance(vision_payload, dict):
            base_payload["vision"] = {
                **base_payload["vision"],
                **vision_payload,
                **({"source": vision_source} if vision_source else {}),
                "error": None,
            }
        elif vision_source:
            base_payload["vision"]["source"] = vision_source
        degraded_flags.extend([str(item) for item in vision_result.get("degraded_flags", []) if str(item).strip()])
        base_payload["latency"]["vision_sec"] = float(vision_result.get("latency_sec", 0.0) or 0.0)

        stage_started = perf_counter()
        local_context_summary = _compose_local_context_summary(
            visual_summary=visual_summary,
            session_payload=base_payload.get("session"),
            hud_payload=base_payload.get("hud_state"),
        )
        gateway_result: dict[str, Any] | None = None
        hybrid_summary: dict[str, Any]
        citations: list[dict[str, Any]]
        if gateway_url is None:
            stage_errors["hybrid"] = "gateway URL is not configured"
            degraded_flags.append("hybrid_unconfigured")
            hybrid_summary, citations = _summarize_hybrid_payload(None)
        elif not transcript_for_answer:
            if str(base_payload["transcript_quality"].get("status", "")).strip() == "low_signal":
                stage_errors["hybrid"] = "hybrid_query skipped because transcript is low-signal"
                degraded_flags.append("hybrid_skipped_low_signal")
            else:
                stage_errors["hybrid"] = "hybrid_query skipped because transcript is empty"
                degraded_flags.append("hybrid_skipped_no_transcript")
            hybrid_summary, citations = _summarize_hybrid_payload(None)
        elif visual_observation_request:
            hybrid_summary = {
                "planner_status": "skipped_visual_observation",
                "degraded": False,
                "warnings": ["visual_observation_request"],
                "results_count": 0,
                "retrieval_results_count": 0,
                "kag_results_count": 0,
            }
            citations = []
        elif short_screen_grounded_request and bool(local_context_summary or visual_summary):
            hybrid_summary = {
                "planner_status": "skipped_screen_grounded",
                "degraded": False,
                "warnings": ["screen_grounded_request"],
                "results_count": 0,
                "retrieval_results_count": 0,
                "kag_results_count": 0,
            }
            citations = []
        else:
            try:
                gateway_result = hybrid_query_func(
                    gateway_url=gateway_url,
                    query=transcript_for_answer,
                    timeout_sec=pilot_hybrid_timeout_sec,
                    topk=pilot_gateway_topk,
                    candidate_k=pilot_gateway_candidate_k,
                    max_entities_per_doc=pilot_max_entities_per_doc,
                    service_token=service_token,
                )
            except Exception as exc:
                stage_errors["hybrid"] = str(exc)
                degraded_flags.append("hybrid_query_failed")
                degraded_flags.append("hybrid_fast_fail")
            hybrid_summary, citations = _summarize_hybrid_payload(gateway_result)
            if bool(hybrid_summary.get("degraded")):
                degraded_flags.append("hybrid_degraded")
                degraded_flags.append("hybrid_fast_fail")
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
        reply_mode = "normal_local"
        skip_grounded_reply_for_low_signal = str(base_payload["transcript_quality"].get("status", "")).strip() == "low_signal"
        if not transcript_for_answer:
            reply_mode = "visual_only_fallback"
        if skip_grounded_reply_for_low_signal:
            degraded_flags.append("grounded_reply_skipped_low_signal")
            grounded_reply_payload = {
                "provider": "low_signal_retry_v1",
                "model": "fallback",
                "device": "local",
                "prompt": "",
                "answer_text": build_low_signal_retry_answer(
                    preferred_language=preferred_reply_language,
                ),
                "cited_entities": [],
                "degraded_flags": list(sorted(dict.fromkeys(degraded_flags))),
                "answer_language": preferred_reply_language,
                "raw_response_text": "",
            }
            reply_mode = "low_signal_retry"
        elif visual_observation_request and bool(local_context_summary or visual_summary):
            grounded_reply_payload = {
                "provider": "visual_observation_direct_v1",
                "model": "fallback",
                "device": "local",
                "prompt": "",
                "answer_text": build_visual_observation_answer(
                    visual_summary=visual_summary or local_context_summary,
                    preferred_language=preferred_reply_language,
                ),
                "cited_entities": [],
                "degraded_flags": [],
                "answer_language": preferred_reply_language,
                "raw_response_text": "",
            }
            reply_mode = "visual_observation_direct"
        elif short_screen_grounded_request and bool(local_context_summary or visual_summary):
            grounded_reply_payload = {
                "provider": "screen_grounded_direct_v1",
                "model": "fallback",
                "device": "local",
                "prompt": "",
                "answer_text": build_visual_observation_answer(
                    visual_summary=local_context_summary or visual_summary,
                    preferred_language=preferred_reply_language,
                ),
                "cited_entities": [],
                "degraded_flags": [],
                "answer_language": preferred_reply_language,
                "raw_response_text": "",
            }
            reply_mode = "screen_grounded_direct"
        elif grounded_reply_client is not None:
            try:
                grounded_reply_payload = grounded_reply_client.generate_reply(
                    transcript=transcript_for_answer,
                    visual_summary=local_context_summary or visual_summary,
                    citations=citations,
                    hybrid_summary=hybrid_summary,
                    degraded_flags=list(sorted(dict.fromkeys(degraded_flags))),
                    preferred_language=preferred_reply_language,
                )
            except Exception as exc:
                stage_errors["grounded_reply"] = str(exc)
                degraded_flags.append("grounded_reply_failed")
        else:
            stage_errors["grounded_reply"] = "local grounded reply provider is unavailable"
            degraded_flags.append("grounded_reply_unavailable")
        if grounded_reply_payload is None:
            grounded_reply_payload = {
                "provider": "deterministic_fallback_v1",
                "model": "fallback",
                "device": "local",
                "prompt": "",
                "answer_text": build_fallback_answer(
                    transcript=transcript_for_answer,
                    visual_summary=local_context_summary or visual_summary,
                    citations=citations,
                    degraded_flags=list(sorted(dict.fromkeys(degraded_flags))),
                    stage_errors=stage_errors,
                    preferred_language=preferred_reply_language,
                ),
                "cited_entities": [
                    str(item.get("title", "")).strip()
                    for item in citations[:3]
                    if str(item.get("title", "")).strip()
                ],
                "degraded_flags": list(sorted(dict.fromkeys(degraded_flags))),
                "answer_language": preferred_reply_language,
                "raw_response_text": "",
            }
            reply_mode = "fallback_answer"
        provider_degraded_flags = [
            str(item)
            for item in grounded_reply_payload.get("degraded_flags", [])
            if str(item).strip()
            and str(item).strip()
            not in {"grounded_reply_answer_sentence_capped", "grounded_reply_answer_truncated"}
        ]
        degraded_flags.extend(provider_degraded_flags)
        answer_text = str(grounded_reply_payload.get("answer_text", "")).strip()
        sanitized_answer_text, answer_sanitization_flags = sanitize_grounded_reply_answer_text(answer_text)
        degraded_flags.extend(
            [
                flag
                for flag in answer_sanitization_flags
                if flag not in {"grounded_reply_answer_sentence_capped", "grounded_reply_answer_truncated"}
            ]
        )
        grounded_reply_payload["degraded_flags"] = list(
            sorted(dict.fromkeys([*provider_degraded_flags, *answer_sanitization_flags]))
        )
        current_degraded_flags = list(sorted(dict.fromkeys(degraded_flags)))
        if answer_text and not sanitized_answer_text:
            degraded_flags.append("grounded_reply_answer_fallback")
            grounded_reply_payload["degraded_flags"] = list(
                sorted(dict.fromkeys([*grounded_reply_payload["degraded_flags"], "grounded_reply_answer_fallback"]))
            )
            current_degraded_flags = list(sorted(dict.fromkeys(degraded_flags)))
        answer_text = sanitized_answer_text
        if not answer_text:
            answer_text = build_fallback_answer(
                transcript=transcript_for_answer,
                visual_summary=local_context_summary or visual_summary,
                citations=citations,
                degraded_flags=current_degraded_flags,
                stage_errors=stage_errors,
                preferred_language=preferred_reply_language,
            )
            reply_mode = "fallback_answer"
        answer_text, spoken_answer_flags = _finalize_spoken_answer_text(answer_text)
        grounded_reply_payload["degraded_flags"] = list(
            sorted(dict.fromkeys([*grounded_reply_payload["degraded_flags"], *spoken_answer_flags]))
        )
        if not answer_text:
            answer_text = build_fallback_answer(
                transcript="",
                visual_summary=local_context_summary or visual_summary,
                citations=citations,
                degraded_flags=list(sorted(dict.fromkeys(degraded_flags))),
                stage_errors=stage_errors,
                preferred_language=preferred_reply_language,
            )
            answer_text, fallback_finalize_flags = _finalize_spoken_answer_text(answer_text)
            grounded_reply_payload["degraded_flags"] = list(
                sorted(
                    dict.fromkeys(
                        [
                            *grounded_reply_payload["degraded_flags"],
                            "grounded_reply_answer_fallback",
                            *fallback_finalize_flags,
                        ]
                    )
                )
            )
            reply_mode = "fallback_answer"
        grounded_reply_payload["answer_text"] = answer_text
        grounded_reply_payload["answer_language"] = preferred_reply_language
        base_payload["grounded_reply"] = {
            **grounded_reply_payload,
            "error": stage_errors.get("grounded_reply"),
        }
        base_payload["answer_text"] = answer_text
        base_payload["reply_mode"] = reply_mode
        base_payload["answer_language"] = preferred_reply_language
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
                    language=preferred_reply_language,
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
    max_new_tokens: int,
) -> Any:
    normalized_provider = str(provider_name).strip().lower()
    if provider_kind == "vlm":
        if normalized_provider == "stub":
            return DeterministicStubVLM()
        if normalized_provider == "openvino":
            return OpenVINOVLMClient.from_pretrained(
                model_dir=model_dir,
                device=device,
                max_new_tokens=max_new_tokens,
            )
        raise ValueError("pilot VLM provider must be one of: openvino, stub.")
    if normalized_provider == "stub":
        return DeterministicGroundedReplyStub()
    if normalized_provider == "openvino":
        return OpenVINOGroundedReplyClient.from_pretrained(
            model_dir=model_dir,
            device=device,
            max_new_tokens=max_new_tokens,
        )
    raise ValueError("pilot text provider must be one of: openvino, stub.")


def run_pilot_runtime_loop(
    *,
    runs_dir: Path,
    host_profile: Mapping[str, Any] | None = None,
    gateway_url: str | None,
    voice_runtime_url: str | None,
    tts_runtime_url: str | None,
    hotkey: str,
    input_device_index: int | None = None,
    capture_monitor: int | None,
    capture_region: tuple[int, int, int, int] | None,
    hud_hook_json: Path | None,
    tesseract_bin: str,
    pilot_vlm_model_dir: Path,
    pilot_text_model_dir: Path,
    pilot_vlm_device: str,
    pilot_text_device: str,
    pilot_vlm_provider: str = "openvino",
    pilot_text_provider: str = "openvino",
    pilot_vlm_max_new_tokens: int = DEFAULT_PILOT_VLM_MAX_NEW_TOKENS,
    pilot_text_max_new_tokens: int = DEFAULT_PILOT_TEXT_MAX_NEW_TOKENS,
    asr_language: str | None = DEFAULT_PILOT_ASR_LANGUAGE,
    asr_max_new_tokens: int = DEFAULT_PILOT_ASR_MAX_NEW_TOKENS,
    asr_warmup_requested: bool = False,
    asr_warmup_language: str | None = DEFAULT_PILOT_ASR_LANGUAGE,
    pilot_hybrid_timeout_sec: float = DEFAULT_PILOT_HYBRID_TIMEOUT_SEC,
    pilot_gateway_topk: int = DEFAULT_PILOT_GATEWAY_TOPK,
    pilot_gateway_candidate_k: int = DEFAULT_PILOT_GATEWAY_CANDIDATE_K,
    pilot_max_entities_per_doc: int = DEFAULT_PILOT_MAX_ENTITIES_PER_DOC,
    sample_rate: int = DEFAULT_PILOT_SAMPLE_RATE,
    poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC,
    service_token: str | None = None,
    playback_enabled: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    effective_now = now or datetime.now(timezone.utc)
    resolved_host_profile = _resolve_runtime_host_profile_payload(host_profile)
    runtime_run_dir = _create_run_dir(runs_dir, effective_now)
    latest_status_path = pilot_runtime_latest_status_path(runs_dir)
    run_json_path = runtime_run_dir / "run.json"

    run_payload: dict[str, Any] = {
        "schema_version": PILOT_RUNTIME_SCHEMA,
        "timestamp_utc": effective_now.astimezone(timezone.utc).isoformat(),
        "mode": "pilot_runtime_loop",
        "status": "running",
        "host_profile": resolved_host_profile,
        "paths": {
            "run_dir": str(runtime_run_dir),
            "run_json": str(run_json_path),
            "status_json": str(runtime_run_dir / "pilot_runtime_status.json"),
            "latest_status_json": str(latest_status_path),
            **return_paths(runs_dir),
        },
        "config": {
            "host_profile_id": resolved_host_profile.get("id"),
            "gateway_url": gateway_url,
            "voice_runtime_url": voice_runtime_url,
            "tts_runtime_url": tts_runtime_url,
            "hotkey": hotkey,
            "input_device_index": input_device_index,
            "capture_monitor": capture_monitor,
            "capture_region": format_capture_region(capture_region),
            "hud_hook_json": None if hud_hook_json is None else str(hud_hook_json),
            "tesseract_bin": tesseract_bin,
            "pilot_vlm_model_dir": str(pilot_vlm_model_dir),
            "pilot_text_model_dir": str(pilot_text_model_dir),
            "pilot_vlm_device": pilot_vlm_device,
            "pilot_text_device": pilot_text_device,
            "pilot_vlm_provider": pilot_vlm_provider,
            "pilot_text_provider": pilot_text_provider,
            "pilot_vlm_max_new_tokens": int(pilot_vlm_max_new_tokens),
            "pilot_text_max_new_tokens": int(pilot_text_max_new_tokens),
            "asr_language": asr_language,
            "asr_max_new_tokens": int(asr_max_new_tokens),
            "asr_warmup_request": bool(asr_warmup_requested),
            "asr_warmup_language": asr_warmup_language,
            "pilot_hybrid_timeout_sec": float(pilot_hybrid_timeout_sec),
            "pilot_gateway_topk": int(pilot_gateway_topk),
            "pilot_gateway_candidate_k": int(pilot_gateway_candidate_k),
            "pilot_max_entities_per_doc": int(pilot_max_entities_per_doc),
            "sample_rate": int(sample_rate),
            "poll_interval_sec": float(poll_interval_sec),
            "playback_enabled": bool(playback_enabled),
        },
        "provider_init": {},
        "last_turn": None,
        "last_return_event": None,
        "return_loop_state": reset_return_loop_state(suppress_first_occurrence=True),
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
            max_new_tokens=pilot_vlm_max_new_tokens,
        )
        run_payload["provider_init"]["vlm"] = {
            "status": "ok",
            "provider": pilot_vlm_provider,
            "device": pilot_vlm_device,
            "model_dir": str(pilot_vlm_model_dir),
            "max_new_tokens": int(pilot_vlm_max_new_tokens),
            "warmup": {"requested": pilot_vlm_provider == "openvino", "ok": None, "error": None},
        }
    except Exception as exc:
        degraded_services.append("vlm")
        run_payload["provider_init"]["vlm"] = {
            "status": "error",
            "provider": pilot_vlm_provider,
            "device": pilot_vlm_device,
            "model_dir": str(pilot_vlm_model_dir),
            "max_new_tokens": int(pilot_vlm_max_new_tokens),
            "warmup": {"requested": pilot_vlm_provider == "openvino", "ok": None, "error": None},
            "error": str(exc),
        }

    try:
        grounded_reply_client = _build_provider(
            provider_name=pilot_text_provider,
            model_dir=pilot_text_model_dir,
            device=pilot_text_device,
            provider_kind="text",
            max_new_tokens=pilot_text_max_new_tokens,
        )
        run_payload["provider_init"]["text"] = {
            "status": "ok",
            "provider": pilot_text_provider,
            "device": pilot_text_device,
            "model_dir": str(pilot_text_model_dir),
            "max_new_tokens": int(pilot_text_max_new_tokens),
            "warmup": {"requested": pilot_text_provider == "openvino", "ok": None, "error": None},
        }
    except Exception as exc:
        degraded_services.append("text_core")
        run_payload["provider_init"]["text"] = {
            "status": "error",
            "provider": pilot_text_provider,
            "device": pilot_text_device,
            "model_dir": str(pilot_text_model_dir),
            "max_new_tokens": int(pilot_text_max_new_tokens),
            "warmup": {"requested": pilot_text_provider == "openvino", "ok": None, "error": None},
            "error": str(exc),
        }

    if gateway_url is None:
        degraded_services.append("gateway")
    if voice_runtime_url is None:
        degraded_services.append("voice_runtime_service")
    if tts_runtime_url is None:
        degraded_services.append("tts_runtime_service")

    if vlm_client is not None and pilot_vlm_provider == "openvino":
        try:
            run_payload["provider_init"]["vlm"]["warmup"] = _warmup_vlm_provider(
                vlm_client=vlm_client,
                runtime_run_dir=runtime_run_dir,
            )
        except Exception as exc:
            degraded_services.append("vlm")
            run_payload["provider_init"]["vlm"]["warmup"] = {
                "requested": True,
                "ok": False,
                "error": str(exc),
            }

    if grounded_reply_client is not None and pilot_text_provider == "openvino":
        try:
            run_payload["provider_init"]["text"]["warmup"] = _warmup_grounded_reply_provider(
                grounded_reply_client=grounded_reply_client,
            )
        except Exception as exc:
            degraded_services.append("text_core")
            run_payload["provider_init"]["text"]["warmup"] = {
                "requested": True,
                "ok": False,
                "error": str(exc),
            }

    status_handle = PilotRuntimeStatusHandle(
        runtime_run_dir=runtime_run_dir,
        latest_status_path=latest_status_path,
        host_profile=resolved_host_profile,
        hotkey=hotkey,
        gateway_url=gateway_url,
        voice_runtime_url=voice_runtime_url,
        tts_runtime_url=tts_runtime_url,
        input_device_index=input_device_index,
        asr_language=asr_language,
        asr_max_new_tokens=asr_max_new_tokens,
        asr_warmup_requested=asr_warmup_requested,
        capture_monitor=capture_monitor,
        capture_region=capture_region,
        vlm_model_dir=pilot_vlm_model_dir,
        text_model_dir=pilot_text_model_dir,
        vlm_provider=pilot_vlm_provider,
        text_provider=pilot_text_provider,
        pilot_vlm_max_new_tokens=pilot_vlm_max_new_tokens,
        pilot_text_max_new_tokens=pilot_text_max_new_tokens,
        pilot_hybrid_timeout_sec=pilot_hybrid_timeout_sec,
        provider_init=dict(run_payload["provider_init"]),
        degraded_services=sorted(dict.fromkeys(degraded_services)),
        last_return_event=None,
        return_loop_state=dict(run_payload["return_loop_state"]),
    )
    recorder: PushToTalkRecorder | None = None
    active_recording = False
    prefetched_capture_path: Path | None = None
    prefetched_capture_payload: dict[str, Any] | None = None
    prefetched_capture_error: str | None = None
    prefetched_vision_future: Future[dict[str, Any]] | None = None
    vision_prefetch_executor = ThreadPoolExecutor(max_workers=1) if vlm_client is not None else None

    try:
        hotkey_watcher = PollingHotkey(hotkey)
        recorder = PushToTalkRecorder(
            sample_rate=sample_rate,
            preferred_input_device_index=input_device_index,
        )
        temp_audio_path = runtime_run_dir / "live_recording.wav"
        status_handle.publish()
        _write_json(run_json_path, run_payload)
        while True:
            transition = hotkey_watcher.poll_transition()
            if transition == "down" and not active_recording:
                prefetched_capture_path = None
                prefetched_capture_payload = None
                prefetched_capture_error = None
                if prefetched_vision_future is not None and not prefetched_vision_future.done():
                    prefetched_vision_future.cancel()
                prefetched_vision_future = None
                try:
                    prefetch_path = runtime_run_dir / "tmp" / "hotkey_down_capture.png"
                    prefetch_payload = capture_screen_image(
                        output_path=prefetch_path,
                        monitor_index=capture_monitor,
                        region=capture_region,
                    )
                    prefetched_capture_path = prefetch_path
                    prefetched_capture_payload = dict(prefetch_payload)
                    if vision_prefetch_executor is not None and vlm_client is not None:
                        prefetched_vision_future = vision_prefetch_executor.submit(
                            _run_vision_stage,
                            screenshot_path=prefetch_path,
                            capture_payload=prefetched_capture_payload,
                            vision_input_path=runtime_run_dir / "tmp" / "hotkey_down_vision_input.png",
                            preferred_language=asr_language or asr_warmup_language or DEFAULT_PILOT_ASR_LANGUAGE,
                            vlm_client=vlm_client,
                        )
                except Exception as exc:
                    prefetched_capture_error = str(exc)
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
                    fallback_capture_error: str | None = None
                    try:
                        audio_meta = recorder.stop_to_wav(output_path=temp_audio_path)
                    except Exception as exc:
                        fallback_capture_error = str(exc)
                        if "No audio frames were captured during push-to-talk." not in fallback_capture_error:
                            raise
                        audio_meta = _write_silence_fallback_audio(
                            output_path=temp_audio_path,
                            sample_rate=sample_rate,
                            capture_error=fallback_capture_error,
                            input_device_index=(
                                int(getattr(recorder, "_input_device_index", input_device_index))
                                if getattr(recorder, "_input_device_index", None) is not None
                                else input_device_index
                            ),
                            input_device_name=getattr(recorder, "_input_device_name", None),
                            capture_diagnostics=recorder.capture_diagnostics(
                                duration_sec=perf_counter() - getattr(recorder, "_started_at", perf_counter()),
                                total_frames=0,
                            ),
                        )
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
                        expected_asr_language=asr_language or asr_warmup_language or DEFAULT_PILOT_ASR_LANGUAGE,
                        pilot_hybrid_timeout_sec=pilot_hybrid_timeout_sec,
                        pilot_gateway_topk=pilot_gateway_topk,
                        pilot_gateway_candidate_k=pilot_gateway_candidate_k,
                        pilot_max_entities_per_doc=pilot_max_entities_per_doc,
                        hud_hook_json=hud_hook_json,
                        tesseract_bin=tesseract_bin,
                        service_token=service_token,
                        playback_enabled=playback_enabled,
                        pre_captured_screenshot_path=prefetched_capture_path,
                        pre_captured_capture_payload=prefetched_capture_payload,
                        pre_captured_capture_error=prefetched_capture_error,
                        pre_captured_vision_future=prefetched_vision_future,
                        status_callback=lambda **kwargs: status_handle.transition(
                            state=str(kwargs.get("state", status_handle.state)),
                            degraded_services=status_handle.degraded_services,
                            last_error=status_handle.last_error,
                        ),
                    )
                    prefetched_capture_path = None
                    prefetched_capture_payload = None
                    prefetched_capture_error = None
                    prefetched_vision_future = None
                    turn_payload = turn_result["turn_payload"]
                    run_payload["last_turn"] = {
                        "turn_id": turn_payload.get("turn_id"),
                        "status": turn_payload.get("status"),
                        "turn_json": turn_payload.get("paths", {}).get("turn_json"),
                    }
                    return_loop_state, return_event = _maybe_emit_pilot_return_event(
                        runs_dir=runs_dir,
                        turn_payload=turn_payload,
                        loop_state=run_payload.get("return_loop_state"),
                    )
                    run_payload["return_loop_state"] = return_loop_state
                    if return_event is not None:
                        run_payload["last_return_event"] = return_event
                    run_payload["error"] = None
                    _write_json(run_json_path, run_payload)
                    turn_status = str(turn_payload.get("status", "")).strip().lower()
                    status_handle.transition(
                        state="idle",
                        degraded_services=sorted(
                            dict.fromkeys(
                                [
                                    *(status_handle.degraded_services or []),
                                    *turn_payload.get("degraded_services", []),
                                    *(
                                        ["voice_runtime_service"]
                                        if fallback_capture_error is not None and fallback_capture_error.strip()
                                        else []
                                    ),
                                ]
                            )
                        ),
                        last_error=turn_payload.get("error") or fallback_capture_error,
                        last_turn_payload=turn_payload,
                        last_return_event=(
                            return_event
                            if return_event is not None
                            else getattr(status_handle, "last_return_event", None)
                        ),
                        return_loop_state=return_loop_state,
                        status="degraded" if turn_status in {"degraded", "error"} else "running",
                    )
                    _emit_turn_console_summary(turn_payload)
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
        if active_recording and recorder is not None:
            recorder.discard()
        run_payload["status"] = "stopped"
        _write_json(run_json_path, run_payload)
        status_handle.transition(state="idle", status="stopped")
        return {"run_dir": runtime_run_dir, "run_payload": run_payload, "ok": True}
    except Exception as exc:
        if active_recording and recorder is not None:
            recorder.discard()
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_json(run_json_path, run_payload)
        status_handle.transition(state="idle", last_error=str(exc), status="error")
        return {"run_dir": runtime_run_dir, "run_payload": run_payload, "ok": False}
    finally:
        if vision_prefetch_executor is not None:
            vision_prefetch_executor.shutdown(wait=False, cancel_futures=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "--host-profile",
        choices=list_host_profile_ids(),
        default=DEFAULT_HOST_PROFILE_ID,
    )
    pre_args, _unknown = pre_parser.parse_known_args(argv)
    selected_host_profile = host_profile_payload(str(pre_args.host_profile))
    selected_defaults = dict(selected_host_profile.get("defaults") or {})
    parser = argparse.ArgumentParser(description="Local pilot runtime loop: push-to-talk -> ASR -> vision -> hybrid -> reply -> TTS.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs") / "pilot-runtime", help="Pilot runtime artifact root.")
    parser.add_argument(
        "--host-profile",
        choices=list_host_profile_ids(),
        default=str(selected_host_profile.get("id", DEFAULT_HOST_PROFILE_ID)),
        help="Machine/runtime host profile used to resolve pilot/runtime defaults.",
    )
    parser.add_argument("--gateway-url", type=str, default=DEFAULT_GATEWAY_URL, help="Gateway base URL.")
    parser.add_argument(
        "--voice-runtime-url",
        type=_optional_service_url,
        default=DEFAULT_VOICE_RUNTIME_URL,
        help="Voice runtime base URL. Use 'disabled' to force the runtime into an unconfigured state.",
    )
    parser.add_argument(
        "--tts-runtime-url",
        type=_optional_service_url,
        default=DEFAULT_TTS_RUNTIME_URL,
        help="TTS runtime base URL. Use 'disabled' to force the runtime into an unconfigured state.",
    )
    parser.add_argument("--pilot-hotkey", type=str, default=DEFAULT_PILOT_HOTKEY, help="Push-to-talk hotkey (Fx only).")
    parser.add_argument("--capture-monitor", type=int, default=None, help="Windows monitor index for live capture.")
    parser.add_argument(
        "--capture-region",
        type=str,
        default=None,
        help="Optional capture region formatted as x,y,w,h.",
    )
    parser.add_argument(
        "--hud-hook-json",
        type=Path,
        default=None,
        help="Optional path to the latest ATM10 HUD mod-hook payload JSON.",
    )
    parser.add_argument(
        "--tesseract-bin",
        type=str,
        default=DEFAULT_PILOT_TESSERACT_BIN,
        help="Tesseract binary name/path for additive HUD OCR (default: tesseract).",
    )
    parser.add_argument(
        "--pilot-vlm-model-dir",
        type=Path,
        default=Path(str(selected_defaults.get("pilot_vlm_model_dir", DEFAULT_HOST_PROFILE.pilot_vlm_model_dir))),
        help="Local VLM model dir.",
    )
    parser.add_argument(
        "--pilot-text-model-dir",
        type=Path,
        default=Path(str(selected_defaults.get("pilot_text_model_dir", DEFAULT_HOST_PROFILE.pilot_text_model_dir))),
        help="Local grounded reply model dir.",
    )
    parser.add_argument(
        "--pilot-vlm-device",
        type=str,
        default=str(selected_defaults.get("pilot_vlm_device", DEFAULT_PILOT_VLM_DEVICE)),
        help="OpenVINO device for pilot VLM.",
    )
    parser.add_argument(
        "--pilot-text-device",
        type=str,
        default=str(selected_defaults.get("pilot_text_device", DEFAULT_PILOT_TEXT_DEVICE)),
        help="OpenVINO device for grounded reply model.",
    )
    parser.add_argument(
        "--pilot-vlm-provider",
        choices=("openvino", "stub"),
        default=str(selected_defaults.get("pilot_vlm_provider", "openvino")),
        help="Pilot VLM provider (use stub only for diagnostics).",
    )
    parser.add_argument(
        "--pilot-text-provider",
        choices=("openvino", "stub"),
        default=str(selected_defaults.get("pilot_text_provider", "openvino")),
        help="Pilot grounded-reply provider (use stub only for diagnostics).",
    )
    parser.add_argument(
        "--pilot-vlm-max-new-tokens",
        type=int,
        default=int(selected_defaults.get("pilot_vlm_max_new_tokens", DEFAULT_PILOT_VLM_MAX_NEW_TOKENS)),
        help="VLM token budget for live pilot turns.",
    )
    parser.add_argument(
        "--pilot-text-max-new-tokens",
        type=int,
        default=int(selected_defaults.get("pilot_text_max_new_tokens", DEFAULT_PILOT_TEXT_MAX_NEW_TOKENS)),
        help="Grounded-reply token budget for live pilot turns.",
    )
    parser.add_argument(
        "--input-device-index",
        type=int,
        default=selected_defaults.get("pilot_input_device_index"),
        help="Optional explicit sounddevice input device index for push-to-talk capture.",
    )
    parser.add_argument(
        "--asr-language",
        type=str,
        default=str(selected_defaults.get("voice_asr_language", DEFAULT_PILOT_ASR_LANGUAGE)),
        help="Expected ASR language for live turns.",
    )
    parser.add_argument(
        "--asr-max-new-tokens",
        type=int,
        default=int(selected_defaults.get("voice_asr_max_new_tokens", DEFAULT_PILOT_ASR_MAX_NEW_TOKENS)),
        help="Observed ASR token budget for live turns.",
    )
    parser.add_argument(
        "--asr-warmup-request",
        action=argparse.BooleanOptionalAction,
        default=bool(selected_defaults.get("voice_asr_warmup_request", False)),
        help="Record that managed ASR warmup is expected for this live profile.",
    )
    parser.add_argument(
        "--asr-warmup-language",
        type=str,
        default=str(selected_defaults.get("voice_asr_warmup_language", DEFAULT_PILOT_ASR_LANGUAGE)),
        help="Language hint used by managed ASR warmup.",
    )
    parser.add_argument(
        "--pilot-hybrid-timeout-sec",
        type=float,
        default=float(selected_defaults.get("pilot_hybrid_timeout_sec", DEFAULT_PILOT_HYBRID_TIMEOUT_SEC)),
        help="Pilot-side timeout for opportunistic hybrid queries.",
    )
    parser.add_argument(
        "--pilot-gateway-topk",
        type=int,
        default=int(selected_defaults.get("pilot_gateway_topk", DEFAULT_PILOT_GATEWAY_TOPK)),
        help="Pilot hybrid top-k budget.",
    )
    parser.add_argument(
        "--pilot-gateway-candidate-k",
        type=int,
        default=int(selected_defaults.get("pilot_gateway_candidate_k", DEFAULT_PILOT_GATEWAY_CANDIDATE_K)),
        help="Pilot hybrid candidate-k budget.",
    )
    parser.add_argument(
        "--pilot-max-entities-per-doc",
        type=int,
        default=int(selected_defaults.get("pilot_max_entities_per_doc", DEFAULT_PILOT_MAX_ENTITIES_PER_DOC)),
        help="Pilot hybrid entity budget per document.",
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
    args = parser.parse_args(argv)
    args.host_profile_config = host_profile_payload(str(args.host_profile))
    return args


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
        host_profile=args.host_profile_config,
        gateway_url=args.gateway_url,
        voice_runtime_url=args.voice_runtime_url,
        tts_runtime_url=args.tts_runtime_url,
        hotkey=hotkey,
        input_device_index=args.input_device_index,
        capture_monitor=args.capture_monitor,
        capture_region=capture_region,
        hud_hook_json=args.hud_hook_json,
        tesseract_bin=args.tesseract_bin,
        pilot_vlm_model_dir=args.pilot_vlm_model_dir,
        pilot_text_model_dir=args.pilot_text_model_dir,
        pilot_vlm_device=args.pilot_vlm_device,
        pilot_text_device=args.pilot_text_device,
        pilot_vlm_provider=args.pilot_vlm_provider,
        pilot_text_provider=args.pilot_text_provider,
        pilot_vlm_max_new_tokens=args.pilot_vlm_max_new_tokens,
        pilot_text_max_new_tokens=args.pilot_text_max_new_tokens,
        asr_language=args.asr_language,
        asr_max_new_tokens=args.asr_max_new_tokens,
        asr_warmup_requested=args.asr_warmup_request,
        asr_warmup_language=args.asr_warmup_language,
        pilot_hybrid_timeout_sec=args.pilot_hybrid_timeout_sec,
        pilot_gateway_topk=args.pilot_gateway_topk,
        pilot_gateway_candidate_k=args.pilot_gateway_candidate_k,
        pilot_max_entities_per_doc=args.pilot_max_entities_per_doc,
        sample_rate=args.sample_rate,
        poll_interval_sec=args.poll_interval_sec,
        service_token=args.service_token,
        playback_enabled=not args.disable_tts_playback,
    )
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
