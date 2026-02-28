from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

import scripts.check_gateway_sla as checker


def _write_http_smoke_summary(
    path: Path,
    *,
    request_rows: list[Mapping[str, Any]],
    failed_requests_count: int,
) -> None:
    latencies = [float(row["latency_ms"]) for row in request_rows]
    payload = {
        "scenario": "core",
        "status": "ok",
        "ok": failed_requests_count == 0,
        "started_at_utc": "2026-02-27T12:00:00+00:00",
        "finished_at_utc": "2026-02-27T12:00:01+00:00",
        "duration_ms": 1000.0,
        "request_count": len(request_rows),
        "failed_requests_count": failed_requests_count,
        "latency_p50_ms": checker._percentile_nearest_rank(latencies, 50.0),
        "latency_p95_ms": checker._percentile_nearest_rank(latencies, 95.0),
        "latency_max_ms": max(latencies) if latencies else None,
        "error_buckets": {},
        "requests": request_rows,
        "paths": {"summary_json": str(path)},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def test_check_gateway_sla_happy_path_pass_conservative(tmp_path: Path) -> None:
    http_summary_path = tmp_path / "gateway_http_smoke_summary.json"
    summary_out_path = tmp_path / "gateway_sla_summary.json"
    rows = [
        {"latency_ms": 120.0, "error_code": None, "status": "ok", "ok": True},
        {"latency_ms": 180.0, "error_code": None, "status": "ok", "ok": True},
        {"latency_ms": 210.0, "error_code": None, "status": "ok", "ok": True},
    ]
    _write_http_smoke_summary(http_summary_path, request_rows=rows, failed_requests_count=0)

    result = checker.run_gateway_sla_check(
        http_summary_json=http_summary_path,
        summary_json=summary_out_path,
        profile="conservative",
        policy="signal_only",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["sla_status"] == "pass"
    assert summary["metrics"]["request_count"] == 3
    assert summary["metrics"]["failed_requests_count"] == 0
    assert summary["metrics"]["timeout_count"] == 0
    assert summary["error_buckets"]["none"] == 3


def test_check_gateway_sla_breach_signal_only_returns_zero(tmp_path: Path) -> None:
    http_summary_path = tmp_path / "gateway_http_smoke_summary.json"
    summary_out_path = tmp_path / "gateway_sla_summary.json"
    rows = [
        {"latency_ms": 1800.0, "error_code": None, "status": "ok", "ok": True},
        {"latency_ms": 2100.0, "error_code": "operation_failed", "status": "error", "ok": False},
    ]
    _write_http_smoke_summary(http_summary_path, request_rows=rows, failed_requests_count=1)

    result = checker.run_gateway_sla_check(
        http_summary_json=http_summary_path,
        summary_json=summary_out_path,
        profile="conservative",
        policy="signal_only",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["sla_status"] == "breach"
    assert summary["breaches"]


def test_check_gateway_sla_breach_fail_on_breach_returns_two(tmp_path: Path) -> None:
    http_summary_path = tmp_path / "gateway_http_smoke_summary.json"
    summary_out_path = tmp_path / "gateway_sla_summary.json"
    rows = [
        {"latency_ms": 1800.0, "error_code": None, "status": "ok", "ok": True},
        {"latency_ms": 2200.0, "error_code": "operation_failed", "status": "error", "ok": False},
    ]
    _write_http_smoke_summary(http_summary_path, request_rows=rows, failed_requests_count=1)

    result = checker.run_gateway_sla_check(
        http_summary_json=http_summary_path,
        summary_json=summary_out_path,
        profile="conservative",
        policy="fail_on_breach",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 2
    assert summary["status"] == "ok"
    assert summary["sla_status"] == "breach"


def test_check_gateway_sla_timeout_rate_breach(tmp_path: Path) -> None:
    http_summary_path = tmp_path / "gateway_http_smoke_summary.json"
    summary_out_path = tmp_path / "gateway_sla_summary.json"
    rows: list[dict[str, Any]] = []
    for _ in range(9):
        rows.append({"latency_ms": 100.0, "error_code": None, "status": "ok", "ok": True})
    rows.append(
        {
            "latency_ms": 120.0,
            "error_code": "operation_timeout",
            "status": "error",
            "ok": False,
        }
    )
    _write_http_smoke_summary(http_summary_path, request_rows=rows, failed_requests_count=1)

    result = checker.run_gateway_sla_check(
        http_summary_json=http_summary_path,
        summary_json=summary_out_path,
        profile="conservative",
        policy="signal_only",
    )
    summary = result["summary_payload"]
    assert summary["status"] == "ok"
    assert summary["sla_status"] == "breach"
    assert summary["metrics"]["timeout_count"] == 1
    assert summary["metrics"]["timeout_rate"] > 0.01
    assert any("timeout_rate" in item for item in summary["breaches"])


def test_check_gateway_sla_invalid_input_summary_sets_status_error(tmp_path: Path) -> None:
    http_summary_path = tmp_path / "gateway_http_smoke_summary.json"
    summary_out_path = tmp_path / "gateway_sla_summary.json"
    http_summary_path.write_text(json.dumps({"status": "ok"}), encoding="utf-8")

    result = checker.run_gateway_sla_check(
        http_summary_json=http_summary_path,
        summary_json=summary_out_path,
        profile="conservative",
        policy="signal_only",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 2
    assert summary["status"] == "error"
    assert summary["sla_status"] == "breach"
    assert summary["error"] is not None


def test_check_gateway_sla_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        checker.parse_args()
    assert exc.value.code == 0
