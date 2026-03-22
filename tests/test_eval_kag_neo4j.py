from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.eval_kag_neo4j as eval_kag_neo4j


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_run_eval_kag_neo4j_writes_artifacts_and_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    eval_path = tmp_path / "eval.jsonl"
    runs_dir = tmp_path / "runs"
    now = datetime(2026, 2, 22, 18, 30, 0, tzinfo=timezone.utc)
    _write_jsonl(
        eval_path,
        [
            {"id": "q1", "query": "steel tools", "relevant_ids": ["quest:steel_tools"]},
            {"id": "q2", "query": "wood tools", "relevant_ids": ["quest:starter"]},
            {"id": "q3", "query": "nether star", "relevant_ids": ["quest:missing"]},
        ],
    )

    def _fake_query_kag_neo4j(*, url: str, database: str, user: str, password: str, query: str, topk: int, timeout_sec: float):
        assert url == "http://localhost:7474"
        assert database == "neo4j"
        assert user == "neo4j"
        assert password == "secret"
        assert topk == 3
        assert timeout_sec == 5.0
        if query == "steel tools":
            return [{"id": "quest:steel_tools"}]
        if query == "wood tools":
            return [{"id": "quest:starter"}]
        return []

    monkeypatch.setattr(eval_kag_neo4j, "query_kag_neo4j", _fake_query_kag_neo4j)

    result = eval_kag_neo4j.run_eval_kag_neo4j(
        eval_path=eval_path,
        topk=3,
        neo4j_url="http://localhost:7474",
        neo4j_database="neo4j",
        neo4j_user="neo4j",
        neo4j_password="secret",
        timeout_sec=5.0,
        runs_dir=runs_dir,
        now=now,
    )

    assert result["ok"] is True
    run_dir = result["run_dir"]
    assert run_dir.name == "20260222_183000-kag-neo4j-eval"
    assert (run_dir / "run.json").exists()
    assert (run_dir / "eval_results.json").exists()
    assert (run_dir / "summary.md").exists()
    assert (run_dir / "service_sla_summary.json").exists()

    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    eval_payload = json.loads((run_dir / "eval_results.json").read_text(encoding="utf-8"))
    service_sla_payload = json.loads((run_dir / "service_sla_summary.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "ok"
    assert run_payload["mode"] == "eval_kag_neo4j"
    assert run_payload["params"]["warmup_runs"] == 0
    assert run_payload["warmup"]["executed_calls"] == 0
    assert eval_payload["schema_version"] == "kag_eval_results_v1"
    assert eval_payload["backend"] == "neo4j"
    assert eval_payload["metrics"]["query_count"] == 3
    assert eval_payload["metrics"]["topk"] == 3
    assert eval_payload["metrics"]["mean_recall_at_k"] == pytest.approx(2.0 / 3.0)
    assert eval_payload["metrics"]["mean_mrr_at_k"] == pytest.approx(2.0 / 3.0)
    assert eval_payload["metrics"]["hit_rate_at_k"] == pytest.approx(2.0 / 3.0)
    assert eval_payload["metrics"]["latency_mean_ms"] >= 0.0
    assert eval_payload["metrics"]["latency_p95_ms"] >= 0.0
    assert eval_payload["metrics"]["latency_max_ms"] >= 0.0
    assert service_sla_payload["service_name"] == "kag_neo4j"
    assert service_sla_payload["status"] == "ok"

    summary_md = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "# KAG Neo4j Eval Summary" in summary_md
    assert "| id | query | first_hit_rank | recall | mrr | latency_ms |" in summary_md


def test_run_eval_kag_neo4j_warmup_runs_do_not_affect_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    eval_path = tmp_path / "eval.jsonl"
    runs_dir = tmp_path / "runs"
    now = datetime(2026, 2, 22, 18, 45, 0, tzinfo=timezone.utc)
    _write_jsonl(
        eval_path,
        [
            {"id": "q1", "query": "alpha", "relevant_ids": ["doc:alpha"]},
            {"id": "q2", "query": "beta", "relevant_ids": ["doc:beta"]},
        ],
    )
    calls: dict[str, int] = {"alpha": 0, "beta": 0}

    def _fake_query_kag_neo4j(*, url: str, database: str, user: str, password: str, query: str, topk: int, timeout_sec: float):
        calls[query] += 1
        if query == "alpha":
            return [{"id": "doc:alpha"}]
        return [{"id": "doc:beta"}]

    monkeypatch.setattr(eval_kag_neo4j, "query_kag_neo4j", _fake_query_kag_neo4j)

    result = eval_kag_neo4j.run_eval_kag_neo4j(
        eval_path=eval_path,
        topk=5,
        neo4j_url="http://localhost:7474",
        neo4j_database="neo4j",
        neo4j_user="neo4j",
        neo4j_password="secret",
        timeout_sec=5.0,
        warmup_runs=2,
        runs_dir=runs_dir,
        now=now,
    )

    assert result["ok"] is True
    assert calls["alpha"] == 3
    assert calls["beta"] == 3
    run_payload = json.loads((result["run_dir"] / "run.json").read_text(encoding="utf-8"))
    eval_payload = json.loads((result["run_dir"] / "eval_results.json").read_text(encoding="utf-8"))
    assert run_payload["params"]["warmup_runs"] == 2
    assert run_payload["warmup"]["requested_runs"] == 2
    assert run_payload["warmup"]["executed_calls"] == 4
    assert eval_payload["metrics"]["query_count"] == 2
    assert eval_payload["metrics"]["mean_recall_at_k"] == pytest.approx(1.0)
    assert eval_payload["metrics"]["mean_mrr_at_k"] == pytest.approx(1.0)
    assert eval_payload["metrics"]["hit_rate_at_k"] == pytest.approx(1.0)


def test_eval_kag_neo4j_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["eval_kag_neo4j.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        eval_kag_neo4j.parse_args()
    assert exc.value.code == 0
