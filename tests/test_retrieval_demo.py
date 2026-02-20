import json
from pathlib import Path

import src.rag.retrieval as retrieval
from src.rag.retrieval import load_docs, retrieve_top_k


def test_retrieve_top_k_returns_citations_with_path(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "ftbquests_norm" / "quests.jsonl"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "quest:steel_tools",
                        "source": "ftbquests",
                        "title": "Steel Age",
                        "text": "Craft steel tools after alloying iron and coal.",
                        "tags": ["quest", "mid-game"],
                        "created_at": "2026-02-20T00:00:00+00:00",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "id": "quest:starter",
                        "source": "ftbquests",
                        "title": "Getting Started",
                        "text": "Collect wood and craft stone tools.",
                        "tags": ["quest", "early-game"],
                        "created_at": "2026-02-20T00:00:00+00:00",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    docs = load_docs(jsonl_path)
    results = retrieve_top_k("steel tools", docs, topk=2)

    assert len(results) == 2
    assert results[0]["id"] == "quest:steel_tools"
    assert results[0]["citation"]["id"] == "quest:steel_tools"
    assert results[0]["citation"]["source"] == "ftbquests"
    assert results[0]["citation"]["path"] == str(jsonl_path)


def test_retrieve_top_k_respects_candidate_k_limit() -> None:
    docs = [
        {
            "id": "quest:best",
            "source": "ftbquests",
            "title": "Best Match",
            "text": "steel tools progression",
            "tags": ["quest"],
        },
        {
            "id": "quest:second",
            "source": "ftbquests",
            "title": "Second Match",
            "text": "steel furnace setup",
            "tags": ["quest"],
        },
        {
            "id": "quest:third",
            "source": "ftbquests",
            "title": "Third Match",
            "text": "steel armor branch",
            "tags": ["quest"],
        },
    ]

    results = retrieve_top_k("steel tools", docs, topk=2, candidate_k=1, reranker="none")

    assert len(results) == 1
    assert results[0]["id"] == "quest:best"


def test_retrieve_top_k_applies_qwen3_second_stage(monkeypatch) -> None:
    docs = [
        {
            "id": "quest:best_first_stage",
            "source": "ftbquests",
            "title": "First",
            "text": "steel tools progression",
            "tags": ["quest"],
        },
        {
            "id": "quest:reranked_first",
            "source": "ftbquests",
            "title": "Second",
            "text": "steel tools advanced tips",
            "tags": ["quest"],
        },
    ]

    def _fake_rerank_candidates_qwen3(query, candidate_docs, *, model_id: str, max_length: int):
        assert query == "steel tools"
        assert model_id == "Qwen/Qwen3-Reranker-0.6B"
        assert max_length == 1024
        return [(0.99, candidate_docs[1]), (0.10, candidate_docs[0])]

    monkeypatch.setattr(retrieval, "_rerank_candidates_qwen3", _fake_rerank_candidates_qwen3)

    results = retrieve_top_k(
        "steel tools",
        docs,
        topk=2,
        candidate_k=2,
        reranker="qwen3",
    )

    assert len(results) == 2
    assert results[0]["id"] == "quest:reranked_first"
    assert results[0]["score"] == 0.99
