from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

import scripts.validate_ops_contracts as validator


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _seed_ci_smoke_sources(runs_dir: Path) -> None:
    smoke_payload = {"status": "ok", "observed": {"mode": "phase_a_smoke"}, "violations": []}
    _write_json(runs_dir / "ci-smoke-phase-a" / "smoke_summary.json", smoke_payload)
    _write_json(runs_dir / "ci-smoke-retrieve" / "smoke_summary.json", smoke_payload)
    _write_json(runs_dir / "ci-smoke-eval" / "smoke_summary.json", smoke_payload)

    gateway_payload = {
        "status": "ok",
        "request_count": 1,
        "failed_requests_count": 0,
        "requests": [{"status": "ok"}],
    }
    _write_json(runs_dir / "ci-smoke-gateway-core" / "gateway_smoke_summary.json", gateway_payload)
    _write_json(runs_dir / "ci-smoke-gateway-automation" / "gateway_smoke_summary.json", gateway_payload)
    _write_json(runs_dir / "ci-smoke-gateway-http-core" / "gateway_http_smoke_summary.json", gateway_payload)
    _write_json(
        runs_dir / "ci-smoke-gateway-http-automation" / "gateway_http_smoke_summary.json", gateway_payload
    )

    _write_json(
        runs_dir / "ci-smoke-gateway-sla" / "gateway_sla_summary.json",
        {
            "schema_version": "gateway_sla_summary_v1",
            "status": "ok",
            "sla_status": "pass",
            "metrics": {"request_count": 1},
            "exit_code": 0,
        },
    )
    _write_json(
        runs_dir / "ci-smoke-streamlit" / "streamlit_smoke_summary.json",
        {
            "schema_version": "streamlit_smoke_summary_v1",
            "status": "ok",
            "startup_ok": True,
            "tabs_detected": ["Stack Health"],
            "required_missing_sources": [],
            "optional_missing_sources": [],
            "exit_code": 0,
        },
    )


def test_validate_ops_contracts_happy_path_ci_smoke(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _seed_ci_smoke_sources(runs_dir)

    result = validator.run_validate_ops_contracts(
        profile="ci_smoke",
        runs_dir=runs_dir,
        policy="report_only",
        summary_json=tmp_path / "validation_summary.json",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["schema_version"] == "validation_summary_v1"
    assert summary["status"] == "ok"
    assert summary["totals"]["error_count"] == 0
    assert summary["totals"]["checked_count"] == 9


def test_validate_ops_contracts_missing_file_is_error(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _seed_ci_smoke_sources(runs_dir)
    (runs_dir / "ci-smoke-phase-a" / "smoke_summary.json").unlink()

    result = validator.run_validate_ops_contracts(
        profile="ci_smoke",
        runs_dir=runs_dir,
        policy="report_only",
        summary_json=tmp_path / "validation_summary.json",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "error"
    assert summary["totals"]["error_count"] >= 1
    assert any("phase_a: missing file" in err for err in summary["errors"])


def test_validate_ops_contracts_wrong_schema_is_error(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _seed_ci_smoke_sources(runs_dir)
    _write_json(
        runs_dir / "ci-smoke-gateway-sla" / "gateway_sla_summary.json",
        {
            "schema_version": "gateway_sla_summary_v0",
            "status": "ok",
            "sla_status": "pass",
            "metrics": {"request_count": 1},
            "exit_code": 0,
        },
    )

    result = validator.run_validate_ops_contracts(
        profile="ci_smoke",
        runs_dir=runs_dir,
        policy="report_only",
        summary_json=tmp_path / "validation_summary.json",
    )
    summary = result["summary_payload"]
    assert summary["status"] == "error"
    assert any("schema_version mismatch" in err for err in summary["errors"])


def test_validate_ops_contracts_broken_json_is_error(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _seed_ci_smoke_sources(runs_dir)
    broken = runs_dir / "ci-smoke-streamlit" / "streamlit_smoke_summary.json"
    broken.write_text("{bad", encoding="utf-8")

    result = validator.run_validate_ops_contracts(
        profile="ci_smoke",
        runs_dir=runs_dir,
        policy="report_only",
        summary_json=tmp_path / "validation_summary.json",
    )
    summary = result["summary_payload"]
    assert summary["status"] == "error"
    assert any("json parse failed" in err for err in summary["errors"])


def test_validate_ops_contracts_fail_on_error_policy_returns_two(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _seed_ci_smoke_sources(runs_dir)
    (runs_dir / "ci-smoke-eval" / "smoke_summary.json").unlink()

    result = validator.run_validate_ops_contracts(
        profile="ci_smoke",
        runs_dir=runs_dir,
        policy="fail_on_error",
        summary_json=tmp_path / "validation_summary.json",
    )
    assert result["summary_payload"]["status"] == "error"
    assert result["exit_code"] == 2


def test_validate_ops_contracts_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["validate_ops_contracts.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        validator.parse_args()
    assert exc.value.code == 0
