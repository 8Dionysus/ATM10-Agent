from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.check_gateway_sla_manual_cadence_brief as cadence_checker


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _paths(runs_dir: Path) -> dict[str, Path]:
    return {
        "manual_runner": runs_dir / "nightly-gateway-sla-manual-runner" / "manual_nightly_summary.json",
        "manual_cycle": runs_dir / "nightly-gateway-sla-manual-cycle" / "manual_cycle_summary.json",
        "readiness": runs_dir / "nightly-gateway-sla-readiness" / "readiness_summary.json",
        "governance": runs_dir / "nightly-gateway-sla-governance" / "governance_summary.json",
        "progress": runs_dir / "nightly-gateway-sla-progress" / "progress_summary.json",
        "transition": runs_dir / "nightly-gateway-sla-transition" / "transition_summary.json",
    }


def _manual_runner_payload() -> dict:
    return {
        "schema_version": "gateway_sla_manual_nightly_runner_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-03T13:54:56+00:00",
    }


def _manual_cycle_payload(*, allowed: bool, decision_status: str, next_dispatch: str | None = None) -> dict:
    return {
        "schema_version": "gateway_sla_manual_cycle_summary_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-03T13:55:02+00:00",
        "decision": {
            "accounted_dispatch_allowed": allowed,
            "decision_status": decision_status,
            "next_accounted_dispatch_at_utc": next_dispatch,
            "reason_codes": [] if allowed else ["utc_day_quota_exhausted"],
        },
    }


def _readiness_payload() -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_readiness_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-03T13:54:56+00:00",
        "readiness_status": "not_ready",
    }


def _governance_payload() -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_governance_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-03T13:54:56+00:00",
        "decision_status": "hold",
    }


def _progress_payload(*, remaining_window: int = 12, remaining_streak: int = 3) -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_progress_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-03T13:54:56+00:00",
        "decision_status": "hold",
        "observed": {
            "readiness": {
                "remaining_for_window": remaining_window,
                "remaining_for_streak": remaining_streak,
            }
        },
    }


def _transition_payload() -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_transition_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-03T13:54:56+00:00",
        "decision_status": "hold",
        "allow_switch": False,
    }


def test_cadence_brief_happy_path(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _paths(runs_dir)
    _write_json(p["manual_runner"], _manual_runner_payload())
    _write_json(p["manual_cycle"], _manual_cycle_payload(allowed=True, decision_status="allow_accounted_dispatch"))
    _write_json(p["readiness"], _readiness_payload())
    _write_json(p["governance"], _governance_payload())
    _write_json(p["progress"], _progress_payload(remaining_window=12, remaining_streak=3))
    _write_json(p["transition"], _transition_payload())

    now = datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone.utc)
    result = cadence_checker.run_gateway_sla_manual_cadence_brief(
        runs_dir=runs_dir,
        policy="report_only",
        now=now,
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["schema_version"] == "gateway_sla_manual_cadence_brief_v1"
    assert summary["status"] == "ok"
    assert summary["attention_state"] == "ready_for_accounted_run"
    assert summary["observed"]["remaining_for_window"] == 12
    assert summary["observed"]["remaining_for_streak"] == 3
    assert summary["forecast"]["next_accounted_dispatch_at_utc"] == now.isoformat()
    assert summary["forecast"]["earliest_window_ready_at_utc"] == "2026-03-14T14:00:00+00:00"
    assert summary["forecast"]["earliest_streak_ready_at_utc"] == "2026-03-05T14:00:00+00:00"
    assert summary["forecast"]["earliest_go_candidate_at_utc"] == "2026-03-14T14:00:00+00:00"


def test_cadence_brief_blocked_path_waits_for_utc_reset(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _paths(runs_dir)
    _write_json(
        p["manual_cycle"],
        _manual_cycle_payload(
            allowed=False,
            decision_status="block_accounted_dispatch",
            next_dispatch="2026-03-04T00:00:00+00:00",
        ),
    )
    _write_json(p["progress"], _progress_payload(remaining_window=12, remaining_streak=3))

    result = cadence_checker.run_gateway_sla_manual_cadence_brief(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["attention_state"] == "wait_for_utc_reset"
    assert summary["decision"]["decision_status"] == "block_accounted_dispatch"
    assert summary["forecast"]["next_accounted_dispatch_at_utc"] == "2026-03-04T00:00:00+00:00"


def test_cadence_brief_recovery_attention_state(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _paths(runs_dir)
    _write_json(
        p["manual_cycle"],
        _manual_cycle_payload(
            allowed=False,
            decision_status="allow_recovery_rerun",
            next_dispatch="2026-03-04T00:00:00+00:00",
        ),
    )
    _write_json(p["progress"], _progress_payload(remaining_window=12, remaining_streak=3))

    result = cadence_checker.run_gateway_sla_manual_cadence_brief(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["attention_state"] == "run_recovery_only"
    assert summary["decision"]["decision_status"] == "allow_recovery_rerun"


def test_cadence_brief_missing_required_source_marks_source_repair(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _paths(runs_dir)
    _write_json(p["manual_cycle"], _manual_cycle_payload(allowed=True, decision_status="allow_accounted_dispatch"))

    result = cadence_checker.run_gateway_sla_manual_cadence_brief(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["attention_state"] == "source_repair_required"
    assert summary["sources"]["progress"]["status"] == "missing"
    assert any("progress: source file not found" in row for row in summary["warnings"])


def test_cadence_brief_fail_policy_returns_two_for_attention_states(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _paths(runs_dir)
    _write_json(
        p["manual_cycle"],
        _manual_cycle_payload(
            allowed=False,
            decision_status="block_accounted_dispatch",
            next_dispatch="2026-03-04T00:00:00+00:00",
        ),
    )
    _write_json(p["progress"], _progress_payload())

    result = cadence_checker.run_gateway_sla_manual_cadence_brief(
        runs_dir=runs_dir,
        policy="fail_if_attention_required",
        now=datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert summary["attention_state"] == "wait_for_utc_reset"
    assert result["exit_code"] == 2


def test_cadence_brief_report_only_keeps_zero_for_attention_states(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _paths(runs_dir)
    _write_json(
        p["manual_cycle"],
        _manual_cycle_payload(
            allowed=False,
            decision_status="allow_recovery_rerun",
            next_dispatch="2026-03-04T00:00:00+00:00",
        ),
    )
    _write_json(p["progress"], _progress_payload())

    result = cadence_checker.run_gateway_sla_manual_cadence_brief(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone.utc),
    )

    assert result["summary_payload"]["attention_state"] == "run_recovery_only"
    assert result["exit_code"] == 0


def test_cadence_brief_malformed_required_json_returns_error(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _paths(runs_dir)
    p["manual_cycle"].parent.mkdir(parents=True, exist_ok=True)
    p["manual_cycle"].write_text("{not_json", encoding="utf-8")
    _write_json(p["progress"], _progress_payload())

    result = cadence_checker.run_gateway_sla_manual_cadence_brief(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone.utc),
    )

    assert result["exit_code"] == 2
    assert result["summary_payload"]["status"] == "error"


def test_cadence_brief_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_manual_cadence_brief.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        cadence_checker.parse_args()
    assert exc.value.code == 0
