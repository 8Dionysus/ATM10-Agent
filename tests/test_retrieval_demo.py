import json
from pathlib import Path

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
