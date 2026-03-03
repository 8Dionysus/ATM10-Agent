from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import scripts.check_gateway_sla_fail_nightly_transition as transition_checker


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_readiness(path: Path, checked_at: datetime, readiness_status: str = "ready", window_observed: int = 14) -> None:
    _write_json(
        path,
        {
            "schema_version": "gateway_sla_fail_nightly_readiness_v1",
            "status": "ok",
            "readiness_status": readiness_status,
            "checked_at_utc": checked_at.astimezone(timezone.utc).isoformat(),
            "criteria": {
                "readiness_window": 14,
                "required_baseline_count": 5,
                "max_warn_ratio": 0.20,
                "window_observed": window_observed,
            },
            "window_summary": {"critical_count": 0, "warn_count": 0, "none_count": 14},
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            "exit_code": 0,
        },
    )


def _write_governance(path: Path, checked_at: datetime, decision_status: str = "go", latest_ready_streak: int = 3) -> None:
    _write_json(
        path,
        {
            "schema_version": "gateway_sla_fail_nightly_governance_v1",
            "status": "ok",
            "decision_status": decision_status,
            "checked_at_utc": checked_at.astimezone(timezone.utc).isoformat(),
            "criteria": {
                "required_ready_streak": 3,
                "expected_readiness_window": 14,
                "expected_required_baseline_count": 5,
                "expected_max_warn_ratio": 0.20,
            },
            "observed": {"latest_ready_streak": latest_ready_streak},
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            "exit_code": 0,
        },
    )


def _write_progress(
    path: Path,
    checked_at: datetime,
    decision_status: str = "go",
    latest_ready_streak: int = 3,
    remaining_for_window: int = 0,
    remaining_for_streak: int = 0,
) -> None:
    _write_json(
        path,
        {
            "schema_version": "gateway_sla_fail_nightly_progress_v1",
            "status": "ok",
            "decision_status": decision_status,
            "checked_at_utc": checked_at.astimezone(timezone.utc).isoformat(),
            "criteria": {
                "required_ready_streak": 3,
                "expected_readiness_window": 14,
                "expected_required_baseline_count": 5,
                "expected_max_warn_ratio": 0.20,
            },
            "observed": {
                "readiness": {
                    "latest_ready_streak": latest_ready_streak,
                    "remaining_for_window": remaining_for_window,
                    "remaining_for_streak": remaining_for_streak,
                }
            },
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            "exit_code": 0,
        },
    )


def _seed_history(root: Path, start: datetime, count: int) -> None:
    for idx in range(count):
        ts = start + timedelta(days=idx)
        run_key = ts.strftime("%Y%m%d_%H%M%S")
        _write_readiness(
            root / "readiness" / f"{run_key}-gateway-sla-fail-readiness" / "readiness_summary.json",
            checked_at=ts,
            readiness_status="ready",
            window_observed=14,
        )
    latest = start + timedelta(days=count)
    _write_governance(
        root / "governance" / f"{latest.strftime('%Y%m%d_%H%M%S')}-gateway-sla-governance" / "governance_summary.json",
        checked_at=latest,
        decision_status="go",
        latest_ready_streak=3,
    )
    _write_progress(
        root / "progress" / f"{latest.strftime('%Y%m%d_%H%M%S')}-gateway-sla-progress" / "progress_summary.json",
        checked_at=latest,
        decision_status="go",
        latest_ready_streak=3,
        remaining_for_window=0,
        remaining_for_streak=0,
    )


def test_transition_happy_path_allow_switch(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    _seed_history(seed_root, datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc), 14)

    result = transition_checker.run_gateway_sla_fail_nightly_transition(
        readiness_runs_dir=seed_root / "readiness",
        governance_runs_dir=seed_root / "governance",
        progress_runs_dir=seed_root / "progress",
        policy="report_only",
        runs_dir=tmp_path / "transition-runs",
        now=datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["allow_switch"] is True
    assert summary["decision_status"] == "allow"
    assert summary["recommendation"]["target_critical_policy"] == "fail_nightly"
    assert summary["recommendation"]["reason_codes"] == []


def test_transition_writes_latest_and_history_summary_outputs(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    transition_root = tmp_path / "transition-runs"
    latest_summary_path = transition_root / "transition_summary.json"
    _seed_history(seed_root, datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc), 14)

    result = transition_checker.run_gateway_sla_fail_nightly_transition(
        readiness_runs_dir=seed_root / "readiness",
        governance_runs_dir=seed_root / "governance",
        progress_runs_dir=seed_root / "progress",
        policy="report_only",
        runs_dir=transition_root,
        summary_json=latest_summary_path,
    )
    summary = result["summary_payload"]
    history_summary_path = Path(summary["paths"]["history_summary_json"])

    assert Path(summary["paths"]["summary_json"]) == latest_summary_path
    assert latest_summary_path.is_file()
    assert history_summary_path.is_file()
    assert history_summary_path.parent == result["run_dir"]
    assert json.loads(history_summary_path.read_text(encoding="utf-8"))["schema_version"] == summary["schema_version"]


def test_transition_ignores_top_level_aliases_when_history_rows_exist(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    _seed_history(seed_root, datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc), 14)
    _write_readiness(
        seed_root / "readiness" / "readiness_summary.json",
        checked_at=datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc),
        readiness_status="not_ready",
        window_observed=14,
    )
    _write_governance(
        seed_root / "governance" / "governance_summary.json",
        checked_at=datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc),
        decision_status="hold",
        latest_ready_streak=0,
    )
    _write_progress(
        seed_root / "progress" / "progress_summary.json",
        checked_at=datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc),
        decision_status="hold",
        latest_ready_streak=0,
        remaining_for_window=10,
        remaining_for_streak=3,
    )

    result = transition_checker.run_gateway_sla_fail_nightly_transition(
        readiness_runs_dir=seed_root / "readiness",
        governance_runs_dir=seed_root / "governance",
        progress_runs_dir=seed_root / "progress",
        policy="report_only",
        runs_dir=tmp_path / "transition-runs",
    )
    summary = result["summary_payload"]

    assert summary["allow_switch"] is True
    assert summary["observed"]["readiness"]["valid_count"] == 14
    assert summary["observed"]["governance"]["valid_count"] == 1
    assert summary["observed"]["progress"]["valid_count"] == 1


def test_transition_uses_top_level_aliases_as_legacy_fallback(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    _write_readiness(
        seed_root / "readiness" / "readiness_summary.json",
        checked_at=datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc),
        readiness_status="ready",
        window_observed=14,
    )
    _write_governance(
        seed_root / "governance" / "governance_summary.json",
        checked_at=datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc),
        decision_status="go",
        latest_ready_streak=3,
    )
    _write_progress(
        seed_root / "progress" / "progress_summary.json",
        checked_at=datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc),
        decision_status="go",
        latest_ready_streak=3,
        remaining_for_window=0,
        remaining_for_streak=0,
    )

    result = transition_checker.run_gateway_sla_fail_nightly_transition(
        readiness_runs_dir=seed_root / "readiness",
        governance_runs_dir=seed_root / "governance",
        progress_runs_dir=seed_root / "progress",
        policy="report_only",
        runs_dir=tmp_path / "transition-runs",
    )
    summary = result["summary_payload"]

    assert summary["allow_switch"] is False
    assert summary["observed"]["readiness"]["valid_count"] == 1
    assert summary["observed"]["governance"]["valid_count"] == 1
    assert summary["observed"]["progress"]["valid_count"] == 1
    assert "readiness_valid_count_below_window" in summary["recommendation"]["reason_codes"]


def test_transition_hold_when_latest_not_ready(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    _seed_history(seed_root, datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc), 14)
    latest_readiness = sorted((seed_root / "readiness").glob("**/readiness_summary.json"))[-1]
    payload = json.loads(latest_readiness.read_text(encoding="utf-8"))
    payload["readiness_status"] = "not_ready"
    latest_readiness.write_text(json.dumps(payload), encoding="utf-8")

    result = transition_checker.run_gateway_sla_fail_nightly_transition(
        readiness_runs_dir=seed_root / "readiness",
        governance_runs_dir=seed_root / "governance",
        progress_runs_dir=seed_root / "progress",
        policy="report_only",
        runs_dir=tmp_path / "transition-runs",
    )
    summary = result["summary_payload"]
    assert summary["status"] == "ok"
    assert summary["allow_switch"] is False
    assert "latest_readiness_not_ready" in summary["recommendation"]["reason_codes"]


def test_transition_hold_when_readiness_count_below_window(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    _seed_history(seed_root, datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc), 5)

    result = transition_checker.run_gateway_sla_fail_nightly_transition(
        readiness_runs_dir=seed_root / "readiness",
        governance_runs_dir=seed_root / "governance",
        progress_runs_dir=seed_root / "progress",
        policy="report_only",
        runs_dir=tmp_path / "transition-runs",
    )
    summary = result["summary_payload"]
    assert summary["allow_switch"] is False
    assert "readiness_valid_count_below_window" in summary["recommendation"]["reason_codes"]


def test_transition_hold_when_criteria_mismatch_present(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    _seed_history(seed_root, datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc), 14)
    mismatch = sorted((seed_root / "progress").glob("**/progress_summary.json"))[-1]
    payload = json.loads(mismatch.read_text(encoding="utf-8"))
    payload["criteria"]["expected_readiness_window"] = 10
    mismatch.write_text(json.dumps(payload), encoding="utf-8")

    result = transition_checker.run_gateway_sla_fail_nightly_transition(
        readiness_runs_dir=seed_root / "readiness",
        governance_runs_dir=seed_root / "governance",
        progress_runs_dir=seed_root / "progress",
        policy="report_only",
        runs_dir=tmp_path / "transition-runs",
    )
    summary = result["summary_payload"]
    assert summary["allow_switch"] is False
    assert "invalid_or_mismatched_summaries_present" in summary["recommendation"]["reason_codes"]


def test_transition_exit_policy_fail_if_not_allowed_returns_two(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    _seed_history(seed_root, datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc), 2)

    result = transition_checker.run_gateway_sla_fail_nightly_transition(
        readiness_runs_dir=seed_root / "readiness",
        governance_runs_dir=seed_root / "governance",
        progress_runs_dir=seed_root / "progress",
        policy="fail_if_not_allowed",
        runs_dir=tmp_path / "transition-runs",
    )
    assert result["summary_payload"]["allow_switch"] is False
    assert result["exit_code"] == 2


def test_transition_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_fail_nightly_transition.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        transition_checker.parse_args()
    assert exc.value.code == 0
