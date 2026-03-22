from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.hybrid_query_demo as hybrid_query_demo
from src.hybrid.planner import execute_hybrid_baseline_query, merge_hybrid_results


def _fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / name


def test_merge_hybrid_results_rrf_dedup_and_kag_only_contribution() -> None:
    merged = merge_hybrid_results(
        [
            {
                "id": "doc:steel_tools",
                "source": "ftbquests",
                "title": "Steel Tools",
                "text": "Craft steel tools.",
                "score": 5.0,
                "citation": {"id": "doc:steel_tools", "source": "ftbquests", "path": "docs.jsonl"},
            },
            {
                "id": "doc:furnace",
                "source": "ftbquests",
                "title": "Better Furnace",
                "text": "Smelt faster.",
                "score": 4.0,
                "citation": {"id": "doc:furnace", "source": "ftbquests", "path": "docs.jsonl"},
            },
        ],
        [
            {
                "id": "doc:steel_tools",
                "source": "ftbquests",
                "title": "Steel Tools",
                "score": 3.0,
                "matched_entities": ["steel", "tools"],
                "citation": {"id": "doc:steel_tools", "source": "ftbquests", "path": "docs.jsonl"},
            },
            {
                "id": "doc:hammer",
                "source": "ftbquests",
                "title": "Hammer Time",
                "score": 2.0,
                "matched_entities": ["steel"],
                "citation": {"id": "doc:hammer", "source": "ftbquests", "path": "docs.jsonl"},
            },
        ],
        topk=5,
    )

    assert [item["id"] for item in merged] == ["doc:steel_tools", "doc:furnace", "doc:hammer"]
    assert merged[0]["planner_source"] == "retrieval_and_kag"
    assert merged[0]["retrieval_rank"] == 1
    assert merged[0]["kag_rank"] == 1
    assert merged[0]["matched_entities"] == ["steel", "tools"]
    assert merged[2]["planner_source"] == "kag_only"
    assert merged[2]["retrieval_rank"] is None
    assert merged[2]["kag_rank"] == 2


def test_execute_hybrid_baseline_query_happy_path() -> None:
    result = execute_hybrid_baseline_query(
        query="steel tools",
        docs_path=_fixture_path("retrieval_docs_sample.jsonl"),
        topk=5,
        candidate_k=10,
        reranker="none",
        reranker_model="Qwen/Qwen3-Reranker-0.6B",
        reranker_runtime="torch",
        reranker_device="AUTO",
        reranker_max_length=1024,
        max_entities_per_doc=128,
    )

    assert result["schema_version"] == "hybrid_query_results_v1"
    assert result["planner_mode"] == "retrieval_first_kag_expansion"
    assert result["planner_status"] == "hybrid_merged"
    assert result["degraded"] is False
    assert result["retrieval_results_count"] >= 1
    assert result["kag_results_count"] >= 1
    assert result["results_count"] >= 1
    assert result["merged_results"][0]["citation"]["id"]
    assert isinstance(result["graph_payload"], dict)


def test_execute_hybrid_baseline_query_retrieval_empty_short_circuit() -> None:
    result = execute_hybrid_baseline_query(
        query="ender dragon reactor",
        docs_path=_fixture_path("retrieval_docs_sample.jsonl"),
        topk=5,
        candidate_k=10,
        reranker="none",
        reranker_model="Qwen/Qwen3-Reranker-0.6B",
        reranker_runtime="torch",
        reranker_device="AUTO",
        reranker_max_length=1024,
        max_entities_per_doc=128,
    )

    assert result["planner_status"] == "retrieval_empty"
    assert result["degraded"] is False
    assert result["retrieval_results_count"] == 0
    assert result["kag_results_count"] == 0
    assert result["results_count"] == 0
    assert result["graph_payload"] is None


def test_execute_hybrid_baseline_query_requires_query() -> None:
    with pytest.raises(ValueError, match="query must be non-empty string"):
        execute_hybrid_baseline_query(
            query="",
            docs_path=_fixture_path("retrieval_docs_sample.jsonl"),
            topk=5,
            candidate_k=10,
            reranker="none",
            reranker_model="Qwen/Qwen3-Reranker-0.6B",
            reranker_runtime="torch",
            reranker_device="AUTO",
            reranker_max_length=1024,
            max_entities_per_doc=128,
        )


def test_execute_hybrid_baseline_query_kag_failure_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("kag boom")

    monkeypatch.setattr("src.hybrid.planner.build_kag_graph", _boom)
    result = execute_hybrid_baseline_query(
        query="steel tools",
        docs_path=_fixture_path("retrieval_docs_sample.jsonl"),
        topk=5,
        candidate_k=10,
        reranker="none",
        reranker_model="Qwen/Qwen3-Reranker-0.6B",
        reranker_runtime="torch",
        reranker_device="AUTO",
        reranker_max_length=1024,
        max_entities_per_doc=128,
    )

    assert result["planner_status"] == "retrieval_only_fallback"
    assert result["degraded"] is True
    assert result["retrieval_results_count"] >= 1
    assert result["kag_results_count"] == 0
    assert result["results_count"] >= 1
    assert result["warnings"]


def test_hybrid_query_demo_writes_artifacts(tmp_path: Path) -> None:
    result = hybrid_query_demo.run_hybrid_query(
        query="steel tools",
        docs_path=_fixture_path("retrieval_docs_sample.jsonl"),
        topk=5,
        candidate_k=10,
        reranker="none",
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 3, 22, 16, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    results_payload = json.loads((run_dir / "hybrid_query_results.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_payload["status"] == "ok"
    assert results_payload["schema_version"] == "hybrid_query_results_v1"
    assert results_payload["query"] == "steel tools"
    assert results_payload["paths"]["run_dir"] == str(run_dir)
    assert "merged_results" in results_payload


def test_hybrid_query_demo_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["hybrid_query_demo.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        hybrid_query_demo.parse_args()
    assert exc.value.code == 0
