from __future__ import annotations

import pytest

from src.agent_core.tts_runtime import (
    CallbackTTSEngine,
    PhraseCache,
    TTSRequest,
    TTSRuntimeService,
    make_silence_wav_bytes,
    split_text_into_chunks,
)


def test_split_text_into_chunks_respects_max_chars() -> None:
    text = "First sentence. Second sentence is longer than first. Third one."
    chunks = split_text_into_chunks(text, max_chars=24)
    assert chunks
    assert all(len(chunk) <= 24 for chunk in chunks)


def test_runtime_falls_back_to_piper_when_xtts_fails() -> None:
    xtts = CallbackTTSEngine(
        name="xtts_v2",
        synthesize_fn=lambda _text, _language, _speaker: (_ for _ in ()).throw(RuntimeError("xtts failed")),
    )
    piper = CallbackTTSEngine(
        name="piper",
        synthesize_fn=lambda text, _language, _speaker: (make_silence_wav_bytes(duration_ms=200 + len(text)), 22050),
    )
    service = TTSRuntimeService(
        xtts_engine=xtts,
        piper_engine=piper,
        silero_engine=None,
        cache=PhraseCache(max_items=16),
    )

    result = service.synthesize(TTSRequest(text="hello world", language="en"))

    assert result["chunk_count"] == 1
    assert result["chunks"][0].engine == "piper"
    assert result["chunks"][0].cached is False


def test_runtime_uses_silero_for_ru_service_voice() -> None:
    calls: dict[str, int] = {"silero": 0}

    silero = CallbackTTSEngine(
        name="silero_ru_service",
        synthesize_fn=lambda text, _language, _speaker: (
            calls.__setitem__("silero", calls["silero"] + 1) or make_silence_wav_bytes(duration_ms=200 + len(text)),
            24000,
        ),
    )
    service = TTSRuntimeService(
        xtts_engine=None,
        piper_engine=None,
        silero_engine=silero,
        cache=PhraseCache(max_items=16),
    )

    result = service.synthesize(TTSRequest(text="служебное сообщение", language="ru", service_voice=True))

    assert calls["silero"] == 1
    assert result["chunks"][0].engine == "silero_ru_service"


def test_phrase_cache_avoids_duplicate_engine_calls() -> None:
    calls = {"xtts": 0}

    def _xtts_synthesize(text: str, _language: str, _speaker: str | None):
        calls["xtts"] += 1
        return make_silence_wav_bytes(duration_ms=250 + len(text)), 22050

    service = TTSRuntimeService(
        xtts_engine=CallbackTTSEngine(name="xtts_v2", synthesize_fn=_xtts_synthesize),
        piper_engine=None,
        silero_engine=None,
        cache=PhraseCache(max_items=16),
    )

    first = service.synthesize(TTSRequest(text="cache me"))
    second = service.synthesize(TTSRequest(text="cache me"))

    assert calls["xtts"] == 1
    assert first["chunks"][0].cached is False
    assert second["chunks"][0].cached is True
    assert second["cache_hits"] == 1


def test_iter_synthesize_yields_first_chunk_without_waiting_for_full_request() -> None:
    calls: list[str] = []

    def _xtts_synthesize(text: str, _language: str, _speaker: str | None):
        calls.append(text)
        return make_silence_wav_bytes(duration_ms=120), 22050

    service = TTSRuntimeService(
        xtts_engine=CallbackTTSEngine(name="xtts_v2", synthesize_fn=_xtts_synthesize),
        piper_engine=None,
        silero_engine=None,
        cache=PhraseCache(max_items=16),
    )

    iterator = service.iter_synthesize(TTSRequest(text="alpha beta gamma", chunk_chars=5))
    first_chunk = next(iterator)

    assert first_chunk.text == "alpha"
    assert calls == ["alpha"]

    rest = list(iterator)
    assert [item.text for item in rest] == ["beta", "gamma"]
    assert calls == ["alpha", "beta", "gamma"]


def test_queue_submit_processes_request() -> None:
    service = TTSRuntimeService(
        xtts_engine=CallbackTTSEngine(
            name="xtts_v2",
            synthesize_fn=lambda text, _language, _speaker: (make_silence_wav_bytes(duration_ms=200 + len(text)), 22050),
        ),
        piper_engine=None,
        silero_engine=None,
        cache=PhraseCache(max_items=16),
    )
    try:
        future = service.submit(TTSRequest(text="queued request"))
        result = future.result(timeout=2.0)
        assert result["chunk_count"] == 1
        assert result["chunks"][0].engine == "xtts_v2"
    finally:
        service.stop()
