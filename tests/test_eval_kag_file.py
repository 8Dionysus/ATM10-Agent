from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.eval_kag_file import run_eval_kag_file


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_run_eval_kag_file_writes_artifacts_and_metrics(tmp_path: Path) -> None:
    docs_path = tmp_path / "docs.jsonl"
    eval_path = tmp_path / "eval.jsonl"
    runs_dir = tmp_path / "runs"
    now = datetime(2026, 3, 22, 18, 30, 0, tzinfo=timezone.utc)
    _write_jsonl(
        docs_path,
        [
            {
                "id": "quest:steel_tools",
                "source": "ftbquests",
                "title": "Steel Tools",
                "text": "Craft steel tools after alloying iron and coal.",
                "tags": ["quest", "mid-game"],
                "created_at": "2026-03-22T00:00:00+00:00",
            },
            {
                "id": "quest:starter",
                "source": "ftbquests",
                "title": "Getting Started",
                "text": "Collect wood and craft stone tools.",
                "tags": ["quest", "early-game"],
                "created_at": "2026-03-22T00:00:00+00:00",
            },
        ],
    )
    _write_jsonl(
        eval_path,
        [
            {"id": "q1", "query": "steel tools", "relevant_ids": ["quest:steel_tools"]},
            {"id": "q2", "query": "wood tools", "relevant_ids": ["quest:starter"]},
        ],
    )

    result = run_eval_kag_file(
        docs_path=docs_path,
        eval_path=eval_path,
        topk=3,
        runs_dir=runs_dir,
        now=now,
    )

    assert result["ok"] is True
    run_dir = result["run_dir"]
    assert run_dir.name == "20260322_183000-kag-file-eval"
    assert (run_dir / "kag_graph.json").exists()
    eval_payload = json.loads((run_dir / "eval_results.json").read_text(encoding="utf-8"))
    service_sla_payload = json.loads((run_dir / "service_sla_summary.json").read_text(encoding="utf-8"))
    assert eval_payload["schema_version"] == "kag_eval_results_v1"
    assert eval_payload["backend"] == "file"
    assert eval_payload["metrics"]["query_count"] == 2
    assert eval_payload["metrics"]["mean_mrr_at_k"] == pytest.approx(1.0)
    assert eval_payload["metrics"]["latency_p95_ms"] >= 0.0
    assert service_sla_payload["service_name"] == "kag_file"
    assert service_sla_payload["status"] == "ok"


def test_run_eval_kag_file_error_writes_service_sla(tmp_path: Path) -> None:
    result = run_eval_kag_file(
        docs_path=tmp_path / "missing.jsonl",
        eval_path=tmp_path / "eval.jsonl",
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 3, 22, 18, 45, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    service_sla_payload = json.loads(
        (result["run_dir"] / "service_sla_summary.json").read_text(encoding="utf-8")
    )
    assert service_sla_payload["status"] == "error"
    assert service_sla_payload["sla_status"] == "breach"
