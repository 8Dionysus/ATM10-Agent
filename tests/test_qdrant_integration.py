from __future__ import annotations

from typing import Any

import src.rag.retrieval as retrieval


def _sample_docs() -> list[dict[str, Any]]:
    return [
        {
            "id": "quest:steel_tools",
            "source": "ftbquests",
            "title": "Steel Age",
            "text": "Craft steel tools after alloying iron and coal.",
            "tags": ["quest", "mid-game"],
            "created_at": "2026-02-20T00:00:00+00:00",
            "__path": "data/ftbquests_norm/quests.jsonl",
        },
        {
            "id": "quest:starter",
            "source": "ftbquests",
            "title": "Getting Started",
            "text": "Collect wood and craft stone tools.",
            "tags": ["quest", "early-game"],
            "created_at": "2026-02-20T00:00:00+00:00",
            "__path": "data/ftbquests_norm/quests.jsonl",
        },
    ]


def test_ingest_docs_qdrant_calls_create_and_upsert(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def _fake_qdrant_request(*, method: str, url: str, payload: dict[str, Any] | None, timeout_sec: float) -> dict[str, Any]:
        calls.append({"method": method, "url": url, "payload": payload, "timeout_sec": timeout_sec})
        return {"status": "ok", "result": {"operation_id": 1}}

    monkeypatch.setattr(retrieval, "_qdrant_request", _fake_qdrant_request)

    summary = retrieval.ingest_docs_qdrant(
        _sample_docs(),
        collection="atm10",
        host="127.0.0.1",
        port=6333,
        vector_size=8,
        batch_size=1,
        timeout_sec=3.0,
    )

    assert summary["collection"] == "atm10"
    assert summary["collection_created"] is True
    assert summary["docs_ingested"] == 2
    assert summary["upsert_calls"] == 2
    assert len(calls) == 3
    assert calls[0]["method"] == "PUT"
    assert calls[0]["url"].endswith("/collections/atm10")
    assert calls[1]["url"].endswith("/collections/atm10/points?wait=true")
    first_point = calls[1]["payload"]["points"][0]
    assert len(first_point["vector"]) == 8
    assert first_point["payload"]["id"] == "quest:steel_tools"
    assert first_point["payload"]["path"] == "data/ftbquests_norm/quests.jsonl"


def test_ingest_docs_qdrant_ignores_existing_collection_conflict(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    first_call = True

    def _fake_qdrant_request(*, method: str, url: str, payload: dict[str, Any] | None, timeout_sec: float) -> dict[str, Any]:
        nonlocal first_call
        calls.append({"method": method, "url": url, "payload": payload, "timeout_sec": timeout_sec})
        if first_call:
            first_call = False
            raise RuntimeError(
                f"Qdrant request failed: {method} {url} HTTP 409: "
                '{"status":{"error":"Wrong input: Collection `atm10` already exists!"}}'
            )
        return {"status": "ok", "result": {"operation_id": 1}}

    monkeypatch.setattr(retrieval, "_qdrant_request", _fake_qdrant_request)

    summary = retrieval.ingest_docs_qdrant(
        _sample_docs(),
        collection="atm10",
        host="127.0.0.1",
        port=6333,
        vector_size=8,
        batch_size=2,
        timeout_sec=3.0,
    )

    assert summary["collection_created"] is False
    assert summary["docs_ingested"] == 2
    assert summary["upsert_calls"] == 1
    assert len(calls) == 2
    assert calls[0]["url"].endswith("/collections/atm10")
    assert calls[1]["url"].endswith("/collections/atm10/points?wait=true")


def test_retrieve_top_k_qdrant_maps_payload_to_citations(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def _fake_qdrant_request(*, method: str, url: str, payload: dict[str, Any] | None, timeout_sec: float) -> dict[str, Any]:
        calls.append({"method": method, "url": url, "payload": payload, "timeout_sec": timeout_sec})
        return {
            "status": "ok",
            "result": [
                {
                    "score": 0.91,
                    "payload": {
                        "id": "quest:steel_tools",
                        "source": "ftbquests",
                        "title": "Steel Age",
                        "text": "Craft steel tools after alloying iron and coal.",
                        "path": "data/ftbquests_norm/quests.jsonl",
                    },
                },
                {"score": 0.50, "payload": {"id": "broken"}},
            ],
        }

    monkeypatch.setattr(retrieval, "_qdrant_request", _fake_qdrant_request)

    results = retrieval.retrieve_top_k_qdrant(
        "steel tools",
        collection="atm10",
        topk=3,
        host="localhost",
        port=6333,
        vector_size=8,
        timeout_sec=3.0,
    )

    assert len(results) == 1
    assert results[0]["id"] == "quest:steel_tools"
    assert results[0]["citation"]["source"] == "ftbquests"
    assert results[0]["citation"]["path"] == "data/ftbquests_norm/quests.jsonl"
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"].endswith("/collections/atm10/points/search")
    assert calls[0]["payload"]["limit"] == 3
    assert len(calls[0]["payload"]["vector"]) == 8


def test_retrieve_top_k_qdrant_applies_qwen3_second_stage(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def _fake_qdrant_request(*, method: str, url: str, payload: dict[str, Any] | None, timeout_sec: float) -> dict[str, Any]:
        calls.append({"method": method, "url": url, "payload": payload, "timeout_sec": timeout_sec})
        return {
            "status": "ok",
            "result": [
                {
                    "score": 0.95,
                    "payload": {
                        "id": "quest:first_stage_first",
                        "source": "ftbquests",
                        "title": "First",
                        "text": "steel tools baseline",
                        "path": "data/ftbquests_norm/quests.jsonl",
                    },
                },
                {
                    "score": 0.65,
                    "payload": {
                        "id": "quest:reranked_first",
                        "source": "ftbquests",
                        "title": "Second",
                        "text": "steel tools optimized",
                        "path": "data/ftbquests_norm/quests.jsonl",
                    },
                },
            ],
        }

    def _fake_rerank_candidates_qwen3(query, candidate_docs, *, model_id: str, max_length: int, runtime: str, device: str):
        assert query == "steel tools"
        assert model_id == "Qwen/Qwen3-Reranker-0.6B"
        assert max_length == 1024
        assert runtime == "torch"
        assert device == "AUTO"
        return [(0.88, candidate_docs[1]), (0.12, candidate_docs[0])]

    monkeypatch.setattr(retrieval, "_qdrant_request", _fake_qdrant_request)
    monkeypatch.setattr(retrieval, "_rerank_candidates_qwen3", _fake_rerank_candidates_qwen3)

    results = retrieval.retrieve_top_k_qdrant(
        "steel tools",
        collection="atm10",
        topk=1,
        candidate_k=5,
        reranker="qwen3",
        host="localhost",
        port=6333,
        vector_size=8,
        timeout_sec=3.0,
    )

    assert len(results) == 1
    assert results[0]["id"] == "quest:reranked_first"
    assert results[0]["score"] == 0.88
    assert len(calls) == 1
    assert calls[0]["payload"]["limit"] == 5
