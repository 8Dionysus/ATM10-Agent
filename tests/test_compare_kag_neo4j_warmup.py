from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.compare_kag_neo4j_warmup as compare_kag_neo4j_warmup


def test_run_compare_kag_neo4j_warmup_writes_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    eval_path = tmp_path / "eval.jsonl"
    eval_path.write_text('{"id":"q1","query":"x","relevant_ids":["doc:x"]}\n', encoding="utf-8")
    runs_dir = tmp_path / "runs"
    now = datetime(2026, 2, 22, 22, 0, 0, tzinfo=timezone.utc)

    counters: dict[int, int] = {0: 0, 1: 0}
    p95_by_warmup: dict[int, list[float]] = {0: [100.0, 90.0], 1: [70.0, 80.0]}

    def _fake_run_eval_kag_neo4j(
        *,
        eval_path: Path,
        topk: int,
        neo4j_url: str,
        neo4j_database: str,
        neo4j_user: str,
        neo4j_password: str | None,
        timeout_sec: float,
        warmup_runs: int,
        runs_dir: Path,
        now: datetime | None = None,
    ):
        index = counters[warmup_runs]
        counters[warmup_runs] = index + 1
        p95 = p95_by_warmup[warmup_runs][index]
        eval_run_dir = runs_dir / f"inner-w{warmup_runs}-{index + 1}"
        eval_run_dir.mkdir(parents=True, exist_ok=True)
        return {
            "ok": True,
            "run_dir": eval_run_dir,
            "eval_payload": {
                "metrics": {
                    "latency_p95_ms": p95,
                    "mean_mrr_at_k": 0.9375,
                    "hit_rate_at_k": 1.0,
                }
            },
        }

    monkeypatch.setattr(compare_kag_neo4j_warmup, "run_eval_kag_neo4j", _fake_run_eval_kag_neo4j)

    result = compare_kag_neo4j_warmup.run_compare_kag_neo4j_warmup(
        eval_path=eval_path,
        repeats=2,
        baseline_warmup_runs=0,
        candidate_warmup_runs=1,
        topk=5,
        neo4j_url="http://localhost:7474",
        neo4j_database="neo4j",
        neo4j_user="neo4j",
        neo4j_password="secret",
        timeout_sec=10.0,
        runs_dir=runs_dir,
        now=now,
    )

    assert result["ok"] is True
    run_dir = result["run_dir"]
    assert run_dir.name == "20260222_220000-kag-neo4j-warmup-compare"
    assert (run_dir / "run.json").exists()
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "summary.md").exists()

    summary_payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary_payload["baseline"]["metrics"]["latency_p95_ms_avg"] == pytest.approx(95.0)
    assert summary_payload["candidate"]["metrics"]["latency_p95_ms_avg"] == pytest.approx(75.0)
    assert summary_payload["delta"]["p95_delta_ms"] == pytest.approx(-20.0)
    assert summary_payload["delta"]["p95_improvement_ms"] == pytest.approx(20.0)
    assert summary_payload["delta"]["p95_improvement_pct"] == pytest.approx((20.0 / 95.0) * 100.0)

    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "ok"
    assert run_payload["params"]["repeats"] == 2
    assert run_payload["params"]["baseline_warmup_runs"] == 0
    assert run_payload["params"]["candidate_warmup_runs"] == 1


def test_compare_kag_neo4j_warmup_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["compare_kag_neo4j_warmup.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        compare_kag_neo4j_warmup.parse_args()
    assert exc.value.code == 0
