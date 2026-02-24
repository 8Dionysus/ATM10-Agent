from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.kag_guardrail_trend_snapshot as trend_snapshot


def _write_eval_results(path: Path, *, recall: float, mrr: float, hit_rate: float, latency_p95_ms: float) -> None:
    payload = {
        "metrics": {
            "query_count": 8,
            "topk": 5,
            "mean_recall_at_k": recall,
            "mean_mrr_at_k": mrr,
            "hit_rate_at_k": hit_rate,
            "latency_mean_ms": 70.0,
            "latency_p95_ms": latency_p95_ms,
            "latency_max_ms": 90.0,
        },
        "cases": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_run_kag_guardrail_trend_snapshot_writes_artifacts(tmp_path: Path) -> None:
    sample_runs_dir = tmp_path / "sample"
    hard_runs_dir = tmp_path / "hard"
    _write_eval_results(
        sample_runs_dir / "20260223_100000-kag-neo4j-eval" / "eval_results.json",
        recall=1.0,
        mrr=0.83,
        hit_rate=1.0,
        latency_p95_ms=72.1,
    )
    _write_eval_results(
        sample_runs_dir / "20260223_110000-kag-neo4j-eval" / "eval_results.json",
        recall=1.0,
        mrr=0.84,
        hit_rate=1.0,
        latency_p95_ms=70.0,
    )
    _write_eval_results(
        hard_runs_dir / "20260223_100500-kag-neo4j-eval" / "eval_results.json",
        recall=1.0,
        mrr=0.93,
        hit_rate=1.0,
        latency_p95_ms=92.4,
    )
    _write_eval_results(
        hard_runs_dir / "20260223_110500-kag-neo4j-eval" / "eval_results.json",
        recall=1.0,
        mrr=0.94,
        hit_rate=1.0,
        latency_p95_ms=95.0,
    )

    result = trend_snapshot.run_kag_guardrail_trend_snapshot(
        sample_runs_dir=sample_runs_dir,
        hard_runs_dir=hard_runs_dir,
        history_limit=2,
        baseline_window=2,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 23, 21, 0, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    run_dir = result["run_dir"]
    assert run_dir.name == "20260223_210000-kag-guardrail-trend"
    assert (run_dir / "run.json").exists()
    assert (run_dir / "trend_snapshot.json").exists()
    assert (run_dir / "summary.md").exists()

    snapshot = json.loads((run_dir / "trend_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["profiles"]["sample"]["latest"]["run_name"] == "20260223_110000-kag-neo4j-eval"
    assert snapshot["profiles"]["hard"]["latest"]["run_name"] == "20260223_110500-kag-neo4j-eval"
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["count"] == 1
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["metrics_mean"]["mean_mrr_at_k"] == pytest.approx(0.83)
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["delta_latest_minus_baseline"][
        "delta_mean_mrr_at_k"
    ] == pytest.approx(0.01)
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["comparison_evaluated"] is True
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["mrr_status"] == "improved"
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["latency_p95_status"] == "improved"
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["mrr_regression_severity"] == "none"
    assert (
        snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["latency_p95_regression_severity"]
        == "none"
    )
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["max_regression_severity"] == "none"
    assert (
        snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["has_warn_or_higher_regression"]
        is False
    )
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["has_any_regression"] is False
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["count"] == 1
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["metrics_mean"]["latency_p95_ms"] == pytest.approx(92.4)
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["delta_latest_minus_baseline"][
        "delta_latency_p95_ms"
    ] == pytest.approx(2.6)
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["comparison_evaluated"] is True
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["mrr_status"] == "improved"
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["latency_p95_status"] == "regressed"
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["mrr_regression_severity"] == "none"
    assert (
        snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["latency_p95_regression_severity"]
        == "warn"
    )
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["max_regression_severity"] == "warn"
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["has_warn_or_higher_regression"] is True
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["has_any_regression"] is True
    assert snapshot["severity_thresholds"]["mrr"]["warn_delta_latest_minus_baseline"] == pytest.approx(0.005)
    assert snapshot["severity_thresholds"]["mrr"]["critical_delta_latest_minus_baseline"] == pytest.approx(0.02)
    assert snapshot["severity_thresholds"]["latency_p95_ms"]["warn_delta_latest_minus_baseline"] == pytest.approx(2.0)
    assert snapshot["severity_thresholds"]["latency_p95_ms"]["critical_delta_latest_minus_baseline"] == pytest.approx(8.0)
    assert snapshot["comparison"]["latest_hard_minus_sample"]["delta_mrr"] == pytest.approx(0.10)
    assert snapshot["comparison"]["latest_hard_minus_sample"]["delta_latency_p95_ms"] == pytest.approx(25.0)


def test_run_kag_guardrail_trend_snapshot_rolling_baseline_is_empty_with_single_run(tmp_path: Path) -> None:
    sample_runs_dir = tmp_path / "sample"
    hard_runs_dir = tmp_path / "hard"
    _write_eval_results(
        sample_runs_dir / "20260223_110000-kag-neo4j-eval" / "eval_results.json",
        recall=1.0,
        mrr=0.84,
        hit_rate=1.0,
        latency_p95_ms=70.0,
    )
    _write_eval_results(
        hard_runs_dir / "20260223_110500-kag-neo4j-eval" / "eval_results.json",
        recall=1.0,
        mrr=0.94,
        hit_rate=1.0,
        latency_p95_ms=95.0,
    )

    result = trend_snapshot.run_kag_guardrail_trend_snapshot(
        sample_runs_dir=sample_runs_dir,
        hard_runs_dir=hard_runs_dir,
        history_limit=2,
        baseline_window=3,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 23, 21, 0, 30, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    snapshot = json.loads((result["run_dir"] / "trend_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["count"] == 0
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["metrics_mean"] is None
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["delta_latest_minus_baseline"] is None
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["comparison_evaluated"] is False
    assert (
        snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["mrr_status"]
        == "insufficient_history"
    )
    assert (
        snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["latency_p95_status"]
        == "insufficient_history"
    )
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["mrr_regression_severity"] == "none"
    assert (
        snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["latency_p95_regression_severity"]
        == "none"
    )
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["max_regression_severity"] == "none"
    assert (
        snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["has_warn_or_higher_regression"]
        is False
    )
    assert snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]["has_any_regression"] is False
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["count"] == 0
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["metrics_mean"] is None
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["delta_latest_minus_baseline"] is None
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["comparison_evaluated"] is False
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["mrr_status"] == "insufficient_history"
    assert (
        snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["latency_p95_status"]
        == "insufficient_history"
    )
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["mrr_regression_severity"] == "none"
    assert (
        snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["latency_p95_regression_severity"]
        == "none"
    )
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["max_regression_severity"] == "none"
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["has_warn_or_higher_regression"] is False
    assert snapshot["profiles"]["hard"]["rolling_baseline"]["regression_flags"]["has_any_regression"] is False


def test_run_kag_guardrail_trend_snapshot_marks_critical_regression_by_threshold(tmp_path: Path) -> None:
    sample_runs_dir = tmp_path / "sample"
    hard_runs_dir = tmp_path / "hard"
    _write_eval_results(
        sample_runs_dir / "20260223_100000-kag-neo4j-eval" / "eval_results.json",
        recall=1.0,
        mrr=0.90,
        hit_rate=1.0,
        latency_p95_ms=60.0,
    )
    _write_eval_results(
        sample_runs_dir / "20260223_110000-kag-neo4j-eval" / "eval_results.json",
        recall=1.0,
        mrr=0.85,
        hit_rate=1.0,
        latency_p95_ms=72.5,
    )
    _write_eval_results(
        hard_runs_dir / "20260223_100500-kag-neo4j-eval" / "eval_results.json",
        recall=1.0,
        mrr=0.95,
        hit_rate=1.0,
        latency_p95_ms=80.0,
    )
    _write_eval_results(
        hard_runs_dir / "20260223_110500-kag-neo4j-eval" / "eval_results.json",
        recall=1.0,
        mrr=0.90,
        hit_rate=1.0,
        latency_p95_ms=88.1,
    )

    result = trend_snapshot.run_kag_guardrail_trend_snapshot(
        sample_runs_dir=sample_runs_dir,
        hard_runs_dir=hard_runs_dir,
        history_limit=2,
        baseline_window=2,
        mrr_warn_delta=0.01,
        mrr_critical_delta=0.03,
        latency_warn_delta_ms=4.0,
        latency_critical_delta_ms=8.0,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 23, 21, 0, 45, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    snapshot = json.loads((result["run_dir"] / "trend_snapshot.json").read_text(encoding="utf-8"))
    sample_flags = snapshot["profiles"]["sample"]["rolling_baseline"]["regression_flags"]
    assert sample_flags["mrr_status"] == "regressed"
    assert sample_flags["latency_p95_status"] == "regressed"
    assert sample_flags["mrr_regression_severity"] == "critical"
    assert sample_flags["latency_p95_regression_severity"] == "critical"
    assert sample_flags["max_regression_severity"] == "critical"
    assert sample_flags["has_warn_or_higher_regression"] is True
    assert sample_flags["has_any_regression"] is True


def test_run_kag_guardrail_trend_snapshot_returns_error_on_missing_profile(tmp_path: Path) -> None:
    sample_runs_dir = tmp_path / "sample"
    hard_runs_dir = tmp_path / "hard"
    _write_eval_results(
        sample_runs_dir / "20260223_100000-kag-neo4j-eval" / "eval_results.json",
        recall=1.0,
        mrr=0.83,
        hit_rate=1.0,
        latency_p95_ms=72.1,
    )
    result = trend_snapshot.run_kag_guardrail_trend_snapshot(
        sample_runs_dir=sample_runs_dir,
        hard_runs_dir=hard_runs_dir,
        history_limit=2,
        baseline_window=2,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 23, 21, 1, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is False
    assert result["run_payload"]["status"] == "error"
    assert result["run_payload"]["error_code"] == "guardrail_trend_failed"


def test_kag_guardrail_trend_snapshot_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["kag_guardrail_trend_snapshot.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        trend_snapshot.parse_args()
    assert exc.value.code == 0
