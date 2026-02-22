from __future__ import annotations

import argparse
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _disabled_engine(name: str, reason: str) -> CallbackTTSEngine:
    def _synthesize(_text: str, _language: str, _speaker: str | None) -> tuple[bytes, int]:
        raise TTSRuntimeError(f"{name} is unavailable: {reason}")

    return CallbackTTSEngine(name=name, synthesize_fn=_synthesize)


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


def _build_piper_engine() -> CallbackTTSEngine:
    piper_executable = os.getenv("PIPER_EXECUTABLE", "piper")
    piper_model_path = os.getenv("PIPER_MODEL_PATH")
    default_speaker = os.getenv("PIPER_SPEAKER")

    if not piper_model_path:
        return _disabled_engine("piper", "PIPER_MODEL_PATH is not set.")

    def _synthesize(text: str, _language: str, speaker: str | None) -> tuple[bytes, int]:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            output_path = Path(temp_file.name)
        command = [
            piper_executable,
            "--model",
            str(piper_model_path),
            "--output_file",
            str(output_path),
        ]
        selected_speaker = speaker or default_speaker
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

    return CallbackTTSEngine(name="piper", synthesize_fn=_synthesize)


def _build_silero_engine() -> CallbackTTSEngine:
    repo_or_dir = os.getenv("SILERO_REPO_OR_DIR", "snakers4/silero-models")
    model_language = os.getenv("SILERO_MODEL_LANGUAGE", "ru")
    model_id = os.getenv("SILERO_MODEL_ID", "v4_ru")
    sample_rate = int(os.getenv("SILERO_SAMPLE_RATE", "24000"))
    default_speaker = os.getenv("SILERO_SPEAKER", "xenia")
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
                    repo_or_dir=repo_or_dir,
                    model="silero_tts",
                    language=model_language,
                    speaker=model_id,
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


def _build_default_service(*, cache_items: int, chunk_chars: int, queue_size: int) -> TTSRuntimeService:
    xtts = _build_xtts_engine()
    piper = _build_piper_engine()
    silero = _build_silero_engine()
    return TTSRuntimeService(
        xtts_engine=xtts,
        piper_engine=piper,
        silero_engine=silero,
        max_chunk_chars=chunk_chars,
        queue_size=queue_size,
        cache=PhraseCache(max_items=cache_items),
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


def _request_from_payload(payload: dict[str, Any]) -> TTSRequest:
    text = str(payload.get("text", "")).strip()
    if not text:
        raise ValueError("text is required and must be non-empty.")
    language = str(payload.get("language", "en")).strip() or "en"
    speaker_value = payload.get("speaker")
    speaker = str(speaker_value).strip() if isinstance(speaker_value, str) and speaker_value.strip() else None
    service_voice = bool(payload.get("service_voice", False))
    chunk_chars_value = payload.get("chunk_chars")
    chunk_chars = int(chunk_chars_value) if isinstance(chunk_chars_value, int) and chunk_chars_value > 0 else None
    return TTSRequest(
        text=text,
        language=language,
        speaker=speaker,
        service_voice=service_voice,
        chunk_chars=chunk_chars,
    )


def create_app(service: TTSRuntimeService, *, prewarm: bool) -> Any:
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import StreamingResponse
    except Exception as exc:  # pragma: no cover - dependency presence
        raise RuntimeError("FastAPI/uvicorn are required for tts_runtime_service.") from exc

    app = FastAPI(title="ATM10 TTS Runtime", version="0.1.0")

    @app.on_event("startup")
    def _on_startup() -> None:
        service.start()
        if prewarm:
            service.prewarm()

    @app.on_event("shutdown")
    def _on_shutdown() -> None:
        service.stop()

    @app.get("/health")
    def _health() -> dict[str, Any]:
        return {"timestamp_utc": _utc_now(), **service.health()}

    @app.post("/tts")
    def _tts(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            request = _request_from_payload(payload)
            result = service.submit(request).result(timeout=120.0)
            return {"ok": True, "result": _serialize_result(result)}
        except (ValueError, TTSRuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/tts_stream")
    def _tts_stream(payload: dict[str, Any]) -> StreamingResponse:
        try:
            request = _request_from_payload(payload)
            result = service.submit(request).result(timeout=120.0)
            serialized = _serialize_result(result)
        except (ValueError, TTSRuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        def _iter_events():
            yield json.dumps({"event": "started", "timestamp_utc": _utc_now()}, ensure_ascii=False) + "\n"
            for chunk in serialized["chunks"]:
                yield json.dumps({"event": "audio_chunk", **chunk}, ensure_ascii=False) + "\n"
            yield (
                json.dumps(
                    {
                        "event": "completed",
                        "timestamp_utc": _utc_now(),
                        "chunk_count": serialized["chunk_count"],
                        "cache_hits": serialized["cache_hits"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        return StreamingResponse(_iter_events(), media_type="application/x-ndjson")

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FastAPI TTS runtime: XTTSv2 + fallback Piper/Silero.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8780, help="Bind port (default: 8780).")
    parser.add_argument("--queue-size", type=int, default=128, help="Queue max size (default: 128).")
    parser.add_argument("--chunk-chars", type=int, default=220, help="Chunk size for long text (default: 220).")
    parser.add_argument("--cache-items", type=int, default=512, help="Phrase cache max entries (default: 512).")
    parser.add_argument("--no-prewarm", action="store_true", help="Disable prewarm on startup.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - dependency presence
        raise SystemExit("uvicorn is required. Install fastapi + uvicorn.") from exc

    service = _build_default_service(
        cache_items=args.cache_items,
        chunk_chars=args.chunk_chars,
        queue_size=args.queue_size,
    )
    app = create_app(service, prewarm=not args.no_prewarm)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
