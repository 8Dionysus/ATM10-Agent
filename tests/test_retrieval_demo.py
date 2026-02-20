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

    def _fake_rerank_candidates_qwen3(query, candidate_docs, *, model_id: str, max_length: int, runtime: str, device: str):
        assert query == "steel tools"
        assert model_id == "Qwen/Qwen3-Reranker-0.6B"
        assert max_length == 1024
        assert runtime == "torch"
        assert device == "AUTO"
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


def test_retrieve_top_k_passes_openvino_runtime_options(monkeypatch) -> None:
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

    def _fake_rerank_candidates_qwen3(query, candidate_docs, *, model_id: str, max_length: int, runtime: str, device: str):
        assert query == "steel tools"
        assert runtime == "openvino"
        assert device == "GPU"
        return [(0.90, candidate_docs[1]), (0.80, candidate_docs[0])]

    monkeypatch.setattr(retrieval, "_rerank_candidates_qwen3", _fake_rerank_candidates_qwen3)

    results = retrieve_top_k(
        "steel tools",
        docs,
        topk=2,
        candidate_k=2,
        reranker="qwen3",
        reranker_runtime="openvino",
        reranker_device="GPU",
    )

    assert len(results) == 2
    assert results[0]["id"] == "quest:reranked_first"


def test_retrieve_top_k_matches_space_query_against_underscore_text() -> None:
    docs = [
        {
            "id": "quest:mekanism",
            "source": "ftbquests",
            "title": "mekanism",
            "text": "build metallurgic_infuser and steel_casing early",
            "tags": ["quest"],
        },
        {
            "id": "quest:other",
            "source": "ftbquests",
            "title": "other",
            "text": "basic wood tools progression",
            "tags": ["quest"],
        },
    ]

    results = retrieve_top_k("metallurgic infuser steel casing", docs, topk=1)

    assert len(results) == 1
    assert results[0]["id"] == "quest:mekanism"


def test_retrieve_top_k_matches_space_query_against_underscore_title() -> None:
    docs = [
        {
            "id": "quest:refined_storage",
            "source": "ftbquests",
            "title": "refined_storage",
            "text": "quest chapter",
            "tags": ["quest"],
        },
        {
            "id": "quest:storage",
            "source": "ftbquests",
            "title": "storage",
            "text": "general storage tips",
            "tags": ["quest"],
        },
    ]

    results = retrieve_top_k("refined storage", docs, topk=1)

    assert len(results) == 1
    assert results[0]["id"] == "quest:refined_storage"


def test_retrieve_top_k_prefers_chapter_title_over_sparse_text_mentions() -> None:
    docs = [
        {
            "id": "ftbquests:chapters/allthemodium.snbt",
            "source": "ftbquests",
            "title": "allthemodium",
            "text": "id:ars_nouveau:source_jar id:ars_nouveau:enchanting_apparatus",
            "tags": ["quest", "ftbquests", "snbt"],
        },
        {
            "id": "ftbquests:chapters/ars_nouveau.snbt",
            "source": "ftbquests",
            "title": "ars_nouveau",
            "text": "id:ars_nouveau:glyph_blink id:ars_nouveau:glyph_heal",
            "tags": ["quest", "ftbquests", "snbt"],
        },
    ]

    results = retrieve_top_k("ars nouveau spells", docs, topk=1, candidate_k=2, reranker="none")

    assert len(results) == 1
    assert results[0]["id"] == "ftbquests:chapters/ars_nouveau.snbt"


def test_retrieve_top_k_ignores_stopword_only_title_overlap() -> None:
    docs = [
        {
            "id": "ftbquests:chapters/deeper_and_darker.snbt",
            "source": "ftbquests",
            "title": "deeper_and_darker",
            "text": "warden dimension progression",
            "tags": ["quest", "ftbquests", "snbt"],
        },
        {
            "id": "ftbquests:chapters/mainquestline_part_1.snbt",
            "source": "ftbquests",
            "title": "mainquestline_part_1",
            "text": "starting quest crafting table furnace",
            "tags": ["quest", "ftbquests", "snbt"],
        },
    ]

    results = retrieve_top_k("starting quest crafting table and furnace", docs, topk=1, candidate_k=2, reranker="none")

    assert len(results) == 1
    assert results[0]["id"] == "ftbquests:chapters/mainquestline_part_1.snbt"


def test_resolve_openvino_device_prefers_gpu_for_auto() -> None:
    device = retrieval._resolve_openvino_device("AUTO", ["CPU", "GPU", "NPU"])
    assert device == "GPU"


def test_resolve_openvino_device_raises_for_missing_device() -> None:
    try:
        retrieval._resolve_openvino_device("NPU", ["CPU", "GPU"])
    except RuntimeError as exc:
        assert "unavailable" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for unavailable OpenVINO device")
