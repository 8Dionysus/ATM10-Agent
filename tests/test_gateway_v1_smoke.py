from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.gateway_v1_smoke as gateway_smoke


def test_gateway_v1_smoke_core_ok(tmp_path: Path) -> None:
    summary_path = tmp_path / "runs" / "ci-smoke-gateway-core" / "gateway_smoke_summary.json"
    result = gateway_smoke.run_gateway_v1_smoke(
        scenario="core",
        runs_dir=tmp_path / "runs" / "ci-smoke-gateway-core",
        summary_json=summary_path,
        now=datetime(2026, 2, 27, 11, 0, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is True
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["status"] == "ok"
    assert summary_payload["scenario"] == "core"
    assert summary_payload["started_at_utc"]
    assert summary_payload["finished_at_utc"]
    assert summary_payload["duration_ms"] >= 0
    assert summary_payload["request_count"] == 3
    assert summary_payload["failed_requests_count"] == 0
    assert summary_payload["latency_p50_ms"] is not None
    assert summary_payload["latency_p95_ms"] is not None
    assert summary_payload["latency_max_ms"] is not None
    assert summary_payload["error_buckets"]["none"] == 3
    assert all(item["latency_ms"] >= 0 for item in summary_payload["requests"])
    assert all(item["ok"] is True for item in summary_payload["requests"])
    assert all(item["status"] == "ok" for item in summary_payload["requests"])


def test_gateway_v1_smoke_automation_ok(tmp_path: Path) -> None:
    summary_path = tmp_path / "runs" / "ci-smoke-gateway-automation" / "gateway_smoke_summary.json"
    result = gateway_smoke.run_gateway_v1_smoke(
        scenario="automation",
        runs_dir=tmp_path / "runs" / "ci-smoke-gateway-automation",
        summary_json=summary_path,
        now=datetime(2026, 2, 27, 11, 1, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is True
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["status"] == "ok"
    assert summary_payload["scenario"] == "automation"
    assert summary_payload["started_at_utc"]
    assert summary_payload["finished_at_utc"]
    assert summary_payload["duration_ms"] >= 0
    assert summary_payload["request_count"] == 1
    assert summary_payload["failed_requests_count"] == 0
    assert summary_payload["latency_p50_ms"] is not None
    assert summary_payload["latency_p95_ms"] is not None
    assert summary_payload["latency_max_ms"] is not None
    assert summary_payload["error_buckets"]["none"] == 1
    assert summary_payload["requests"][0]["latency_ms"] >= 0
    assert summary_payload["requests"][0]["ok"] is True
    assert summary_payload["requests"][0]["operation"] == "automation_dry_run"


def test_gateway_v1_smoke_hybrid_ok(tmp_path: Path) -> None:
    summary_path = tmp_path / "runs" / "ci-smoke-gateway-hybrid" / "gateway_smoke_summary.json"
    result = gateway_smoke.run_gateway_v1_smoke(
        scenario="hybrid",
        runs_dir=tmp_path / "runs" / "ci-smoke-gateway-hybrid",
        summary_json=summary_path,
        now=datetime(2026, 2, 27, 11, 1, 30, tzinfo=timezone.utc),
    )
    assert result["ok"] is True
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["status"] == "ok"
    assert summary_payload["scenario"] == "hybrid"
    assert summary_payload["request_count"] == 1
    assert summary_payload["failed_requests_count"] == 0
    assert summary_payload["error_buckets"]["none"] == 1
    assert summary_payload["requests"][0]["operation"] == "hybrid_query"
    assert summary_payload["requests"][0]["ok"] is True


def test_gateway_v1_smoke_invalid_scenario_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        gateway_smoke.run_gateway_v1_smoke(
            scenario="unsupported",
            runs_dir=tmp_path / "runs",
            now=datetime(2026, 2, 27, 11, 2, 0, tzinfo=timezone.utc),
        )


def test_gateway_v1_smoke_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["gateway_v1_smoke.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        gateway_smoke.parse_args()
    assert exc.value.code == 0
