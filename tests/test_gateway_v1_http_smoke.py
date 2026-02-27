from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import scripts.gateway_v1_http_smoke as gateway_http_smoke


def test_gateway_v1_http_smoke_core_ok(tmp_path: Path) -> None:
    summary_path = tmp_path / "runs" / "ci-smoke-gateway-http-core" / "gateway_http_smoke_summary.json"
    result = gateway_http_smoke.run_gateway_v1_http_smoke(
        scenario="core",
        runs_dir=tmp_path / "runs" / "ci-smoke-gateway-http-core",
        summary_json=summary_path,
        now=datetime(2026, 2, 27, 23, 0, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is True
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["status"] == "ok"
    assert summary_payload["scenario"] == "core"
    assert summary_payload["request_count"] == 3
    assert summary_payload["failed_requests_count"] == 0
    assert all(item["ok"] is True for item in summary_payload["requests"])
    assert all(item["http_status"] == item["expected_http_status"] for item in summary_payload["requests"])


def test_gateway_v1_http_smoke_automation_ok(tmp_path: Path) -> None:
    summary_path = (
        tmp_path / "runs" / "ci-smoke-gateway-http-automation" / "gateway_http_smoke_summary.json"
    )
    result = gateway_http_smoke.run_gateway_v1_http_smoke(
        scenario="automation",
        runs_dir=tmp_path / "runs" / "ci-smoke-gateway-http-automation",
        summary_json=summary_path,
        now=datetime(2026, 2, 27, 23, 1, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is True
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["status"] == "ok"
    assert summary_payload["scenario"] == "automation"
    assert summary_payload["request_count"] == 1
    assert summary_payload["failed_requests_count"] == 0
    assert summary_payload["requests"][0]["operation"] == "automation_dry_run"
    assert summary_payload["requests"][0]["http_status"] == summary_payload["requests"][0]["expected_http_status"]


def test_gateway_v1_http_smoke_invalid_scenario_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        gateway_http_smoke.run_gateway_v1_http_smoke(
            scenario="unsupported",
            runs_dir=tmp_path / "runs",
            now=datetime(2026, 2, 27, 23, 2, 0, tzinfo=timezone.utc),
        )


def test_gateway_v1_http_smoke_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["gateway_v1_http_smoke.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        gateway_http_smoke.parse_args()
    assert exc.value.code == 0
