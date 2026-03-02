from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import scripts.gateway_sla_trend_snapshot as trend_snapshot


def _write_sla_summary(
    path: Path,
    *,
    checked_at_utc: str,
    status: str = "ok",
    sla_status: str = "pass",
    error_rate: float = 0.0,
    timeout_rate: float = 0.0,
    latency_p95_ms: float = 100.0,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": "gateway_sla_summary_v1",
        "status": status,
        "sla_status": sla_status,
        "profile": "conservative",
        "policy": "signal_only",
        "checked_at_utc": checked_at_utc,
        "metrics": {
            "request_count": 3,
            "failed_requests_count": 0,
            "error_rate": error_rate,
            "timeout_count": 0,
            "timeout_rate": timeout_rate,
            "latency_p50_ms": 80.0,
            "latency_p95_ms": latency_p95_ms,
            "latency_max_ms": latency_p95_ms + 10.0,
        },
        "thresholds": {
            "latency_p95_ms_max": 1500.0,
            "error_rate_max": 0.05,
            "timeout_rate_max": 0.01,
        },
        "error_buckets": {"none": 3},
        "breaches": [],
        "paths": {"summary_json": str(path)},
        "exit_code": 0,
        "error": None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_gateway_sla_trend_snapshot_happy_path(tmp_path: Path) -> None:
    runs = tmp_path / "sla-runs"
    _write_sla_summary(
        runs / "20260301_120000-gateway-sla-check" / "gateway_sla_summary.json",
        checked_at_utc="2026-03-01T12:00:00+00:00",
        sla_status="pass",
        error_rate=0.01,
        timeout_rate=0.0,
        latency_p95_ms=100.0,
    )
    _write_sla_summary(
        runs / "20260301_121000-gateway-sla-check" / "gateway_sla_summary.json",
        checked_at_utc="2026-03-01T12:10:00+00:00",
        sla_status="pass",
        error_rate=0.02,
        timeout_rate=0.0,
        latency_p95_ms=120.0,
    )
    _write_sla_summary(
        runs / "20260301_122000-gateway-sla-check" / "gateway_sla_summary.json",
        checked_at_utc="2026-03-01T12:20:00+00:00",
        sla_status="breach",
        error_rate=0.015,
        timeout_rate=0.005,
        latency_p95_ms=160.0,
    )
    result = trend_snapshot.run_gateway_sla_trend_snapshot(
        sla_runs_dir=runs,
        history_limit=10,
        baseline_window=5,
        runs_dir=tmp_path / "trend-runs",
        now=datetime(2026, 3, 1, 13, 0, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is True
    assert result["exit_code"] == 0
    snapshot = result["snapshot_payload"]
    assert snapshot["schema_version"] == "gateway_sla_trend_snapshot_v1"
    assert snapshot["status"] == "ok"
    assert snapshot["latest"]["sla_status"] == "breach"
    assert snapshot["rolling_baseline"]["count"] == 2
    assert snapshot["rolling_baseline"]["regression_flags"]["error_rate_status"] == "stable"
    assert snapshot["rolling_baseline"]["regression_flags"]["timeout_rate_status"] == "regressed"
    assert snapshot["rolling_baseline"]["regression_flags"]["latency_p95_status"] == "regressed"
    assert snapshot["breach_drift"]["breach_rate_status"] == "regressed"
    assert snapshot["critical_policy"]["has_critical_regression"] is True
    assert snapshot["critical_policy"]["should_fail_nightly"] is False


def test_gateway_sla_trend_snapshot_single_run_insufficient_history(tmp_path: Path) -> None:
    runs = tmp_path / "sla-runs"
    _write_sla_summary(
        runs / "20260301_120000-gateway-sla-check" / "gateway_sla_summary.json",
        checked_at_utc="2026-03-01T12:00:00+00:00",
        sla_status="pass",
        error_rate=0.01,
        timeout_rate=0.0,
        latency_p95_ms=100.0,
    )
    result = trend_snapshot.run_gateway_sla_trend_snapshot(
        sla_runs_dir=runs,
        history_limit=10,
        baseline_window=5,
        runs_dir=tmp_path / "trend-runs",
        now=datetime(2026, 3, 1, 13, 1, 0, tzinfo=timezone.utc),
    )
    snapshot = result["snapshot_payload"]
    assert snapshot["status"] == "ok"
    assert snapshot["rolling_baseline"]["count"] == 0
    assert snapshot["rolling_baseline"]["regression_flags"]["error_rate_status"] == "insufficient_history"
    assert snapshot["breach_drift"]["breach_rate_status"] == "insufficient_history"


def test_gateway_sla_trend_snapshot_fail_nightly_on_critical(tmp_path: Path) -> None:
    runs = tmp_path / "sla-runs"
    _write_sla_summary(
        runs / "20260301_120000-gateway-sla-check" / "gateway_sla_summary.json",
        checked_at_utc="2026-03-01T12:00:00+00:00",
        sla_status="pass",
        error_rate=0.0,
        timeout_rate=0.0,
        latency_p95_ms=100.0,
    )
    _write_sla_summary(
        runs / "20260301_121000-gateway-sla-check" / "gateway_sla_summary.json",
        checked_at_utc="2026-03-01T12:10:00+00:00",
        sla_status="breach",
        error_rate=0.5,
        timeout_rate=0.2,
        latency_p95_ms=1000.0,
    )
    result = trend_snapshot.run_gateway_sla_trend_snapshot(
        sla_runs_dir=runs,
        history_limit=10,
        baseline_window=5,
        critical_policy="fail_nightly",
        runs_dir=tmp_path / "trend-runs",
        now=datetime(2026, 3, 1, 13, 2, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is False
    assert result["exit_code"] == 2
    snapshot = result["snapshot_payload"]
    assert snapshot["status"] == "ok"
    assert snapshot["critical_policy"]["has_critical_regression"] is True
    assert snapshot["critical_policy"]["should_fail_nightly"] is True


def test_gateway_sla_trend_snapshot_skips_invalid_files_with_warning(tmp_path: Path) -> None:
    runs = tmp_path / "sla-runs"
    _write_sla_summary(
        runs / "20260301_120000-gateway-sla-check" / "gateway_sla_summary.json",
        checked_at_utc="2026-03-01T12:00:00+00:00",
        sla_status="pass",
    )
    bad = runs / "20260301_121000-gateway-sla-check" / "gateway_sla_summary.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{bad", encoding="utf-8")

    result = trend_snapshot.run_gateway_sla_trend_snapshot(
        sla_runs_dir=runs,
        history_limit=10,
        baseline_window=5,
        runs_dir=tmp_path / "trend-runs",
        now=datetime(2026, 3, 1, 13, 3, 0, tzinfo=timezone.utc),
    )
    snapshot = result["snapshot_payload"]
    assert snapshot["status"] == "ok"
    assert snapshot["warnings"]


def test_gateway_sla_trend_snapshot_returns_error_when_no_valid_summaries(tmp_path: Path) -> None:
    runs = tmp_path / "sla-runs"
    bad = runs / "20260301_121000-gateway-sla-check" / "gateway_sla_summary.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text(json.dumps({"schema_version": "gateway_sla_summary_v1", "status": "error"}), encoding="utf-8")

    result = trend_snapshot.run_gateway_sla_trend_snapshot(
        sla_runs_dir=runs,
        history_limit=10,
        baseline_window=5,
        runs_dir=tmp_path / "trend-runs",
        now=datetime(2026, 3, 1, 13, 4, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is False
    assert result["exit_code"] == 2
    snapshot = result["snapshot_payload"]
    assert snapshot["status"] == "error"
    assert snapshot["error"] is not None


def test_gateway_sla_trend_snapshot_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["gateway_sla_trend_snapshot.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        trend_snapshot.parse_args()
    assert exc.value.code == 0
