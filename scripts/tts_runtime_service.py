from __future__ import annotations

import argparse
import base64
import io
import ipaddress
import json
import os
import subprocess
import sys
import tempfile
import threading
import traceback
import wave
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.tts_runtime import (
    CallbackTTSEngine,
    PhraseCache,
    TTSRequest,
    TTSRuntimeError,
    TTSRuntimeService,
    make_silence_wav_bytes,
)
from scripts.gateway_artifact_policy import redact_error_entry

FastAPIRequest = Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


TTS_HTTP_DEFAULT_MAX_REQUEST_BODY_BYTES = 262_144
TTS_HTTP_DEFAULT_MAX_JSON_DEPTH = 8
TTS_HTTP_DEFAULT_MAX_STRING_LENGTH = 8_192
TTS_HTTP_DEFAULT_MAX_ARRAY_ITEMS = 256
TTS_HTTP_DEFAULT_MAX_OBJECT_KEYS = 256
_SERVICE_TOKEN_HEADER = "X-ATM10-Token"
_SERVICE_TOKEN_ENV = "ATM10_SERVICE_TOKEN"


@dataclass(frozen=True)
class TTSHTTPPolicy:
    max_request_body_bytes: int = TTS_HTTP_DEFAULT_MAX_REQUEST_BODY_BYTES
    max_json_depth: int = TTS_HTTP_DEFAULT_MAX_JSON_DEPTH
    max_string_length: int = TTS_HTTP_DEFAULT_MAX_STRING_LENGTH
    max_array_items: int = TTS_HTTP_DEFAULT_MAX_ARRAY_ITEMS
    max_object_keys: int = TTS_HTTP_DEFAULT_MAX_OBJECT_KEYS


class TTSPayloadLimitError(ValueError):
    def __init__(self, *, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-tts-service")
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


def _validate_http_policy(policy: TTSHTTPPolicy) -> None:
    if policy.max_request_body_bytes <= 0:
        raise ValueError("max_request_body_bytes must be > 0.")
    if policy.max_json_depth <= 0:
        raise ValueError("max_json_depth must be > 0.")
    if policy.max_string_length <= 0:
        raise ValueError("max_string_length must be > 0.")
    if policy.max_array_items <= 0:
        raise ValueError("max_array_items must be > 0.")
    if policy.max_object_keys <= 0:
        raise ValueError("max_object_keys must be > 0.")


def _resolve_service_token(cli_value: str | None) -> str | None:
    if cli_value is not None:
        stripped = cli_value.strip()
        return stripped or None
    env_value = os.getenv(_SERVICE_TOKEN_ENV, "").strip()
    return env_value or None


def _is_loopback_host(host: str) -> bool:
    normalized = str(host).strip()
    if not normalized:
        return False
    if normalized.lower() == "localhost":
        return True
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validate_bind_security(
    *,
    host: str,
    service_token: str | None,
    allow_insecure_no_token: bool,
) -> str | None:
    effective_service_token = _resolve_service_token(service_token)
    if effective_service_token is not None or allow_insecure_no_token or _is_loopback_host(host):
        return effective_service_token
    raise ValueError(
        "Refusing to start tts_runtime_service on a non-loopback host without a service token. "
        "Set --service-token / ATM10_SERVICE_TOKEN or pass --allow-insecure-no-token to opt into "
        "the insecure bind explicitly."
    )


def _is_authorized(request_headers: Mapping[str, Any], *, service_token: str | None) -> bool:
    if not service_token:
        return True
    presented = str(request_headers.get(_SERVICE_TOKEN_HEADER, "")).strip()
    return presented == service_token


def _raise_payload_limit_if_needed(value: Any, *, policy: TTSHTTPPolicy, depth: int = 1) -> None:
    if depth > policy.max_json_depth:
        raise TTSPayloadLimitError(
            error_code="payload_limit_exceeded",
            message=(
                "payload_limit_exceeded: "
                f"max_json_depth={policy.max_json_depth}, observed_depth={depth}"
            ),
        )
    if isinstance(value, str):
        if len(value) > policy.max_string_length:
            raise TTSPayloadLimitError(
                error_code="payload_limit_exceeded",
                message=(
                    "payload_limit_exceeded: "
                    f"max_string_length={policy.max_string_length}, observed_length={len(value)}"
                ),
            )
        return
    if isinstance(value, list):
        if len(value) > policy.max_array_items:
            raise TTSPayloadLimitError(
                error_code="payload_limit_exceeded",
                message=(
                    "payload_limit_exceeded: "
                    f"max_array_items={policy.max_array_items}, observed_items={len(value)}"
                ),
            )
        for item in value:
            _raise_payload_limit_if_needed(item, policy=policy, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > policy.max_object_keys:
            raise TTSPayloadLimitError(
                error_code="payload_limit_exceeded",
                message=(
                    "payload_limit_exceeded: "
                    f"max_object_keys={policy.max_object_keys}, observed_keys={len(value)}"
                ),
            )
        for item in value.values():
            _raise_payload_limit_if_needed(item, policy=policy, depth=depth + 1)


def _parse_json_body_bytes(
    *,
    body_bytes: bytes,
    content_length: int | None,
    policy: TTSHTTPPolicy,
) -> dict[str, Any]:
    if content_length is not None and content_length > policy.max_request_body_bytes:
        raise TTSPayloadLimitError(error_code="payload_too_large", message="payload too large")
    if len(body_bytes) > policy.max_request_body_bytes:
        raise TTSPayloadLimitError(error_code="payload_too_large", message="payload too large")
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"JSON parse failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object.")
    _raise_payload_limit_if_needed(payload, policy=policy)
    return payload


def _internal_error_response(
    *,
    run_dir: Path | None,
    endpoint: str,
    exc: Exception,
    stream_event: bool,
) -> dict[str, Any]:
    if run_dir is not None:
        redacted_entry = redact_error_entry(
            {
                "timestamp_utc": _utc_now(),
                "endpoint": endpoint,
                "error_code": "internal_error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
            enable_redaction=True,
        )
        _append_jsonl(run_dir / "service_errors.jsonl", redacted_entry)
    if stream_event:
        return {"event": "error", "error": "internal service error", "error_code": "internal_error"}
    return {"ok": False, "error": "internal service error", "error_code": "internal_error"}


def _disabled_engine(name: str, reason: str) -> CallbackTTSEngine:
    error_message = f"{name} is unavailable: {reason}"

    def _prewarm() -> None:
        raise TTSRuntimeError(error_message)

    def _synthesize(_text: str, _language: str, _speaker: str | None) -> tuple[bytes, int]:
        raise TTSRuntimeError(error_message)

    return CallbackTTSEngine(name=name, synthesize_fn=_synthesize, prewarm_fn=_prewarm)


def _build_silence_fallback_engine(name: str = "silence_fallback", *, sample_rate: int = 22050) -> CallbackTTSEngine:
    def _prewarm() -> None:
        return None

    def _synthesize(text: str, _language: str, _speaker: str | None) -> tuple[bytes, int]:
        duration_ms = min(max(300, len(text) * 16), 1500)
        return make_silence_wav_bytes(duration_ms=duration_ms, sample_rate=sample_rate), sample_rate

    return CallbackTTSEngine(name=name, synthesize_fn=_synthesize, prewarm_fn=_prewarm)


def _synthesize_windows_sapi_wav(*, text: str, language: str, speaker: str | None) -> tuple[bytes, int]:
    text_payload_b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    language_payload_b64 = base64.b64encode(str(language or "").encode("utf-8")).decode("ascii")
    speaker_name = (speaker or os.getenv("WINDOWS_SAPI_VOICE_NAME", "")).strip()
    speaker_payload_b64 = base64.b64encode(speaker_name.encode("utf-8")).decode("ascii")

    with tempfile.TemporaryDirectory(prefix="atm10-windows-sapi-") as temp_dir:
        output_path = Path(temp_dir) / "tts.wav"
        output_path_b64 = base64.b64encode(str(output_path).encode("utf-8")).decode("ascii")
        powershell_script = "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                "Add-Type -AssemblyName System.Speech",
                f"$text = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{text_payload_b64}'))",
                f"$languageTag = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{language_payload_b64}'))",
                f"$voiceName = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{speaker_payload_b64}'))",
                f"$outputPath = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{output_path_b64}'))",
                "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer",
                "try {",
                "  if (-not [string]::IsNullOrWhiteSpace($voiceName)) {",
                "    $synth.SelectVoice($voiceName)",
                "  } elseif (-not [string]::IsNullOrWhiteSpace($languageTag)) {",
                "    $candidate = $synth.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo } | Where-Object { $_.Culture.Name -like ($languageTag + '*') } | Select-Object -First 1",
                "    if ($null -ne $candidate) { $synth.SelectVoice($candidate.Name) }",
                "  }",
                "  $synth.SetOutputToWaveFile($outputPath)",
                "  $synth.Speak($text)",
                "} finally {",
                "  $synth.Dispose()",
                "}",
            ]
        )
        encoded_script = base64.b64encode(powershell_script.encode("utf-16le")).decode("ascii")
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_script],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except FileNotFoundError as exc:
            raise TTSRuntimeError("Windows PowerShell is unavailable for System.Speech fallback.") from exc
        except subprocess.TimeoutExpired as exc:
            raise TTSRuntimeError("Windows SAPI fallback timed out.") from exc
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "").strip() or f"exit_code={completed.returncode}"
            raise TTSRuntimeError(f"Windows SAPI fallback failed: {message}")
        if not output_path.exists():
            raise TTSRuntimeError("Windows SAPI fallback did not produce an output wav file.")
        wav_bytes = output_path.read_bytes()
        if not wav_bytes:
            raise TTSRuntimeError("Windows SAPI fallback produced empty audio.")
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            sample_rate = int(wav_file.getframerate())
        return wav_bytes, sample_rate


def _build_windows_sapi_engine(name: str = "windows_sapi_fallback") -> CallbackTTSEngine:
    def _prewarm() -> None:
        _synthesize_windows_sapi_wav(text="ATM10 pilot runtime probe.", language="en", speaker=None)

    def _synthesize(text: str, language: str, speaker: str | None) -> tuple[bytes, int]:
        return _synthesize_windows_sapi_wav(text=text, language=language, speaker=speaker)

    return CallbackTTSEngine(name=name, synthesize_fn=_synthesize, prewarm_fn=_prewarm)


def _env_flag(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _looks_like_local_repo_path(repo_or_dir: str) -> bool:
    candidate = repo_or_dir.strip()
    if not candidate:
        return False
    if candidate.startswith((".", "~")):
        return True
    if Path(candidate).is_absolute():
        return True
    if "\\" in candidate:
        return True
    if ":" in candidate:
        return True
    return Path(candidate).exists()


def _resolve_silero_repo_source(*, repo_or_dir: str, allow_remote: bool, repo_ref: str | None) -> tuple[str, str]:
    if _looks_like_local_repo_path(repo_or_dir):
        return "local", repo_or_dir

    if not allow_remote:
        raise TTSRuntimeError(
            "Silero remote torch.hub source is disabled by default. "
            "Use SILERO_ALLOW_REMOTE_HUB=true only with a pinned revision."
        )

    if ":" in repo_or_dir:
        owner_repo, _, inline_ref = repo_or_dir.partition(":")
        if not owner_repo or not inline_ref:
            raise TTSRuntimeError("SILERO_REPO_OR_DIR must include both owner/repo and revision after ':'.")
        return "github", repo_or_dir

    if not repo_ref:
        raise TTSRuntimeError(
            "Silero remote source requires pinned revision. "
            "Set SILERO_REPO_REF or include ':<ref>' in SILERO_REPO_OR_DIR."
        )
    return "github", f"{repo_or_dir}:{repo_ref}"


def _wav_bytes_from_waveform(*, waveform: Any, sample_rate: int) -> bytes:
    mono = np.asarray(waveform, dtype=np.float32).reshape(-1)
    clipped = np.clip(mono, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(pcm16.tobytes())
    return buffer.getvalue()


def _sample_rate_from_wav_bytes(wav_bytes: bytes) -> int:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        return int(wav_file.getframerate())


def _build_xtts_engine() -> CallbackTTSEngine:
    model_name = os.getenv("XTTS_MODEL_NAME", "tts_models/multilingual/multi-dataset/xtts_v2")
    default_speaker_wav = os.getenv("XTTS_DEFAULT_SPEAKER_WAV")
    use_gpu = os.getenv("XTTS_USE_GPU", "false").strip().lower() in {"1", "true", "yes"}
    state: dict[str, Any] = {"model": None}
    lock = threading.RLock()

    def _load_model() -> Any:
        with lock:
            if state["model"] is not None:
                return state["model"]
            try:
                from TTS.api import TTS
            except Exception as exc:
                raise TTSRuntimeError("XTTS v2 dependency is missing. Install coqui TTS package.") from exc
            state["model"] = TTS(model_name=model_name, progress_bar=False, gpu=use_gpu)
            return state["model"]

    def _prewarm() -> None:
        _load_model()

    def _synthesize(text: str, language: str, speaker: str | None) -> tuple[bytes, int]:
        model = _load_model()
        kwargs: dict[str, Any] = {"text": text}
        if language:
            kwargs["language"] = language
        speaker_wav_path = None
        if speaker and Path(speaker).is_file():
            speaker_wav_path = str(Path(speaker).resolve())
        elif default_speaker_wav and Path(default_speaker_wav).is_file():
            speaker_wav_path = str(Path(default_speaker_wav).resolve())
        if speaker_wav_path is not None:
            kwargs["speaker_wav"] = speaker_wav_path
        elif speaker:
            kwargs["speaker"] = speaker

        waveform = model.tts(**kwargs)
        sample_rate = int(getattr(getattr(model, "synthesizer", None), "output_sample_rate", 24000))
        return _wav_bytes_from_waveform(waveform=waveform, sample_rate=sample_rate), sample_rate

    return CallbackTTSEngine(name="xtts_v2", synthesize_fn=_synthesize, prewarm_fn=_prewarm)


def _resolve_piper_config(
    *,
    piper_executable: str | None = None,
    piper_model_path: str | None = None,
    piper_speaker: str | None = None,
) -> dict[str, str | None]:
    effective_executable = str(piper_executable or os.getenv("PIPER_EXECUTABLE", "piper")).strip() or "piper"
    model_path_value = piper_model_path
    if model_path_value is None:
        model_path_value = os.getenv("PIPER_MODEL_PATH")
    speaker_value = piper_speaker
    if speaker_value is None:
        speaker_value = os.getenv("PIPER_SPEAKER")
    normalized_model_path = str(model_path_value).strip() if model_path_value is not None else ""
    normalized_speaker = str(speaker_value).strip() if speaker_value is not None else ""
    return {
        "executable": effective_executable,
        "model_path": normalized_model_path or None,
        "speaker": normalized_speaker or None,
    }


def _load_piper_python_voice() -> Any | None:
    try:
        from piper import PiperVoice
    except Exception:
        return None
    return PiperVoice


def _build_piper_python_synthesis_config(selected_speaker: str | None) -> Any | None:
    normalized_speaker = str(selected_speaker or "").strip()
    if not normalized_speaker:
        return None
    try:
        from piper.config import SynthesisConfig
    except Exception as exc:
        raise TTSRuntimeError("Piper Python synthesis config is unavailable.") from exc
    try:
        speaker_id = int(normalized_speaker)
    except ValueError as exc:
        raise TTSRuntimeError(
            f"Piper speaker must be numeric for the Python runtime: {normalized_speaker}"
        ) from exc
    return SynthesisConfig(speaker_id=speaker_id)


def _synthesize_with_loaded_piper_voice(
    *,
    voice: Any,
    text: str,
    selected_speaker: str | None,
) -> tuple[bytes, int]:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        synth_config = _build_piper_python_synthesis_config(selected_speaker)
        voice.synthesize_wav(text, wav_file, syn_config=synth_config)
    wav_bytes = buffer.getvalue()
    if not wav_bytes:
        raise TTSRuntimeError("Piper Python synthesis produced empty audio.")
    sample_rate = _sample_rate_from_wav_bytes(wav_bytes)
    return wav_bytes, sample_rate


def _build_piper_engine(
    *,
    piper_executable: str | None = None,
    piper_model_path: str | None = None,
    piper_speaker: str | None = None,
) -> CallbackTTSEngine:
    resolved_piper = _resolve_piper_config(
        piper_executable=piper_executable,
        piper_model_path=piper_model_path,
        piper_speaker=piper_speaker,
    )
    piper_executable = str(resolved_piper["executable"])
    piper_model_path = resolved_piper["model_path"]
    default_speaker = resolved_piper["speaker"]

    if not piper_model_path:
        return _disabled_engine("piper", "PIPER_MODEL_PATH is not set.")

    state: dict[str, Any] = {"voice": None, "backend": None}
    lock = threading.RLock()

    def _load_voice() -> tuple[Any | None, str]:
        with lock:
            if state["backend"] == "python":
                return state["voice"], "python"
            if state["backend"] == "subprocess":
                return None, "subprocess"

            piper_voice_cls = _load_piper_python_voice()
            if piper_voice_cls is not None:
                try:
                    state["voice"] = piper_voice_cls.load(str(piper_model_path))
                    state["backend"] = "python"
                    return state["voice"], "python"
                except Exception:
                    state["voice"] = None
            state["backend"] = "subprocess"
            return None, "subprocess"

    def _synthesize_via_subprocess(text: str, selected_speaker: str | None) -> tuple[bytes, int]:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            output_path = Path(temp_file.name)
        command = [
            piper_executable,
            "--model",
            str(piper_model_path),
            "--output_file",
            str(output_path),
        ]
        if selected_speaker:
            command.extend(["--speaker", str(selected_speaker)])
        try:
            result = subprocess.run(
                command,
                input=text,
                capture_output=True,
                text=True,
                check=False,
                timeout=60.0,
            )
            if result.returncode != 0:
                message = (result.stderr or result.stdout or "unknown piper error").strip()
                raise TTSRuntimeError(f"Piper synthesis failed: {message}")
            wav_bytes = output_path.read_bytes()
            if not wav_bytes:
                raise TTSRuntimeError("Piper synthesis produced empty audio.")
            sample_rate = _sample_rate_from_wav_bytes(wav_bytes)
            return wav_bytes, sample_rate
        finally:
            output_path.unlink(missing_ok=True)

    def _prewarm() -> None:
        voice, backend = _load_voice()
        if backend == "python":
            if voice is None:
                raise TTSRuntimeError("Piper Python runtime did not load a voice.")
            return
        _synthesize_via_subprocess("ATM10 pilot runtime probe.", None)

    def _synthesize(text: str, _language: str, speaker: str | None) -> tuple[bytes, int]:
        selected_speaker = speaker or default_speaker
        voice, backend = _load_voice()
        if backend == "python" and voice is not None:
            return _synthesize_with_loaded_piper_voice(
                voice=voice,
                text=text,
                selected_speaker=selected_speaker,
            )
        return _synthesize_via_subprocess(text, selected_speaker)

    return CallbackTTSEngine(name="piper", synthesize_fn=_synthesize, prewarm_fn=_prewarm)


def _build_silero_engine() -> CallbackTTSEngine:
    repo_or_dir = os.getenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    repo_ref = os.getenv("SILERO_REPO_REF")
    allow_remote_hub = _env_flag(os.getenv("SILERO_ALLOW_REMOTE_HUB"))
    model_language = os.getenv("SILERO_MODEL_LANGUAGE", "ru")
    model_id = os.getenv("SILERO_MODEL_ID", "v4_ru")
    sample_rate = int(os.getenv("SILERO_SAMPLE_RATE", "24000"))
    default_speaker = os.getenv("SILERO_SPEAKER", "xenia")
    repo_source, resolved_repo_or_dir = _resolve_silero_repo_source(
        repo_or_dir=repo_or_dir,
        allow_remote=allow_remote_hub,
        repo_ref=repo_ref,
    )
    state: dict[str, Any] = {"model": None}
    lock = threading.RLock()

    def _load_model() -> Any:
        with lock:
            if state["model"] is not None:
                return state["model"]
            try:
                import torch
            except Exception as exc:
                raise TTSRuntimeError("Silero dependency is missing. Install torch.") from exc
            try:
                model, _example_text = torch.hub.load(
                    repo_or_dir=resolved_repo_or_dir,
                    model="silero_tts",
                    language=model_language,
                    speaker=model_id,
                    source=repo_source,
                )
            except Exception as exc:
                raise TTSRuntimeError(f"Silero model load failed: {exc}") from exc
            state["model"] = model
            return model

    def _prewarm() -> None:
        _load_model()

    def _synthesize(text: str, _language: str, speaker: str | None) -> tuple[bytes, int]:
        model = _load_model()
        selected_speaker = speaker or default_speaker
        try:
            waveform = model.apply_tts(
                text=text,
                speaker=selected_speaker,
                sample_rate=sample_rate,
            )
        except Exception as exc:
            raise TTSRuntimeError(f"Silero synthesis failed: {exc}") from exc
        if hasattr(waveform, "detach"):
            waveform = waveform.detach().cpu().numpy()
        wav_bytes = _wav_bytes_from_waveform(waveform=waveform, sample_rate=sample_rate)
        return wav_bytes, sample_rate

    return CallbackTTSEngine(name="silero_ru_service", synthesize_fn=_synthesize, prewarm_fn=_prewarm)


def _build_default_service(
    *,
    cache_items: int,
    chunk_chars: int,
    queue_size: int,
    piper_executable: str | None = None,
    piper_model_path: str | None = None,
    piper_speaker: str | None = None,
) -> TTSRuntimeService:
    xtts = _build_xtts_engine()
    resolved_piper = _resolve_piper_config(
        piper_executable=piper_executable,
        piper_model_path=piper_model_path,
        piper_speaker=piper_speaker,
    )
    piper = _build_piper_engine(
        piper_executable=str(resolved_piper["executable"]),
        piper_model_path=resolved_piper["model_path"],
        piper_speaker=resolved_piper["speaker"],
    )
    try:
        silero = _build_silero_engine()
    except TTSRuntimeError as exc:
        silero = _disabled_engine("silero_ru_service", str(exc))
    return TTSRuntimeService(
        xtts_engine=xtts,
        piper_engine=piper,
        silero_engine=silero,
        fallback_engines=[
            _build_windows_sapi_engine(),
            _build_silence_fallback_engine(),
        ],
        max_chunk_chars=chunk_chars,
        queue_size=queue_size,
        cache=PhraseCache(max_items=cache_items),
        effective_config={
            "piper": dict(resolved_piper),
        },
    )


def _serialize_result(result: dict[str, Any]) -> dict[str, Any]:
    payload_chunks: list[dict[str, Any]] = []
    for chunk in result["chunks"]:
        payload_chunks.append(
            {
                "index": chunk.index,
                "text": chunk.text,
                "engine": chunk.engine,
                "sample_rate": chunk.sample_rate,
                "cached": chunk.cached,
                "audio_wav_b64": base64.b64encode(chunk.audio_wav_bytes).decode("ascii"),
            }
        )
    return {
        "timestamp_utc": _utc_now(),
        "chunk_count": result["chunk_count"],
        "cache_hits": result["cache_hits"],
        "router_chain": result["router_chain"],
        "chunks": payload_chunks,
    }


def _coerce_bool_value(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    raise ValueError(f"{field_name} must be boolean or one of true|false|1|0.")


def _request_from_payload(payload: dict[str, Any]) -> TTSRequest:
    text = str(payload.get("text", "")).strip()
    if not text:
        raise ValueError("text is required and must be non-empty.")
    language = str(payload.get("language", "en")).strip() or "en"
    speaker_value = payload.get("speaker")
    speaker = str(speaker_value).strip() if isinstance(speaker_value, str) and speaker_value.strip() else None
    service_voice = _coerce_bool_value(payload.get("service_voice", False), field_name="service_voice")
    chunk_chars_value = payload.get("chunk_chars")
    chunk_chars = int(chunk_chars_value) if isinstance(chunk_chars_value, int) and chunk_chars_value > 0 else None
    return TTSRequest(
        text=text,
        language=language,
        speaker=speaker,
        service_voice=service_voice,
        chunk_chars=chunk_chars,
    )


def create_app(
    service: TTSRuntimeService,
    *,
    prewarm: bool,
    http_policy: TTSHTTPPolicy | None = None,
    run_dir: Path | None = None,
    service_token: str | None = None,
    expose_openapi: bool = False,
) -> Any:
    effective_http_policy = http_policy or TTSHTTPPolicy()
    _validate_http_policy(effective_http_policy)
    effective_service_token = _resolve_service_token(service_token)
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, StreamingResponse
    except Exception as exc:  # pragma: no cover - dependency presence
        raise RuntimeError("FastAPI/uvicorn are required for tts_runtime_service.") from exc
    global FastAPIRequest
    FastAPIRequest = Request

    @asynccontextmanager
    async def _lifespan(_app: Any):
        service.start()
        if prewarm:
            service.prewarm()
        try:
            yield
        finally:
            service.stop()

    app = FastAPI(
        title="ATM10 TTS Runtime",
        version="0.1.0",
        lifespan=_lifespan,
        docs_url="/docs" if expose_openapi else None,
        openapi_url="/openapi.json" if expose_openapi else None,
        redoc_url=None,
    )

    @app.get("/health")
    async def _health(http_request: FastAPIRequest) -> Any:
        if not _is_authorized(http_request.headers, service_token=effective_service_token):
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "unauthorized", "error_code": "unauthorized"},
            )
        return {
            "timestamp_utc": _utc_now(),
            "auth_enabled": bool(effective_service_token),
            "api_docs_exposed": bool(expose_openapi),
            "policy": asdict(effective_http_policy),
            **service.health(),
        }

    @app.post("/tts")
    async def _tts(http_request: FastAPIRequest) -> Any:
        if not _is_authorized(http_request.headers, service_token=effective_service_token):
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "unauthorized", "error_code": "unauthorized"},
            )
        raw_body = await http_request.body()
        try:
            content_length_raw = http_request.headers.get("content-length")
            content_length = int(content_length_raw) if content_length_raw is not None else None
            if content_length is not None and content_length < 0:
                raise ValueError("invalid Content-Length header")
            payload = _parse_json_body_bytes(
                body_bytes=raw_body,
                content_length=content_length,
                policy=effective_http_policy,
            )
        except TTSPayloadLimitError as exc:
            return JSONResponse(
                status_code=413,
                content={"ok": False, "error": str(exc), "error_code": exc.error_code},
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": str(exc), "error_code": "bad_request"},
            )
        try:
            request = _request_from_payload(payload)
            result = service.submit(request).result(timeout=120.0)
            return {"ok": True, "result": _serialize_result(result)}
        except (ValueError, TTSRuntimeError) as exc:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": str(exc), "error_code": "bad_request"},
            )
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content=_internal_error_response(
                    run_dir=run_dir,
                    endpoint="/tts",
                    exc=exc,
                    stream_event=False,
                ),
            )

    @app.post("/tts_stream")
    async def _tts_stream(http_request: FastAPIRequest) -> Any:
        if not _is_authorized(http_request.headers, service_token=effective_service_token):
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "unauthorized", "error_code": "unauthorized"},
            )
        raw_body = await http_request.body()
        try:
            content_length_raw = http_request.headers.get("content-length")
            content_length = int(content_length_raw) if content_length_raw is not None else None
            if content_length is not None and content_length < 0:
                raise ValueError("invalid Content-Length header")
            payload = _parse_json_body_bytes(
                body_bytes=raw_body,
                content_length=content_length,
                policy=effective_http_policy,
            )
        except TTSPayloadLimitError as exc:
            return JSONResponse(
                status_code=413,
                content={"ok": False, "error": str(exc), "error_code": exc.error_code},
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": str(exc), "error_code": "bad_request"},
            )

        try:
            request = _request_from_payload(payload)
        except (ValueError, TTSRuntimeError) as exc:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": str(exc), "error_code": "bad_request"},
            )
        except Exception as exc:
            return JSONResponse(
                status_code=500,
                content=_internal_error_response(
                    run_dir=run_dir,
                    endpoint="/tts_stream",
                    exc=exc,
                    stream_event=False,
                ),
            )

        def _iter_events():
            yield json.dumps({"event": "started", "timestamp_utc": _utc_now()}, ensure_ascii=False) + "\n"
            chunk_count = 0
            cache_hits = 0
            try:
                for chunk in service.iter_synthesize(request):
                    chunk_count += 1
                    if chunk.cached:
                        cache_hits += 1
                    chunk_payload = {
                        "index": chunk.index,
                        "text": chunk.text,
                        "engine": chunk.engine,
                        "sample_rate": chunk.sample_rate,
                        "cached": chunk.cached,
                        "audio_wav_b64": base64.b64encode(chunk.audio_wav_bytes).decode("ascii"),
                    }
                    yield json.dumps({"event": "audio_chunk", **chunk_payload}, ensure_ascii=False) + "\n"
            except (ValueError, TTSRuntimeError) as exc:
                yield (
                    json.dumps(
                        {
                            "event": "error",
                            "timestamp_utc": _utc_now(),
                            "error": str(exc),
                            "error_code": "bad_request",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                return
            except Exception as exc:
                internal_event = _internal_error_response(
                    run_dir=run_dir,
                    endpoint="/tts_stream",
                    exc=exc,
                    stream_event=True,
                )
                yield json.dumps(internal_event, ensure_ascii=False) + "\n"
                return
            yield (
                json.dumps(
                    {
                        "event": "completed",
                        "timestamp_utc": _utc_now(),
                        "chunk_count": chunk_count,
                        "cache_hits": cache_hits,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        return StreamingResponse(_iter_events(), media_type="application/x-ndjson")

    return app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FastAPI TTS runtime: XTTSv2 + fallback Piper/Silero.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8780, help="Bind port (default: 8780).")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    parser.add_argument("--queue-size", type=int, default=128, help="Queue max size (default: 128).")
    parser.add_argument("--chunk-chars", type=int, default=220, help="Chunk size for long text (default: 220).")
    parser.add_argument("--cache-items", type=int, default=512, help="Phrase cache max entries (default: 512).")
    parser.add_argument(
        "--tts-piper-executable",
        type=str,
        default=None,
        help="Optional Piper executable override. Falls back to PIPER_EXECUTABLE or 'piper'.",
    )
    parser.add_argument(
        "--tts-piper-model-path",
        type=str,
        default=None,
        help="Optional Piper model path override. Falls back to PIPER_MODEL_PATH.",
    )
    parser.add_argument(
        "--tts-piper-speaker",
        type=str,
        default=None,
        help="Optional Piper speaker override. Falls back to PIPER_SPEAKER.",
    )
    parser.add_argument(
        "--max-request-bytes",
        type=int,
        default=TTS_HTTP_DEFAULT_MAX_REQUEST_BODY_BYTES,
        help=(
            "Maximum allowed HTTP request body size in bytes "
            f"(default: {TTS_HTTP_DEFAULT_MAX_REQUEST_BODY_BYTES})."
        ),
    )
    parser.add_argument(
        "--max-json-depth",
        type=int,
        default=TTS_HTTP_DEFAULT_MAX_JSON_DEPTH,
        help=f"Maximum allowed JSON depth (default: {TTS_HTTP_DEFAULT_MAX_JSON_DEPTH}).",
    )
    parser.add_argument(
        "--max-string-length",
        type=int,
        default=TTS_HTTP_DEFAULT_MAX_STRING_LENGTH,
        help=f"Maximum allowed JSON string length (default: {TTS_HTTP_DEFAULT_MAX_STRING_LENGTH}).",
    )
    parser.add_argument(
        "--max-array-items",
        type=int,
        default=TTS_HTTP_DEFAULT_MAX_ARRAY_ITEMS,
        help=f"Maximum allowed JSON array length (default: {TTS_HTTP_DEFAULT_MAX_ARRAY_ITEMS}).",
    )
    parser.add_argument(
        "--max-object-keys",
        type=int,
        default=TTS_HTTP_DEFAULT_MAX_OBJECT_KEYS,
        help=f"Maximum allowed JSON object key count (default: {TTS_HTTP_DEFAULT_MAX_OBJECT_KEYS}).",
    )
    parser.add_argument(
        "--service-token",
        type=str,
        default=None,
        help=(
            "Optional shared token for HTTP endpoints. "
            "When set (or via ATM10_SERVICE_TOKEN), require header X-ATM10-Token."
        ),
    )
    parser.add_argument(
        "--allow-insecure-no-token",
        action="store_true",
        help=(
            "Allow binding to a non-loopback host without a service token. "
            "Intended only for explicit local-network testing."
        ),
    )
    parser.add_argument(
        "--expose-openapi",
        action="store_true",
        help="Expose /docs and /openapi.json for local debugging (default: disabled).",
    )
    parser.add_argument("--no-prewarm", action="store_true", help="Disable prewarm on startup.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - dependency presence
        raise SystemExit("uvicorn is required. Install fastapi + uvicorn.") from exc

    service = _build_default_service(
        cache_items=args.cache_items,
        chunk_chars=args.chunk_chars,
        queue_size=args.queue_size,
        piper_executable=args.tts_piper_executable,
        piper_model_path=args.tts_piper_model_path,
        piper_speaker=args.tts_piper_speaker,
    )
    http_policy = TTSHTTPPolicy(
        max_request_body_bytes=args.max_request_bytes,
        max_json_depth=args.max_json_depth,
        max_string_length=args.max_string_length,
        max_array_items=args.max_array_items,
        max_object_keys=args.max_object_keys,
    )
    try:
        service_token = _validate_bind_security(
            host=args.host,
            service_token=args.service_token,
            allow_insecure_no_token=args.allow_insecure_no_token,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    now = datetime.now(timezone.utc)
    run_dir = _create_run_dir(args.runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    resolved_piper = _resolve_piper_config(
        piper_executable=args.tts_piper_executable,
        piper_model_path=args.tts_piper_model_path,
        piper_speaker=args.tts_piper_speaker,
    )
    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "tts_runtime_service",
        "status": "running",
        "service": {
            "host": args.host,
            "port": args.port,
            "base_url": f"http://{args.host}:{args.port}",
            "api_docs_exposed": args.expose_openapi,
            "http_policy": asdict(http_policy),
            "auth": {
                "enabled": bool(service_token),
                "header": _SERVICE_TOKEN_HEADER,
            },
            "tts": {
                "preferred_tts_engine": "piper" if resolved_piper["model_path"] else "windows_sapi_fallback",
                "piper": {
                    "executable": resolved_piper["executable"],
                    "model_path": resolved_piper["model_path"],
                    "speaker": resolved_piper["speaker"],
                },
            },
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    app = create_app(
        service,
        prewarm=not args.no_prewarm,
        http_policy=http_policy,
        run_dir=run_dir,
        service_token=service_token,
        expose_openapi=args.expose_openapi,
    )
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        run_payload["status"] = "stopped"
        _write_json(run_json_path, run_payload)

    print(f"[tts_runtime_service] run_dir: {run_dir}")
    print(f"[tts_runtime_service] run_json: {run_json_path}")
    print(f"[tts_runtime_service] base_url: http://{args.host}:{args.port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
