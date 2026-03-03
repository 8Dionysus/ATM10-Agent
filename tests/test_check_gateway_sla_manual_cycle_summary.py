from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.check_gateway_sla_manual_cycle_summary as cycle_checker


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _preflight_payload(*, allowed: bool, decision_status: str) -> dict:
    return {
        "schema_version": "gateway_sla_manual_preflight_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-03T13:09:00+00:00",
        "observed": {
            "workflow_runs_observed": 5,
            "today_dispatch_count": 0 if allowed else 3,
            "latest_dispatch_run": {"run_id": 111},
        },
        "decision": {
            "accounted_dispatch_allowed": allowed,
            "decision_status": decision_status,
            "next_accounted_dispatch_at_utc": None if allowed else "2026-03-04T00:00:00+00:00",
            "reason_codes": [] if allowed else ["utc_day_quota_exhausted"],
        },
    }


def _readiness_payload() -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_readiness_v1",
        "status": "ok",
        "readiness_status": "not_ready",
    }


def _governance_payload() -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_governance_v1",
        "status": "ok",
        "decision_status": "hold",
    }


def _progress_payload() -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_progress_v1",
        "status": "ok",
        "decision_status": "hold",
        "observed": {
            "readiness": {
                "remaining_for_window": 13,
                "remaining_for_streak": 3,
            }
        },
    }


def _transition_payload() -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_transition_v1",
        "status": "ok",
        "decision_status": "hold",
        "allow_switch": False,
        "recommendation": {
            "reason_codes": [
                "latest_readiness_not_ready",
                "readiness_valid_count_below_window",
            ]
        },
    }


def _default_paths(runs_dir: Path) -> dict[str, Path]:
    return {
        "preflight": runs_dir / "nightly-gateway-sla-preflight" / "preflight_summary.json",
        "readiness": runs_dir / "nightly-gateway-sla-readiness" / "readiness_summary.json",
        "governance": runs_dir / "nightly-gateway-sla-governance" / "governance_summary.json",
        "progress": runs_dir / "nightly-gateway-sla-progress" / "progress_summary.json",
        "transition": runs_dir / "nightly-gateway-sla-transition" / "transition_summary.json",
    }


def test_manual_cycle_summary_happy_path(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    paths = _default_paths(runs_dir)
    _write_json(paths["preflight"], _preflight_payload(allowed=True, decision_status="allow_accounted_dispatch"))
    _write_json(paths["readiness"], _readiness_payload())
    _write_json(paths["governance"], _governance_payload())
    _write_json(paths["progress"], _progress_payload())
    _write_json(paths["transition"], _transition_payload())

    result = cycle_checker.run_gateway_sla_manual_cycle_summary(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 13, 20, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["schema_version"] == "gateway_sla_manual_cycle_summary_v1"
    assert summary["status"] == "ok"
    assert summary["decision"]["accounted_dispatch_allowed"] is True
    assert summary["decision"]["decision_status"] == "allow_accounted_dispatch"
    assert summary["sources"]["preflight"]["status"] == "present"
    assert summary["sources"]["transition"]["status"] == "present"
    assert summary["observed"]["readiness_status"] == "not_ready"
    assert summary["observed"]["governance_decision_status"] == "hold"
    assert summary["observed"]["progress"]["remaining_for_window"] == 13
    assert summary["observed"]["transition"]["allow_switch"] is False


def test_manual_cycle_summary_blocked_report_only_is_ok(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    paths = _default_paths(runs_dir)
    _write_json(paths["preflight"], _preflight_payload(allowed=False, decision_status="block_accounted_dispatch"))

    result = cycle_checker.run_gateway_sla_manual_cycle_summary(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 13, 21, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["decision"]["decision_status"] == "block_accounted_dispatch"
    assert summary["decision"]["accounted_dispatch_allowed"] is False


def test_manual_cycle_summary_blocked_fail_if_blocked_exits_two(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    paths = _default_paths(runs_dir)
    _write_json(paths["preflight"], _preflight_payload(allowed=False, decision_status="block_accounted_dispatch"))

    result = cycle_checker.run_gateway_sla_manual_cycle_summary(
        runs_dir=runs_dir,
        policy="fail_if_blocked",
        now=datetime(2026, 3, 3, 13, 22, 0, tzinfo=timezone.utc),
    )

    assert result["exit_code"] == 2
    assert result["summary_payload"]["decision"]["accounted_dispatch_allowed"] is False


def test_manual_cycle_summary_missing_optional_sources_warn_only(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    paths = _default_paths(runs_dir)
    _write_json(paths["preflight"], _preflight_payload(allowed=True, decision_status="allow_accounted_dispatch"))

    result = cycle_checker.run_gateway_sla_manual_cycle_summary(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 13, 23, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["sources"]["readiness"]["status"] == "missing"
    assert summary["sources"]["governance"]["status"] == "missing"
    assert summary["sources"]["progress"]["status"] == "missing"
    assert summary["sources"]["transition"]["status"] == "missing"
    assert len(summary["warnings"]) >= 4
    assert summary["decision"]["decision_status"] == "allow_accounted_dispatch"


def test_manual_cycle_summary_missing_preflight_returns_error(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"

    result = cycle_checker.run_gateway_sla_manual_cycle_summary(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 13, 24, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 2
    assert summary["status"] == "error"
    assert summary["decision"]["decision_status"] == "error"
    assert any("preflight" in item for item in summary["decision"]["reason_codes"])


def test_manual_cycle_summary_invalid_preflight_preserves_other_source_statuses(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    paths = _default_paths(runs_dir)
    _write_json(
        paths["preflight"],
        {
            "schema_version": "wrong_schema",
            "status": "ok",
        },
    )
    _write_json(paths["readiness"], _readiness_payload())

    result = cycle_checker.run_gateway_sla_manual_cycle_summary(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 13, 25, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 2
    assert summary["status"] == "error"
    assert summary["sources"]["preflight"]["status"] == "invalid"
    assert summary["sources"]["readiness"]["status"] == "present"
    assert summary["decision"]["reason_codes"] == ["preflight_summary_invalid"]


def test_manual_cycle_summary_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_manual_cycle_summary.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        cycle_checker.parse_args()
    assert exc.value.code == 0
