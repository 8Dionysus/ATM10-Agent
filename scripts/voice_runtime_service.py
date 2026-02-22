from __future__ import annotations

import argparse
import base64
import json
import sys
import threading
import traceback
import wave
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.io_voice import (
    DEFAULT_FAST_TTS_RUNTIME,
    DEFAULT_QWEN3_ASR_MODEL,
    DEFAULT_QWEN3_TTS_MODEL,
    DEFAULT_WHISPER_GENAI_MODEL_DIR,
    QwenASRClient,
    QwenTTSClient,
    WhisperGenAIASRClient,
    VoiceRuntimeUnavailableError,
    synthesize_ovms_tts_to_wav,
    write_wav_pcm16,
)


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-voice-service")
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


SUPPORTED_TTS_RUNTIMES = ("auto", "qwen3", DEFAULT_FAST_TTS_RUNTIME)
SUPPORTED_ASR_BACKENDS = ("qwen_asr", "whisper_genai")
ARCHIVED_ASR_BACKENDS = ("qwen_asr",)


def _create_asr_warmup_silence_wav(*, run_dir: Path, sample_rate: int = 16000, duration_sec: float = 0.8) -> Path:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be > 0.")
    if duration_sec <= 0:
        raise ValueError("duration_sec must be > 0.")
    out_dir = run_dir / "tmp"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "asr_warmup_silence.wav"
    num_samples = max(1, int(round(sample_rate * duration_sec)))
    silence = np.zeros(num_samples, dtype=np.float32)
    write_wav_pcm16(path=out_path, waveform=silence, sample_rate=sample_rate)
    return out_path


def _run_asr_warmup_request(
    *,
    state: "VoiceRuntimeState",
    audio_path: Path | None,
    language: str | None,
) -> dict[str, Any]:
    warmup_audio = audio_path if audio_path is not None else _create_asr_warmup_silence_wav(run_dir=state.run_dir)
    if not warmup_audio.exists():
        raise FileNotFoundError(f"ASR warmup audio does not exist: {warmup_audio}")
    client = state.ensure_asr()
    t0 = perf_counter()
    result = client.transcribe_path(
        audio_path=warmup_audio,
        context="",
        language=language,
    )
    latency_sec = perf_counter() - t0
    return {
        "audio_path": str(warmup_audio),
        "latency_sec": latency_sec,
        "text_preview": str(result.get("text", ""))[:120],
        "language": str(result.get("language", "")),
    }


class VoiceRuntimeState:
    def __init__(
        self,
        *,
        run_dir: Path,
        asr_model_id: str,
        asr_backend: str,
        asr_device: str,
        asr_task: str,
        asr_static_language: str | None,
        tts_model_id: str,
        device_map: str,
        dtype: str,
        asr_max_new_tokens: int,
    ) -> None:
        self.run_dir = run_dir
        self.asr_model_id = asr_model_id
        self.asr_backend = asr_backend
        self.asr_device = asr_device
        self.asr_task = asr_task
        self.asr_static_language = asr_static_language
        self.tts_model_id = tts_model_id
        self.device_map = device_map
        self.dtype = dtype
        self.asr_max_new_tokens = asr_max_new_tokens

        self._lock = threading.RLock()
        self._asr_client: Any | None = None
        self._tts_client: QwenTTSClient | None = None
        self._asr_load_sec: float | None = None
        self._tts_load_sec: float | None = None
        self._asr_load_error: str | None = None
        self._tts_load_error: str | None = None

    def ensure_asr(self) -> Any:
        with self._lock:
            if self._asr_client is not None:
                return self._asr_client
            t0 = perf_counter()
            try:
                if self.asr_backend == "qwen_asr":
                    self._asr_client = QwenASRClient.from_pretrained(
                        model_id=self.asr_model_id,
                        device_map=self.device_map,
                        dtype=self.dtype,
                        max_new_tokens=self.asr_max_new_tokens,
                    )
                elif self.asr_backend == "whisper_genai":
                    self._asr_client = WhisperGenAIASRClient.from_pretrained(
                        model_dir=self.asr_model_id,
                        device=self.asr_device,
                        task=self.asr_task,
                        max_new_tokens=self.asr_max_new_tokens,
                        static_language=self.asr_static_language,
                    )
                else:
                    raise ValueError(f"Unsupported ASR backend: {self.asr_backend}")
                self._asr_load_sec = perf_counter() - t0
                self._asr_load_error = None
                return self._asr_client
            except Exception as exc:
                self._asr_load_error = str(exc)
                raise

    def ensure_tts(self) -> QwenTTSClient:
        with self._lock:
            if self._tts_client is not None:
                return self._tts_client
            t0 = perf_counter()
            try:
                self._tts_client = QwenTTSClient.from_pretrained(
                    model_id=self.tts_model_id,
                    device_map=self.device_map,
                    dtype=self.dtype,
                )
                self._tts_load_sec = perf_counter() - t0
                self._tts_load_error = None
                return self._tts_client
            except Exception as exc:
                self._tts_load_error = str(exc)
                raise

    def health_payload(self) -> dict[str, Any]:
        with self._lock:
            return {
                "timestamp_utc": _utc_now(),
                "status": "ok",
                "models": {
                    "asr": {
                        "backend": self.asr_backend,
                        "id": self.asr_model_id,
                        "device": self.asr_device if self.asr_backend == "whisper_genai" else self.device_map,
                        "task": self.asr_task if self.asr_backend == "whisper_genai" else "transcribe",
                        "static_language": self.asr_static_language if self.asr_backend == "whisper_genai" else None,
                        "loaded": self._asr_client is not None,
                        "load_seconds": self._asr_load_sec,
                        "load_error": self._asr_load_error,
                    },
                    "tts": {
                        "id": self.tts_model_id,
                        "loaded": self._tts_client is not None,
                        "load_seconds": self._tts_load_sec,
                        "load_error": self._tts_load_error,
                        "supported_runtimes": list(SUPPORTED_TTS_RUNTIMES),
                    },
                },
            }


def process_asr_request(state: VoiceRuntimeState, payload: Mapping[str, Any]) -> dict[str, Any]:
    audio_path_value = payload.get("audio_path")
    if not isinstance(audio_path_value, str) or not audio_path_value.strip():
        raise ValueError("audio_path is required and must be non-empty string.")
    audio_path = Path(audio_path_value)
    if not audio_path.exists():
        raise FileNotFoundError(f"audio_path does not exist: {audio_path}")

    context = payload.get("context", "")
    language_value = payload.get("language")
    context_text = context if isinstance(context, str) else str(context)
    language = language_value if isinstance(language_value, str) else None
    client = state.ensure_asr()
    result = client.transcribe_path(
        audio_path=audio_path,
        context=context_text,
        language=language,
    )
    return {
        "timestamp_utc": _utc_now(),
        "audio_path": str(audio_path),
        "text": result["text"],
        "language": result["language"],
    }


def process_tts_request(state: VoiceRuntimeState, payload: Mapping[str, Any]) -> dict[str, Any]:
    text, speaker, language, instruct, out_wav_path = _parse_tts_payload(state, payload)
    requested_runtime = _resolve_tts_runtime(payload)
    ovms_tts_url, ovms_tts_model = _resolve_ovms_overrides(payload)
    result_payload = _synthesize_tts_non_streaming(
        state=state,
        requested_runtime=requested_runtime,
        text=text,
        speaker=speaker,
        language=language,
        instruct=instruct,
        out_wav_path=out_wav_path,
        ovms_tts_url=ovms_tts_url,
        ovms_tts_model=ovms_tts_model,
    )
    return {
        "timestamp_utc": _utc_now(),
        "text": text,
        **result_payload,
    }


def _waveform_to_pcm16_bytes(waveform: np.ndarray) -> bytes:
    mono = np.asarray(waveform, dtype=np.float32).reshape(-1)
    clipped = np.clip(mono, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    return pcm16.tobytes()


def _resolve_tts_runtime(payload: Mapping[str, Any]) -> str:
    runtime_value = payload.get("runtime", "auto")
    runtime = str(runtime_value).strip().lower() if runtime_value is not None else "auto"
    if runtime == "fast_fallback":
        runtime = DEFAULT_FAST_TTS_RUNTIME
    if runtime not in SUPPORTED_TTS_RUNTIMES:
        raise ValueError(
            "runtime must be one of: auto, qwen3, ovms."
        )
    return runtime


def _resolve_ovms_overrides(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    url_value = payload.get("ovms_tts_url")
    model_value = payload.get("ovms_tts_model")
    ovms_tts_url = str(url_value).strip() if isinstance(url_value, str) and url_value.strip() else None
    ovms_tts_model = str(model_value).strip() if isinstance(model_value, str) and model_value.strip() else None
    return ovms_tts_url, ovms_tts_model


def _load_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        channels = int(wav_file.getnchannels())
        sample_rate = int(wav_file.getframerate())
        num_frames = int(wav_file.getnframes())
        raw = wav_file.readframes(num_frames)

    if channels <= 0:
        raise RuntimeError(f"Invalid WAV channels: {channels}")
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data.reshape(-1), sample_rate


def _synthesize_tts_qwen(
    *,
    state: VoiceRuntimeState,
    text: str,
    speaker: str | None,
    language: str,
    instruct: str | None,
    out_wav_path: Path,
) -> dict[str, Any]:
    client = state.ensure_tts()
    selected_speaker = client.resolve_speaker(speaker)
    waveform, sample_rate = client.synthesize_custom_voice(
        text=text,
        speaker=selected_speaker,
        language=language,
        instruct=instruct,
    )
    write_wav_pcm16(path=out_wav_path, waveform=waveform, sample_rate=sample_rate)
    return {
        "speaker_selected": selected_speaker,
        "language": language,
        "sample_rate": int(sample_rate),
        "num_samples": int(waveform.shape[0]),
        "audio_out_wav": str(out_wav_path),
        "tts_runtime": "qwen3",
        "fallback_used": False,
        "fallback_reason": None,
    }


def _synthesize_tts_fast_fallback(
    *,
    text: str,
    speaker: str | None,
    language: str,
    out_wav_path: Path,
    ovms_tts_url: str | None,
    ovms_tts_model: str | None,
) -> dict[str, Any]:
    synthesize_ovms_tts_to_wav(
        text=text,
        output_path=out_wav_path,
        endpoint_url=ovms_tts_url,
        model_id=ovms_tts_model,
        speaker=speaker,
        language=language,
    )
    waveform, sample_rate = _load_wav_mono(out_wav_path)
    return {
        "speaker_selected": speaker or "default_system_voice",
        "language": language,
        "sample_rate": int(sample_rate),
        "num_samples": int(waveform.shape[0]),
        "audio_out_wav": str(out_wav_path),
        "tts_runtime": DEFAULT_FAST_TTS_RUNTIME,
    }


def _synthesize_tts_non_streaming(
    *,
    state: VoiceRuntimeState,
    requested_runtime: str,
    text: str,
    speaker: str | None,
    language: str,
    instruct: str | None,
    out_wav_path: Path,
    ovms_tts_url: str | None,
    ovms_tts_model: str | None,
) -> dict[str, Any]:
    if requested_runtime == "qwen3":
        result = _synthesize_tts_qwen(
            state=state,
            text=text,
            speaker=speaker,
            language=language,
            instruct=instruct,
            out_wav_path=out_wav_path,
        )
        result["requested_tts_runtime"] = requested_runtime
        return result

    if requested_runtime == DEFAULT_FAST_TTS_RUNTIME:
        result = _synthesize_tts_fast_fallback(
            text=text,
            speaker=speaker,
            language=language,
            out_wav_path=out_wav_path,
            ovms_tts_url=ovms_tts_url,
            ovms_tts_model=ovms_tts_model,
        )
        result["requested_tts_runtime"] = requested_runtime
        result["fallback_used"] = False
        result["fallback_reason"] = None
        return result

    try:
        result = _synthesize_tts_qwen(
            state=state,
            text=text,
            speaker=speaker,
            language=language,
            instruct=instruct,
            out_wav_path=out_wav_path,
        )
        result["requested_tts_runtime"] = requested_runtime
        return result
    except VoiceRuntimeUnavailableError as exc:
        result = _synthesize_tts_fast_fallback(
            text=text,
            speaker=speaker,
            language=language,
            out_wav_path=out_wav_path,
            ovms_tts_url=ovms_tts_url,
            ovms_tts_model=ovms_tts_model,
        )
        result["requested_tts_runtime"] = requested_runtime
        result["fallback_used"] = True
        result["fallback_reason"] = str(exc)
        return result


def _iter_waveform_chunks(*, waveform: np.ndarray, chunk_ms: int, sample_rate: int):
    chunk_samples = max(1, int(sample_rate * (float(chunk_ms) / 1000.0)))
    mono = np.asarray(waveform, dtype=np.float32).reshape(-1)
    for offset in range(0, int(mono.shape[0]), int(chunk_samples)):
        chunk = mono[offset : offset + int(chunk_samples)]
        if chunk.size == 0:
            continue
        yield chunk


def _parse_tts_payload(
    state: VoiceRuntimeState,
    payload: Mapping[str, Any],
) -> tuple[str, str | None, str, str | None, Path]:
    text_value = payload.get("text")
    if not isinstance(text_value, str) or not text_value.strip():
        raise ValueError("text is required and must be non-empty string.")
    text = text_value

    speaker_value = payload.get("speaker")
    speaker = speaker_value if isinstance(speaker_value, str) and speaker_value.strip() else None
    language_value = payload.get("language")
    language = language_value if isinstance(language_value, str) and language_value.strip() else "Auto"
    instruct_value = payload.get("instruct")
    instruct = instruct_value if isinstance(instruct_value, str) and instruct_value.strip() else None

    out_wav_value = payload.get("out_wav_path")
    if isinstance(out_wav_value, str) and out_wav_value.strip():
        out_wav_path = Path(out_wav_value)
    else:
        out_dir = state.run_dir / "tts_outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_wav_path = out_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.wav"
    return text, speaker, language, instruct, out_wav_path


def process_tts_stream_request(state: VoiceRuntimeState, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    text, speaker, language, instruct, out_wav_path = _parse_tts_payload(state, payload)

    chunk_ms_raw = payload.get("chunk_ms", 200)
    if not isinstance(chunk_ms_raw, int) or chunk_ms_raw <= 0:
        raise ValueError("chunk_ms must be positive integer.")
    chunk_ms = int(chunk_ms_raw)
    requested_runtime = _resolve_tts_runtime(payload)
    ovms_tts_url, ovms_tts_model = _resolve_ovms_overrides(payload)

    t0 = perf_counter()
    selected_speaker = speaker or "default_system_voice"
    fallback_used = False
    fallback_reason: str | None = None
    collected_chunks: list[np.ndarray] = []
    sample_rate: int | None = None
    first_chunk_latency_sec: float | None = None
    streaming_mode = "fallback_chunked"

    if requested_runtime != DEFAULT_FAST_TTS_RUNTIME:
        try:
            client = state.ensure_tts()
            selected_speaker = client.resolve_speaker(speaker)
            for chunk, chunk_sample_rate, mode in client.stream_synthesize_custom_voice(
                text=text,
                speaker=selected_speaker,
                language=language,
                instruct=instruct,
                chunk_duration_ms=chunk_ms,
            ):
                if chunk.size == 0:
                    continue
                if sample_rate is None:
                    sample_rate = int(chunk_sample_rate)
                if first_chunk_latency_sec is None:
                    first_chunk_latency_sec = perf_counter() - t0
                collected_chunks.append(np.asarray(chunk, dtype=np.float32).reshape(-1))
                streaming_mode = mode
        except VoiceRuntimeUnavailableError as exc:
            if requested_runtime == "qwen3":
                raise
            fallback_used = True
            fallback_reason = str(exc)

    if not collected_chunks:
        synthesize_ovms_tts_to_wav(
            text=text,
            output_path=out_wav_path,
            endpoint_url=ovms_tts_url,
            model_id=ovms_tts_model,
            speaker=speaker,
            language=language,
        )
        waveform, sample_rate = _load_wav_mono(out_wav_path)
        for chunk in _iter_waveform_chunks(waveform=waveform, chunk_ms=chunk_ms, sample_rate=sample_rate):
            if first_chunk_latency_sec is None:
                first_chunk_latency_sec = perf_counter() - t0
            collected_chunks.append(chunk)
        if not collected_chunks:
            raise RuntimeError("Fast fallback TTS produced empty waveform.")
        streaming_mode = "ovms_file_chunked"
        selected_speaker = speaker or "default_system_voice"
    else:
        assert sample_rate is not None
        waveform = np.concatenate(collected_chunks)
        write_wav_pcm16(path=out_wav_path, waveform=waveform, sample_rate=sample_rate)

    assert sample_rate is not None
    waveform = np.concatenate(collected_chunks)

    events: list[dict[str, Any]] = [
        {
            "event": "started",
            "timestamp_utc": _utc_now(),
            "text": text,
            "speaker_selected": selected_speaker,
            "language": language,
            "chunk_ms": chunk_ms,
            "requested_tts_runtime": requested_runtime,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
        }
    ]

    for chunk_index, chunk in enumerate(collected_chunks):
        pcm16_b64 = base64.b64encode(_waveform_to_pcm16_bytes(chunk)).decode("ascii")
        events.append(
            {
                "event": "audio_chunk",
                "timestamp_utc": _utc_now(),
                "chunk_index": chunk_index,
                "sample_rate": int(sample_rate),
                "num_samples": int(chunk.shape[0]),
                "first_chunk_latency_sec": first_chunk_latency_sec,
                "streaming_mode": streaming_mode,
                "pcm16_b64": pcm16_b64,
            }
        )

    total_synthesis_sec = perf_counter() - t0
    audio_duration_sec = float(waveform.shape[0]) / float(sample_rate)
    rtf = total_synthesis_sec / audio_duration_sec if audio_duration_sec > 0 else None
    events.append(
        {
            "event": "completed",
            "timestamp_utc": _utc_now(),
            "text": text,
            "speaker_selected": selected_speaker,
            "language": language,
            "streaming_mode": streaming_mode,
            "requested_tts_runtime": requested_runtime,
            "tts_runtime": "qwen3" if streaming_mode != "ovms_file_chunked" else DEFAULT_FAST_TTS_RUNTIME,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "sample_rate": int(sample_rate),
            "num_samples": int(waveform.shape[0]),
            "audio_duration_sec": audio_duration_sec,
            "first_chunk_latency_sec": first_chunk_latency_sec,
            "total_synthesis_sec": total_synthesis_sec,
            "rtf": rtf,
            "audio_out_wav": str(out_wav_path),
        }
    )
    return events


def _create_handler(state: VoiceRuntimeState) -> type[BaseHTTPRequestHandler]:
    class VoiceServiceHandler(BaseHTTPRequestHandler):
        server_version = "ATM10VoiceService/1.0"

        def _send_json(self, code: int, payload: Mapping[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict[str, Any]:
            length_raw = self.headers.get("Content-Length")
            if length_raw is None:
                raise ValueError("Content-Length header is required.")
            length = int(length_raw)
            if length <= 0:
                raise ValueError("Request body must be non-empty JSON.")
            raw = self.rfile.read(length)
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("JSON body must be an object.")
            return parsed

        def _start_ndjson(self, code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.end_headers()

        def _write_ndjson_event(self, payload: Mapping[str, Any]) -> None:
            body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            self.wfile.write(body)
            self.wfile.flush()

        def _send_tts_stream(self, payload: Mapping[str, Any]) -> None:
            headers_started = False
            try:
                events = process_tts_stream_request(state, payload)
                self._start_ndjson(200)
                headers_started = True
                for event in events:
                    self._write_ndjson_event(event)
            except (ValueError, FileNotFoundError) as exc:
                if headers_started:
                    self._write_ndjson_event(
                        {"event": "error", "error": str(exc), "error_code": "bad_request"}
                    )
                    return
                self._send_json(400, {"ok": False, "error": str(exc), "error_code": "bad_request"})
            except VoiceRuntimeUnavailableError as exc:
                if headers_started:
                    self._write_ndjson_event(
                        {
                            "event": "error",
                            "error": str(exc),
                            "error_code": "voice_runtime_missing_dependency",
                        }
                    )
                    return
                self._send_json(
                    503,
                    {"ok": False, "error": str(exc), "error_code": "voice_runtime_missing_dependency"},
                )
            except Exception as exc:  # pragma: no cover - defensive path
                if headers_started:
                    self._write_ndjson_event(
                        {
                            "event": "error",
                            "error": str(exc),
                            "error_code": "internal_error",
                            "traceback": traceback.format_exc(),
                        }
                    )
                    return
                self._send_json(
                    500,
                    {
                        "ok": False,
                        "error": str(exc),
                        "error_code": "internal_error",
                        "traceback": traceback.format_exc(),
                    },
                )

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._send_json(200, state.health_payload())
                return
            self._send_json(404, {"error": "not_found", "path": self.path})

        def do_POST(self) -> None:  # noqa: N802
            try:
                payload = self._read_json_body()
                if self.path == "/asr":
                    result = process_asr_request(state, payload)
                    self._send_json(200, {"ok": True, "result": result})
                    return
                if self.path == "/tts":
                    result = process_tts_request(state, payload)
                    self._send_json(200, {"ok": True, "result": result})
                    return
                if self.path == "/tts_stream":
                    self._send_tts_stream(payload)
                    return
                self._send_json(404, {"error": "not_found", "path": self.path})
            except (ValueError, FileNotFoundError) as exc:
                self._send_json(400, {"ok": False, "error": str(exc), "error_code": "bad_request"})
            except VoiceRuntimeUnavailableError as exc:
                self._send_json(
                    503,
                    {"ok": False, "error": str(exc), "error_code": "voice_runtime_missing_dependency"},
                )
            except Exception as exc:  # pragma: no cover - defensive path
                self._send_json(
                    500,
                    {
                        "ok": False,
                        "error": str(exc),
                        "error_code": "internal_error",
                        "traceback": traceback.format_exc(),
                    },
                )

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return VoiceServiceHandler


def run_voice_runtime_service(
    *,
    host: str,
    port: int,
    runs_dir: Path,
    asr_model_id: str,
    tts_model_id: str,
    device_map: str,
    dtype: str,
    asr_max_new_tokens: int,
    preload_asr: bool,
    preload_tts: bool,
    asr_backend: str = "whisper_genai",
    asr_device: str = "NPU",
    asr_task: str = "transcribe",
    asr_static_language: str | None = None,
    allow_archived_asr_backend: bool = False,
    asr_warmup_request: bool = False,
    asr_warmup_audio: Path | None = None,
    asr_warmup_language: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if asr_backend in ARCHIVED_ASR_BACKENDS and not allow_archived_asr_backend:
        raise ValueError(
            f"ASR backend '{asr_backend}' is archived. "
            "Use --allow-archived-qwen-asr to enable it temporarily."
        )
    if now is None:
        now = datetime.now(timezone.utc)
    run_dir = _create_run_dir(runs_dir, now)
    run_json_path = run_dir / "run.json"
    state = VoiceRuntimeState(
        run_dir=run_dir,
        asr_model_id=asr_model_id,
        asr_backend=asr_backend,
        asr_device=asr_device,
        asr_task=asr_task,
        asr_static_language=asr_static_language,
        tts_model_id=tts_model_id,
        device_map=device_map,
        dtype=dtype,
        asr_max_new_tokens=asr_max_new_tokens,
    )

    preload: dict[str, Any] = {
        "asr": {
            "requested": preload_asr,
            "ok": None,
            "error": None,
            "warmup": {
                "requested": asr_warmup_request,
                "ok": None,
                "error": None,
                "audio_path": str(asr_warmup_audio) if asr_warmup_audio is not None else None,
                "requested_language": asr_warmup_language,
                "result_language": None,
                "latency_sec": None,
                "text_preview": None,
            },
        },
        "tts": {"requested": preload_tts, "ok": None, "error": None},
    }

    if preload_asr:
        try:
            state.ensure_asr()
            preload["asr"]["ok"] = True
        except Exception as exc:
            preload["asr"]["ok"] = False
            preload["asr"]["error"] = str(exc)
    if preload_tts:
        try:
            state.ensure_tts()
            preload["tts"]["ok"] = True
        except Exception as exc:
            preload["tts"]["ok"] = False
            preload["tts"]["error"] = str(exc)

    if asr_warmup_request:
        try:
            warmup_result = _run_asr_warmup_request(
                state=state,
                audio_path=asr_warmup_audio,
                language=asr_warmup_language,
            )
            preload["asr"]["warmup"]["ok"] = True
            preload["asr"]["warmup"]["latency_sec"] = warmup_result["latency_sec"]
            preload["asr"]["warmup"]["text_preview"] = warmup_result["text_preview"]
            preload["asr"]["warmup"]["audio_path"] = warmup_result["audio_path"]
            preload["asr"]["warmup"]["result_language"] = warmup_result["language"]
        except Exception as exc:
            preload["asr"]["warmup"]["ok"] = False
            preload["asr"]["warmup"]["error"] = str(exc)

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "voice_runtime_service",
        "status": "running",
        "service": {
            "host": host,
            "port": port,
            "base_url": f"http://{host}:{port}",
        },
        "models": {
            "asr_backend": asr_backend,
            "asr_backend_archived": asr_backend in ARCHIVED_ASR_BACKENDS,
            "asr_model": asr_model_id,
            "asr_device": asr_device if asr_backend == "whisper_genai" else device_map,
            "asr_task": asr_task if asr_backend == "whisper_genai" else "transcribe",
            "asr_static_language": asr_static_language if asr_backend == "whisper_genai" else None,
            "asr_warmup_request": asr_warmup_request,
            "asr_warmup_audio": str(asr_warmup_audio) if asr_warmup_audio is not None else None,
            "asr_warmup_language": asr_warmup_language,
            "tts_model": tts_model_id,
            "device_map": device_map,
            "dtype": dtype,
            "asr_max_new_tokens": asr_max_new_tokens,
        },
        "preload": preload,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    handler = _create_handler(state)
    server = ThreadingHTTPServer((host, port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        run_payload["status"] = "stopped"
        _write_json(run_json_path, run_payload)

    return {"run_dir": run_dir, "run_payload": run_payload, "ok": True}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Long-lived voice runtime HTTP service with selectable ASR/TTS runtime backends."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765).")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    parser.add_argument(
        "--asr-backend",
        type=str,
        default="whisper_genai",
        choices=SUPPORTED_ASR_BACKENDS,
        help="ASR backend: whisper_genai (active) or qwen_asr (archived).",
    )
    parser.add_argument(
        "--asr-model",
        type=str,
        default=DEFAULT_WHISPER_GENAI_MODEL_DIR,
        help=(
            "ASR model id/path. For whisper_genai: OpenVINO model directory "
            f"(default: {DEFAULT_WHISPER_GENAI_MODEL_DIR}). "
            "For qwen_asr (archived): HF id/path."
        ),
    )
    parser.add_argument(
        "--asr-device",
        type=str,
        default="NPU",
        choices=("CPU", "GPU", "NPU"),
        help="ASR device for whisper_genai backend (default: NPU).",
    )
    parser.add_argument(
        "--asr-task",
        type=str,
        default="transcribe",
        choices=("transcribe", "translate"),
        help="ASR task for whisper_genai backend (default: transcribe).",
    )
    parser.add_argument(
        "--asr-language",
        type=str,
        default=None,
        help="Optional static language hint for whisper_genai backend (example: en or <|en|>).",
    )
    parser.add_argument(
        "--allow-archived-qwen-asr",
        action="store_true",
        help="Allow archived qwen_asr backend for temporary rollback/testing.",
    )
    parser.add_argument("--tts-model", type=str, default=DEFAULT_QWEN3_TTS_MODEL, help="TTS model id/path.")
    parser.add_argument("--device-map", type=str, default="auto", help="Model device_map.")
    parser.add_argument(
        "--dtype",
        type=str,
        default="auto",
        choices=("auto", "float16", "bfloat16", "float32"),
        help="Torch dtype (default: auto).",
    )
    parser.add_argument("--asr-max-new-tokens", type=int, default=512, help="ASR max_new_tokens.")
    parser.add_argument(
        "--asr-warmup-request",
        action="store_true",
        help="Run one ASR request on startup to warm runtime/graph caches.",
    )
    parser.add_argument(
        "--asr-warmup-audio",
        type=Path,
        default=None,
        help="Optional WAV/audio path for ASR warmup request. If omitted, service uses generated silence WAV.",
    )
    parser.add_argument(
        "--asr-warmup-language",
        type=str,
        default=None,
        help="Optional language hint for ASR warmup request.",
    )
    parser.add_argument("--no-preload-asr", action="store_true", help="Do not preload ASR model on startup.")
    parser.add_argument("--no-preload-tts", action="store_true", help="Do not preload TTS model on startup.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    asr_model_id = args.asr_model
    if args.asr_backend == "whisper_genai" and asr_model_id == DEFAULT_QWEN3_ASR_MODEL:
        asr_model_id = DEFAULT_WHISPER_GENAI_MODEL_DIR

    result = run_voice_runtime_service(
        host=args.host,
        port=args.port,
        runs_dir=args.runs_dir,
        asr_model_id=asr_model_id,
        asr_backend=args.asr_backend,
        asr_device=args.asr_device,
        asr_task=args.asr_task,
        asr_static_language=args.asr_language,
        allow_archived_asr_backend=args.allow_archived_qwen_asr,
        asr_warmup_request=args.asr_warmup_request,
        asr_warmup_audio=args.asr_warmup_audio,
        asr_warmup_language=args.asr_warmup_language,
        tts_model_id=args.tts_model,
        device_map=args.device_map,
        dtype=args.dtype,
        asr_max_new_tokens=args.asr_max_new_tokens,
        preload_asr=not args.no_preload_asr,
        preload_tts=not args.no_preload_tts,
    )
    run_dir = result["run_dir"]
    print(f"[voice_runtime_service] run_dir: {run_dir}")
    print(f"[voice_runtime_service] run_json: {run_dir / 'run.json'}")
    print(f"[voice_runtime_service] base_url: http://{args.host}:{args.port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
