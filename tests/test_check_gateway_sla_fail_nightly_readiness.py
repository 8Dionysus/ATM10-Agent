from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import scripts.check_gateway_sla_fail_nightly_readiness as readiness_checker


def _write_trend_snapshot(
    path: Path,
    *,
    checked_at_utc: str,
    status: str = "ok",
    metrics_max_severity: str = "none",
    breach_rate_severity: str = "none",
    baseline_count: int = 5,
    sla_status: str = "pass",
) -> None:
    payload: dict[str, Any] = {
        "schema_version": "gateway_sla_trend_snapshot_v1",
        "status": status,
        "checked_at_utc": checked_at_utc,
        "latest": {
            "checked_at_utc": checked_at_utc,
            "sla_status": sla_status,
            "run_name": path.parent.name,
        },
        "rolling_baseline": {
            "count": baseline_count,
            "regression_flags": {
                "max_regression_severity": metrics_max_severity,
            },
        },
        "breach_drift": {
            "breach_rate_severity": breach_rate_severity,
        },
        "paths": {
            "trend_snapshot_json": str(path),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _seed_history(
    root: Path,
    *,
    count: int,
    start: datetime,
    severity_schedule: list[str] | None = None,
    breach_schedule: list[str] | None = None,
    baseline_count: int = 5,
) -> None:
    for index in range(count):
        checked_at = start + timedelta(minutes=index)
        metrics_severity = "none"
        if severity_schedule is not None and index < len(severity_schedule):
            metrics_severity = severity_schedule[index]
        breach_severity = "none"
        if breach_schedule is not None and index < len(breach_schedule):
            breach_severity = breach_schedule[index]
        _write_trend_snapshot(
            root / f"{checked_at.strftime('%Y%m%d_%H%M%S')}-gateway-sla-trend" / "gateway_sla_trend_snapshot.json",
            checked_at_utc=checked_at.astimezone(timezone.utc).isoformat(),
            metrics_max_severity=metrics_severity,
            breach_rate_severity=breach_severity,
            baseline_count=baseline_count,
            sla_status="breach" if _max_label(metrics_severity, breach_severity) != "none" else "pass",
        )


def _max_label(a: str, b: str) -> str:
    rank = {"none": 0, "warn": 1, "critical": 2}
    return a if rank.get(a, 0) >= rank.get(b, 0) else b


def test_readiness_happy_path_ready(tmp_path: Path) -> None:
    trend_root = tmp_path / "trend-history"
    start = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    severity = ["warn", "warn"] + ["none"] * 12
    _seed_history(trend_root, count=14, start=start, severity_schedule=severity, baseline_count=5)

    result = readiness_checker.run_gateway_sla_fail_nightly_readiness(
        trend_runs_dir=trend_root,
        history_limit=30,
        readiness_window=14,
        required_baseline_count=5,
        max_warn_ratio=0.20,
        policy="report_only",
        runs_dir=tmp_path / "readiness-runs",
        now=datetime(2026, 3, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["readiness_status"] == "ready"
    assert summary["window_summary"]["critical_count"] == 0
    assert summary["window_summary"]["warn_count"] == 2
    assert summary["window_summary"]["warn_ratio"] <= 0.20
    assert summary["recommendation"]["target_critical_policy"] == "fail_nightly"


def test_readiness_not_ready_when_insufficient_window(tmp_path: Path) -> None:
    trend_root = tmp_path / "trend-history"
    start = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    _seed_history(trend_root, count=7, start=start, baseline_count=5)

    result = readiness_checker.run_gateway_sla_fail_nightly_readiness(
        trend_runs_dir=trend_root,
        readiness_window=14,
        required_baseline_count=5,
        policy="report_only",
        runs_dir=tmp_path / "readiness-runs",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["readiness_status"] == "not_ready"
    assert "insufficient_window" in summary["recommendation"]["reason_codes"]


def test_readiness_not_ready_on_critical_severity(tmp_path: Path) -> None:
    trend_root = tmp_path / "trend-history"
    start = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    severity = ["none"] * 13 + ["critical"]
    _seed_history(trend_root, count=14, start=start, severity_schedule=severity, baseline_count=5)

    result = readiness_checker.run_gateway_sla_fail_nightly_readiness(
        trend_runs_dir=trend_root,
        readiness_window=14,
        required_baseline_count=5,
        policy="report_only",
        runs_dir=tmp_path / "readiness-runs",
    )
    summary = result["summary_payload"]
    assert summary["readiness_status"] == "not_ready"
    assert summary["window_summary"]["critical_count"] == 1
    assert "critical_regression_present" in summary["recommendation"]["reason_codes"]


def test_readiness_not_ready_when_warn_ratio_above_threshold(tmp_path: Path) -> None:
    trend_root = tmp_path / "trend-history"
    start = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    severity = ["warn"] * 4 + ["none"] * 10
    _seed_history(trend_root, count=14, start=start, severity_schedule=severity, baseline_count=5)

    result = readiness_checker.run_gateway_sla_fail_nightly_readiness(
        trend_runs_dir=trend_root,
        readiness_window=14,
        required_baseline_count=5,
        max_warn_ratio=0.20,
        policy="report_only",
        runs_dir=tmp_path / "readiness-runs",
    )
    summary = result["summary_payload"]
    assert summary["readiness_status"] == "not_ready"
    assert summary["window_summary"]["warn_ratio"] > 0.20
    assert "warn_ratio_above_threshold" in summary["recommendation"]["reason_codes"]


def test_readiness_counts_invalid_or_error_snapshots(tmp_path: Path) -> None:
    trend_root = tmp_path / "trend-history"
    start = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    _seed_history(trend_root, count=14, start=start, baseline_count=5)
    bad_path = trend_root / "20260301_003000-gateway-sla-trend" / "gateway_sla_trend_snapshot.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("{bad", encoding="utf-8")
    error_path = trend_root / "20260301_003100-gateway-sla-trend" / "gateway_sla_trend_snapshot.json"
    _write_trend_snapshot(
        error_path,
        checked_at_utc="2026-03-01T00:31:00+00:00",
        status="error",
    )

    result = readiness_checker.run_gateway_sla_fail_nightly_readiness(
        trend_runs_dir=trend_root,
        history_limit=30,
        readiness_window=14,
        required_baseline_count=5,
        policy="report_only",
        runs_dir=tmp_path / "readiness-runs",
    )
    summary = result["summary_payload"]
    assert summary["status"] == "ok"
    assert summary["readiness_status"] == "not_ready"
    assert summary["window_summary"]["invalid_or_error_count"] >= 2
    assert summary["warnings"]
    assert "invalid_or_error_snapshots_present" in summary["recommendation"]["reason_codes"]


def test_readiness_error_when_no_valid_snapshots(tmp_path: Path) -> None:
    trend_root = tmp_path / "trend-history"
    bad = trend_root / "20260301_010000-gateway-sla-trend" / "gateway_sla_trend_snapshot.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text(json.dumps({"schema_version": "gateway_sla_trend_snapshot_v1", "status": "error"}), encoding="utf-8")

    result = readiness_checker.run_gateway_sla_fail_nightly_readiness(
        trend_runs_dir=trend_root,
        policy="report_only",
        runs_dir=tmp_path / "readiness-runs",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 2
    assert summary["status"] == "error"
    assert summary["error"] is not None


def test_readiness_exit_policy_report_only_not_ready_returns_zero(tmp_path: Path) -> None:
    trend_root = tmp_path / "trend-history"
    _seed_history(
        trend_root,
        count=14,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        severity_schedule=["warn"] * 5 + ["none"] * 9,
        baseline_count=5,
    )
    result = readiness_checker.run_gateway_sla_fail_nightly_readiness(
        trend_runs_dir=trend_root,
        max_warn_ratio=0.20,
        policy="report_only",
        runs_dir=tmp_path / "readiness-runs",
    )
    assert result["summary_payload"]["readiness_status"] == "not_ready"
    assert result["exit_code"] == 0


def test_readiness_exit_policy_fail_if_not_ready_returns_two(tmp_path: Path) -> None:
    trend_root = tmp_path / "trend-history"
    _seed_history(
        trend_root,
        count=14,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        severity_schedule=["warn"] * 5 + ["none"] * 9,
        baseline_count=5,
    )
    result = readiness_checker.run_gateway_sla_fail_nightly_readiness(
        trend_runs_dir=trend_root,
        max_warn_ratio=0.20,
        policy="fail_if_not_ready",
        runs_dir=tmp_path / "readiness-runs",
    )
    assert result["summary_payload"]["readiness_status"] == "not_ready"
    assert result["exit_code"] == 2


def test_readiness_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_fail_nightly_readiness.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        readiness_checker.parse_args()
    assert exc.value.code == 0
