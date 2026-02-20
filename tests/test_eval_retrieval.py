import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.eval_retrieval import run_eval_retrieval


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_run_eval_retrieval_writes_artifacts_and_metrics(tmp_path: Path) -> None:
    docs_path = tmp_path / "docs.jsonl"
    eval_path = tmp_path / "eval.jsonl"
    runs_dir = tmp_path / "runs"
    now = datetime(2026, 2, 20, 17, 45, 0, tzinfo=timezone.utc)

    _write_jsonl(
        docs_path,
        [
            {
                "id": "quest:steel_tools",
                "source": "ftbquests",
                "title": "Steel Age",
                "text": "Craft steel tools after alloying iron and coal.",
                "tags": ["quest", "mid-game"],
                "created_at": "2026-02-20T00:00:00+00:00",
            },
            {
                "id": "quest:starter",
                "source": "ftbquests",
                "title": "Getting Started",
                "text": "Collect wood and craft stone tools.",
                "tags": ["quest", "early-game"],
                "created_at": "2026-02-20T00:00:00+00:00",
            },
        ],
    )
    _write_jsonl(
        eval_path,
        [
            {"id": "q1", "query": "steel tools", "relevant_ids": ["quest:steel_tools"]},
            {"id": "q2", "query": "wood tools", "relevant_ids": ["quest:starter"]},
            {"id": "q3", "query": "nether star", "relevant_ids": ["quest:missing"]},
        ],
    )

    result = run_eval_retrieval(
        backend="in_memory",
        docs_path=docs_path,
        eval_path=eval_path,
        topk=1,
        candidate_k=1,
        reranker="none",
        runs_dir=runs_dir,
        now=now,
    )

    assert result["ok"] is True
    run_dir = result["run_dir"]
    assert run_dir.name == "20260220_174500"
    assert (run_dir / "run.json").exists()
    assert (run_dir / "eval_results.json").exists()

    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    eval_payload = json.loads((run_dir / "eval_results.json").read_text(encoding="utf-8"))

    assert run_payload["status"] == "ok"
    assert run_payload["mode"] == "eval_retrieval"
    assert eval_payload["metrics"]["query_count"] == 3
    assert eval_payload["metrics"]["topk"] == 1
    assert eval_payload["metrics"]["candidate_k"] == 1
    assert eval_payload["metrics"]["mean_recall_at_k"] == pytest.approx(2.0 / 3.0)
    assert eval_payload["metrics"]["mean_mrr_at_k"] == pytest.approx(2.0 / 3.0)
    assert eval_payload["metrics"]["hit_rate_at_k"] == pytest.approx(2.0 / 3.0)
