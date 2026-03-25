from __future__ import annotations

import io
import queue
import re
import threading
import wave
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping

import numpy as np


class TTSRuntimeError(RuntimeError):
    """Raised when no configured TTS engine can satisfy request."""


@dataclass(frozen=True)
class TTSRequest:
    text: str
    language: str = "en"
    speaker: str | None = None
    service_voice: bool = False
    chunk_chars: int | None = None


@dataclass(frozen=True)
class TTSChunk:
    index: int
    text: str
    engine: str
    sample_rate: int
    audio_wav_bytes: bytes
    cached: bool


def _wav_bytes_from_waveform(*, waveform: np.ndarray, sample_rate: int) -> bytes:
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


def make_silence_wav_bytes(*, duration_ms: int = 300, sample_rate: int = 22050) -> bytes:
    num_samples = max(1, int(sample_rate * (float(duration_ms) / 1000.0)))
    waveform = np.zeros(num_samples, dtype=np.float32)
    return _wav_bytes_from_waveform(waveform=waveform, sample_rate=sample_rate)


def split_text_into_chunks(text: str, *, max_chars: int = 220) -> list[str]:
    normalized = " ".join(text.strip().split())
    if not normalized:
        return []
    if max_chars <= 0:
        return [normalized]

    sentence_parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]
    chunks: list[str] = []
    current = ""
    for part in sentence_parts:
        candidate = part if not current else f"{current} {part}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(part) <= max_chars:
            current = part
            continue
        words = part.split()
        line = ""
        for word in words:
            candidate_word = word if not line else f"{line} {word}"
            if len(candidate_word) <= max_chars:
                line = candidate_word
            else:
                if line:
                    chunks.append(line)
                line = word
        if line:
            current = line
    if current:
        chunks.append(current)
    return chunks


class PhraseCache:
    def __init__(self, *, max_items: int = 512) -> None:
        self._max_items = max(1, int(max_items))
        self._lock = threading.RLock()
        self._items: OrderedDict[str, tuple[str, int, bytes]] = OrderedDict()

    def get(self, key: str) -> tuple[str, int, bytes] | None:
        with self._lock:
            value = self._items.get(key)
            if value is None:
                return None
            self._items.move_to_end(key)
            return value

    def put(self, key: str, value: tuple[str, int, bytes]) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)

    def size(self) -> int:
        with self._lock:
            return len(self._items)


class CallbackTTSEngine:
    def __init__(
        self,
        *,
        name: str,
        synthesize_fn: Callable[[str, str, str | None], tuple[bytes, int]],
        prewarm_fn: Callable[[], None] | None = None,
    ) -> None:
        self.name = name
        self._synthesize_fn = synthesize_fn
        self._prewarm_fn = prewarm_fn

    def prewarm(self) -> None:
        if self._prewarm_fn is not None:
            self._prewarm_fn()

    def synthesize(self, *, text: str, language: str, speaker: str | None) -> tuple[bytes, int]:
        return self._synthesize_fn(text, language, speaker)


class TTSRuntimeService:
    def __init__(
        self,
        *,
        xtts_engine: CallbackTTSEngine | None,
        piper_engine: CallbackTTSEngine | None,
        silero_engine: CallbackTTSEngine | None,
        fallback_engine: CallbackTTSEngine | None = None,
        fallback_engines: list[CallbackTTSEngine] | None = None,
        max_chunk_chars: int = 220,
        queue_size: int = 128,
        cache: PhraseCache | None = None,
        effective_config: Mapping[str, Any] | None = None,
    ) -> None:
        self.xtts_engine = xtts_engine
        self.piper_engine = piper_engine
        self.silero_engine = silero_engine
        self.fallback_engine = fallback_engine
        combined_fallbacks: list[CallbackTTSEngine] = []
        if fallback_engine is not None:
            combined_fallbacks.append(fallback_engine)
        if fallback_engines:
            combined_fallbacks.extend(engine for engine in fallback_engines if engine is not None)
        self.fallback_engines = combined_fallbacks
        self.max_chunk_chars = max(20, int(max_chunk_chars))
        self.cache = cache or PhraseCache(max_items=512)
        self._effective_config = dict(effective_config or {})

        self._queue: queue.Queue[tuple[TTSRequest, Future[dict[str, Any]]] | None] = queue.Queue(maxsize=queue_size)
        self._worker: threading.Thread | None = None
        self._lock = threading.RLock()
        self._prewarm_status: dict[str, dict[str, Any]] = {}

    def _router_chain(self, request: TTSRequest) -> list[CallbackTTSEngine]:
        language = request.language.lower().strip()
        if request.service_voice and language.startswith("ru"):
            engines = [self.silero_engine, self.piper_engine]
        else:
            engines = [self.xtts_engine, self.piper_engine]
        engines.extend(self.fallback_engines)
        return [engine for engine in engines if engine is not None]

    def _cache_key(self, *, request: TTSRequest, chunk_text: str) -> str:
        speaker = request.speaker or ""
        return f"{request.language.lower()}|{speaker.lower()}|{int(request.service_voice)}|{chunk_text.lower()}"

    def _synthesize_chunk(self, *, request: TTSRequest, index: int, chunk_text: str) -> TTSChunk:
        cache_key = self._cache_key(request=request, chunk_text=chunk_text)
        cached = self.cache.get(cache_key)
        if cached is not None:
            engine_name, sample_rate, wav_bytes = cached
            return TTSChunk(
                index=index,
                text=chunk_text,
                engine=engine_name,
                sample_rate=sample_rate,
                audio_wav_bytes=wav_bytes,
                cached=True,
            )

        errors: list[str] = []
        for engine in self._router_chain(request):
            try:
                wav_bytes, sample_rate = engine.synthesize(
                    text=chunk_text,
                    language=request.language,
                    speaker=request.speaker,
                )
                self.cache.put(cache_key, (engine.name, int(sample_rate), bytes(wav_bytes)))
                return TTSChunk(
                    index=index,
                    text=chunk_text,
                    engine=engine.name,
                    sample_rate=int(sample_rate),
                    audio_wav_bytes=bytes(wav_bytes),
                    cached=False,
                )
            except Exception as exc:  # pragma: no cover - defensive path
                errors.append(f"{engine.name}: {exc}")

        raise TTSRuntimeError(f"No TTS engine succeeded. Errors: {errors}")

    def iter_synthesize(self, request: TTSRequest) -> Iterator[TTSChunk]:
        text_chunks = split_text_into_chunks(
            request.text,
            max_chars=request.chunk_chars or self.max_chunk_chars,
        )
        if not text_chunks:
            raise ValueError("text must be non-empty.")
        for index, chunk_text in enumerate(text_chunks):
            yield self._synthesize_chunk(request=request, index=index, chunk_text=chunk_text)

    def synthesize(self, request: TTSRequest) -> dict[str, Any]:
        chunks = list(self.iter_synthesize(request))

        return {
            "chunk_count": len(chunks),
            "cache_hits": sum(1 for item in chunks if item.cached),
            "chunks": chunks,
            "router_chain": [engine.name for engine in self._router_chain(request)],
        }

    def prewarm(self) -> dict[str, dict[str, Any]]:
        status: dict[str, dict[str, Any]] = {}
        for engine in (self.xtts_engine, self.piper_engine, self.silero_engine, *self.fallback_engines):
            if engine is None:
                continue
            try:
                engine.prewarm()
                status[engine.name] = {"ok": True, "error": None}
            except Exception as exc:  # pragma: no cover - defensive path
                status[engine.name] = {"ok": False, "error": str(exc)}
        with self._lock:
            self._prewarm_status = status
        return status

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            request, future = item
            try:
                result = self.synthesize(request)
            except Exception as exc:
                future.set_exception(exc)
            else:
                future.set_result(result)
            finally:
                self._queue.task_done()

    def start(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._worker_loop, name="tts-runtime-worker", daemon=True)
            self._worker.start()

    def stop(self) -> None:
        with self._lock:
            if self._worker is None:
                return
            self._queue.put(None)
            self._worker.join(timeout=2.0)
            self._worker = None

    def submit(self, request: TTSRequest) -> Future[dict[str, Any]]:
        self.start()
        future: Future[dict[str, Any]] = Future()
        self._queue.put((request, future))
        return future

    def _piper_diagnostics(self, prewarm: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        piper_config = self._effective_config.get("piper")
        piper_config = piper_config if isinstance(piper_config, Mapping) else {}
        piper_model_path = piper_config.get("model_path")
        piper_configured = (
            isinstance(piper_model_path, str) and bool(piper_model_path.strip())
        )
        piper_prewarm = prewarm.get("piper")
        piper_prewarm = piper_prewarm if isinstance(piper_prewarm, Mapping) else {}
        piper_prewarm_ok = piper_prewarm.get("ok")
        if not isinstance(piper_prewarm_ok, bool):
            piper_prewarm_ok = None
        piper_error = str(piper_prewarm.get("error", "")).strip() or None
        preferred_tts_engine = "piper" if piper_configured else "windows_sapi_fallback"
        tts_degraded_reason: str | None = None
        if piper_configured:
            if piper_prewarm_ok is False and piper_error:
                tts_degraded_reason = piper_error
            elif piper_prewarm_ok is False:
                tts_degraded_reason = "piper_prewarm_failed"
            elif piper_prewarm_ok is None:
                tts_degraded_reason = "piper_prewarm_not_run"
        elif self.fallback_engines:
            tts_degraded_reason = "piper_not_configured"
        return {
            "preferred_tts_engine": preferred_tts_engine,
            "piper_available": piper_configured,
            "piper_prewarm_ok": piper_prewarm_ok,
            "tts_degraded_reason": tts_degraded_reason,
            "engines": {
                "piper": {
                    "configured": piper_configured,
                    "ok": piper_prewarm_ok,
                    "error": piper_error,
                }
            },
            "effective_config": dict(self._effective_config),
        }

    def health(self) -> dict[str, Any]:
        with self._lock:
            worker_alive = self._worker is not None and self._worker.is_alive()
            prewarm = dict(self._prewarm_status)
        piper_diagnostics = self._piper_diagnostics(prewarm)
        return {
            "status": "ok",
            "worker_alive": worker_alive,
            "queue_size": self._queue.qsize(),
            "cache_items": self.cache.size(),
            "prewarm": prewarm,
            **piper_diagnostics,
        }
