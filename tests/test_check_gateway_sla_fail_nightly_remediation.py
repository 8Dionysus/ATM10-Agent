from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.check_gateway_sla_fail_nightly_remediation as remediation_checker


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _paths(runs_dir: Path) -> dict[str, Path]:
    return {
        "readiness": runs_dir / "nightly-gateway-sla-readiness" / "readiness_summary.json",
        "governance": runs_dir / "nightly-gateway-sla-governance" / "governance_summary.json",
        "progress": runs_dir / "nightly-gateway-sla-progress" / "progress_summary.json",
        "transition": runs_dir / "nightly-gateway-sla-transition" / "transition_summary.json",
        "manual_cadence": runs_dir / "nightly-gateway-sla-manual-cadence" / "cadence_brief.json",
    }


def _readiness_payload(
    *,
    readiness_status: str = "ready",
    reason_codes: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_readiness_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-08T09:00:00+00:00",
        "readiness_status": readiness_status,
        "recommendation": {
            "target_critical_policy": "fail_nightly" if readiness_status == "ready" else "signal_only",
            "reason_codes": [] if reason_codes is None else reason_codes,
        },
    }


def _governance_payload(
    *,
    decision_status: str = "go",
    latest_ready_streak: int = 3,
    reason_codes: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_governance_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-08T09:01:00+00:00",
        "decision_status": decision_status,
        "observed": {
            "latest_ready_streak": latest_ready_streak,
            "invalid_or_mismatched_count": 0,
        },
        "recommendation": {
            "target_critical_policy": "fail_nightly" if decision_status == "go" else "signal_only",
            "switch_surface": "nightly_only",
            "reason_codes": [] if reason_codes is None else reason_codes,
        },
    }


def _progress_payload(
    *,
    decision_status: str = "go",
    remaining_window: int = 0,
    remaining_streak: int = 0,
    latest_ready_streak: int = 3,
    reason_codes: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_progress_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-08T09:02:00+00:00",
        "decision_status": decision_status,
        "observed": {
            "readiness": {
                "remaining_for_window": remaining_window,
                "remaining_for_streak": remaining_streak,
                "latest_ready_streak": latest_ready_streak,
            },
            "governance": {
                "latest_decision_status": decision_status,
            },
        },
        "recommendation": {
            "target_critical_policy": "fail_nightly" if decision_status == "go" else "signal_only",
            "reason_codes": [] if reason_codes is None else reason_codes,
        },
    }


def _transition_payload(
    *,
    decision_status: str = "go",
    allow_switch: bool = True,
    reason_codes: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_transition_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-08T09:03:00+00:00",
        "decision_status": decision_status,
        "allow_switch": allow_switch,
        "recommendation": {
            "target_critical_policy": "fail_nightly" if decision_status == "go" else "signal_only",
            "switch_surface": "nightly_only",
            "reason_codes": [] if reason_codes is None else reason_codes,
        },
    }


def _manual_cadence_payload(
    *,
    attention_state: str = "ready_for_accounted_run",
    decision_status: str = "allow_accounted_dispatch",
    reason_codes: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "gateway_sla_manual_cadence_brief_v1",
        "status": "ok",
        "checked_at_utc": "2026-03-08T09:04:00+00:00",
        "attention_state": attention_state,
        "decision": {
            "accounted_dispatch_allowed": decision_status == "allow_accounted_dispatch",
            "decision_status": decision_status,
            "next_accounted_dispatch_at_utc": None,
            "reason_codes": [] if reason_codes is None else reason_codes,
        },
    }


def test_remediation_green_snapshot_has_no_candidate_items(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _paths(runs_dir)
    _write_json(p["readiness"], _readiness_payload())
    _write_json(p["governance"], _governance_payload())
    _write_json(p["progress"], _progress_payload())
    _write_json(p["transition"], _transition_payload())
    _write_json(p["manual_cadence"], _manual_cadence_payload())

    result = remediation_checker.run_gateway_sla_fail_nightly_remediation(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 8, 10, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]
    history_summary_path = Path(summary["paths"]["history_summary_json"])
    latest_summary_path = Path(summary["paths"]["summary_json"])

    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["reason_codes"] == []
    assert summary["candidate_items"] == []
    assert summary["observed"]["attention_state"] == "ready_for_accounted_run"
    assert history_summary_path.is_file()
    assert latest_summary_path.is_file()
    assert history_summary_path.parent == result["run_dir"]
    assert summary["sources"]["manual_cadence"]["status"] == "present"


def test_remediation_hold_snapshot_builds_window_streak_and_regression_backlog(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _paths(runs_dir)
    _write_json(
        p["readiness"],
        _readiness_payload(
            readiness_status="not_ready",
            reason_codes=["insufficient_window", "insufficient_baseline_count_in_window"],
        ),
    )
    _write_json(
        p["governance"],
        _governance_payload(
            decision_status="hold",
            latest_ready_streak=0,
            reason_codes=["latest_not_ready", "ready_streak_below_threshold"],
        ),
    )
    _write_json(
        p["progress"],
        _progress_payload(
            decision_status="hold",
            remaining_window=12,
            remaining_streak=3,
            latest_ready_streak=0,
            reason_codes=[
                "latest_readiness_not_ready",
                "insufficient_window_observed",
                "ready_streak_below_threshold",
                "latest_governance_hold",
            ],
        ),
    )
    _write_json(
        p["transition"],
        _transition_payload(
            decision_status="hold",
            allow_switch=False,
            reason_codes=[
                "latest_readiness_not_ready",
                "latest_governance_not_go",
                "latest_progress_not_go",
                "readiness_valid_count_below_window",
                "ready_streak_below_threshold",
            ],
        ),
    )

    result = remediation_checker.run_gateway_sla_fail_nightly_remediation(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 8, 10, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["observed"]["readiness_status"] == "not_ready"
    assert summary["observed"]["governance_decision_status"] == "hold"
    assert summary["observed"]["progress_decision_status"] == "hold"
    assert summary["observed"]["transition_allow_switch"] is False
    assert summary["observed"]["remaining_for_window"] == 12
    assert summary["observed"]["remaining_for_streak"] == 3
    assert [item["id"] for item in summary["candidate_items"]] == [
        "regression_investigation",
        "window_accumulation",
        "ready_streak_stabilization",
    ]
    assert "insufficient_window" in summary["reason_codes"]
    assert "latest_readiness_not_ready" in summary["reason_codes"]
    assert "ready_streak_below_threshold" in summary["reason_codes"]


def test_remediation_invalid_required_source_triggers_telemetry_integrity_and_fail_policy(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _paths(runs_dir)
    _write_json(p["readiness"], _readiness_payload())
    p["governance"].parent.mkdir(parents=True, exist_ok=True)
    p["governance"].write_text("{bad", encoding="utf-8")
    _write_json(p["progress"], _progress_payload())
    _write_json(p["transition"], _transition_payload())

    result = remediation_checker.run_gateway_sla_fail_nightly_remediation(
        runs_dir=runs_dir,
        policy="fail_if_remediation_required",
        now=datetime(2026, 3, 8, 10, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert summary["status"] == "ok"
    assert summary["sources"]["governance"]["status"] == "invalid"
    assert [item["id"] for item in summary["candidate_items"]] == ["telemetry_integrity"]
    assert any("governance: invalid JSON" in item for item in summary["warnings"])
    assert result["exit_code"] == 2


@pytest.mark.parametrize(
    ("attention_state", "decision_status", "reason_codes"),
    [
        ("wait_for_utc_reset", "block_accounted_dispatch", ["utc_day_quota_exhausted"]),
        ("run_recovery_only", "allow_recovery_rerun", []),
    ],
)
def test_remediation_manual_guardrail_uses_cadence_attention_state(
    tmp_path: Path,
    attention_state: str,
    decision_status: str,
    reason_codes: list[str],
) -> None:
    runs_dir = tmp_path / "runs"
    p = _paths(runs_dir)
    _write_json(p["readiness"], _readiness_payload())
    _write_json(p["governance"], _governance_payload())
    _write_json(p["progress"], _progress_payload())
    _write_json(p["transition"], _transition_payload())
    _write_json(
        p["manual_cadence"],
        _manual_cadence_payload(
            attention_state=attention_state,
            decision_status=decision_status,
            reason_codes=reason_codes,
        ),
    )

    result = remediation_checker.run_gateway_sla_fail_nightly_remediation(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 8, 10, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["observed"]["attention_state"] == attention_state
    assert [item["id"] for item in summary["candidate_items"]] == ["manual_guardrail"]
    assert summary["candidate_items"][0]["source_refs"] == ["manual_cadence"]


def test_remediation_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_fail_nightly_remediation.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        remediation_checker.parse_args()
    assert exc.value.code == 0
