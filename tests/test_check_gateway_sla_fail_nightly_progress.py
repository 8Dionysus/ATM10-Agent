from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import scripts.check_gateway_sla_fail_nightly_progress as progress_checker


def _write_readiness_summary(
    path: Path,
    *,
    checked_at_utc: str,
    status: str = "ok",
    readiness_status: str = "ready",
    readiness_window: int = 14,
    required_baseline_count: int = 5,
    max_warn_ratio: float = 0.20,
    window_observed: int | None = None,
) -> None:
    observed = readiness_window if window_observed is None else window_observed
    payload: dict[str, Any] = {
        "schema_version": "gateway_sla_fail_nightly_readiness_v1",
        "status": status,
        "readiness_status": readiness_status,
        "checked_at_utc": checked_at_utc,
        "criteria": {
            "readiness_window": readiness_window,
            "required_baseline_count": required_baseline_count,
            "max_warn_ratio": max_warn_ratio,
            "window_observed": observed,
        },
        "window_summary": {
            "critical_count": 0,
            "warn_count": 0,
            "none_count": observed,
            "warn_ratio": 0.0,
            "insufficient_history_count": 0,
            "invalid_or_error_count": 0,
        },
        "recommendation": {
            "target_critical_policy": "fail_nightly" if readiness_status == "ready" else "signal_only",
            "reason_codes": [],
        },
        "policy": "report_only",
        "exit_code": 0,
        "warnings": [],
        "error": None,
        "paths": {"summary_json": str(path)},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_governance_summary(
    path: Path,
    *,
    checked_at_utc: str,
    status: str = "ok",
    decision_status: str = "hold",
    required_ready_streak: int = 3,
    expected_readiness_window: int = 14,
    expected_required_baseline_count: int = 5,
    expected_max_warn_ratio: float = 0.20,
    latest_ready_streak: int = 0,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": "gateway_sla_fail_nightly_governance_v1",
        "status": status,
        "decision_status": decision_status,
        "checked_at_utc": checked_at_utc,
        "policy": "report_only",
        "criteria": {
            "required_ready_streak": required_ready_streak,
            "expected_readiness_window": expected_readiness_window,
            "expected_required_baseline_count": expected_required_baseline_count,
            "expected_max_warn_ratio": expected_max_warn_ratio,
            "history_limit": 60,
        },
        "observed": {
            "window_observed": 4,
            "valid_readiness_count": 4,
            "invalid_or_mismatched_count": 0,
            "latest_readiness_status": "ready" if latest_ready_streak > 0 else "not_ready",
            "latest_ready_streak": latest_ready_streak,
            "ready_count_in_history": latest_ready_streak,
        },
        "latest": {
            "readiness_summary_json": "runs/nightly-gateway-sla-readiness/readiness_summary.json",
            "readiness_status": "ready" if latest_ready_streak > 0 else "not_ready",
        },
        "recommendation": {
            "target_critical_policy": "fail_nightly" if decision_status == "go" else "signal_only",
            "switch_surface": "nightly_only",
            "reason_codes": [] if decision_status == "go" else ["ready_streak_below_threshold"],
        },
        "exit_code": 0,
        "warnings": [],
        "error": None,
        "paths": {"summary_json": str(path)},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _seed_readiness_history(
    root: Path,
    *,
    start: datetime,
    statuses: list[str],
    window_observed: int = 14,
) -> None:
    for index, status in enumerate(statuses):
        checked_at = start + timedelta(days=index)
        _write_readiness_summary(
            root / f"{checked_at.strftime('%Y%m%d_%H%M%S')}-gateway-sla-fail-readiness" / "readiness_summary.json",
            checked_at_utc=checked_at.astimezone(timezone.utc).isoformat(),
            readiness_status=status,
            window_observed=window_observed,
        )


def _seed_governance_history(
    root: Path,
    *,
    start: datetime,
    decisions: list[str],
    latest_ready_streak: int = 0,
    required_ready_streak: int = 3,
) -> None:
    for index, decision in enumerate(decisions):
        checked_at = start + timedelta(days=index)
        _write_governance_summary(
            root / f"{checked_at.strftime('%Y%m%d_%H%M%S')}-gateway-sla-governance" / "governance_summary.json",
            checked_at_utc=checked_at.astimezone(timezone.utc).isoformat(),
            decision_status=decision,
            required_ready_streak=required_ready_streak,
            latest_ready_streak=latest_ready_streak if index == len(decisions) - 1 else 0,
        )


def test_progress_happy_path_go(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    governance_root = tmp_path / "governance-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["not_ready", "ready", "ready", "ready"],
        window_observed=14,
    )
    _seed_governance_history(
        governance_root,
        start=datetime(2026, 3, 1, 1, 0, 0, tzinfo=timezone.utc),
        decisions=["hold", "go"],
        latest_ready_streak=3,
    )

    result = progress_checker.run_gateway_sla_fail_nightly_progress(
        readiness_runs_dir=readiness_root,
        governance_runs_dir=governance_root,
        policy="report_only",
        runs_dir=tmp_path / "progress-runs",
        now=datetime(2026, 3, 2, 0, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["decision_status"] == "go"
    assert summary["observed"]["readiness"]["remaining_for_window"] == 0
    assert summary["observed"]["readiness"]["remaining_for_streak"] == 0
    assert summary["recommendation"]["target_critical_policy"] == "fail_nightly"
    assert summary["recommendation"]["reason_codes"] == []


def test_progress_writes_latest_and_history_summary_outputs(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    governance_root = tmp_path / "governance-runs"
    progress_root = tmp_path / "progress-runs"
    latest_summary_path = progress_root / "progress_summary.json"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "ready"],
        window_observed=14,
    )
    _seed_governance_history(
        governance_root,
        start=datetime(2026, 3, 1, 1, 0, 0, tzinfo=timezone.utc),
        decisions=["go"],
        latest_ready_streak=2,
        required_ready_streak=2,
    )

    result = progress_checker.run_gateway_sla_fail_nightly_progress(
        readiness_runs_dir=readiness_root,
        governance_runs_dir=governance_root,
        required_ready_streak=2,
        runs_dir=progress_root,
        summary_json=latest_summary_path,
    )
    summary = result["summary_payload"]
    history_summary_path = Path(summary["paths"]["history_summary_json"])

    assert Path(summary["paths"]["summary_json"]) == latest_summary_path
    assert latest_summary_path.is_file()
    assert history_summary_path.is_file()
    assert history_summary_path.parent == result["run_dir"]
    assert json.loads(history_summary_path.read_text(encoding="utf-8"))["schema_version"] == summary["schema_version"]


def test_progress_ignores_top_level_aliases_when_history_rows_exist(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    governance_root = tmp_path / "governance-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "ready"],
        window_observed=14,
    )
    _seed_governance_history(
        governance_root,
        start=datetime(2026, 3, 1, 1, 0, 0, tzinfo=timezone.utc),
        decisions=["go"],
        latest_ready_streak=2,
        required_ready_streak=2,
    )
    _write_readiness_summary(
        readiness_root / "readiness_summary.json",
        checked_at_utc="2026-03-20T00:00:00+00:00",
        readiness_status="not_ready",
        window_observed=14,
    )
    _write_governance_summary(
        governance_root / "governance_summary.json",
        checked_at_utc="2026-03-20T00:00:00+00:00",
        decision_status="hold",
        required_ready_streak=2,
        latest_ready_streak=0,
    )

    result = progress_checker.run_gateway_sla_fail_nightly_progress(
        readiness_runs_dir=readiness_root,
        governance_runs_dir=governance_root,
        required_ready_streak=2,
        runs_dir=tmp_path / "progress-runs",
    )
    summary = result["summary_payload"]

    assert summary["decision_status"] == "go"
    assert summary["observed"]["readiness"]["valid_count"] == 2
    assert summary["observed"]["governance"]["valid_count"] == 1
    assert summary["observed"]["readiness"]["latest_status"] == "ready"
    assert summary["observed"]["governance"]["latest_decision_status"] == "go"


def test_progress_uses_top_level_aliases_as_legacy_fallback(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    governance_root = tmp_path / "governance-runs"
    _write_readiness_summary(
        readiness_root / "readiness_summary.json",
        checked_at_utc="2026-03-20T00:00:00+00:00",
        readiness_status="ready",
        window_observed=14,
    )
    _write_governance_summary(
        governance_root / "governance_summary.json",
        checked_at_utc="2026-03-20T00:05:00+00:00",
        decision_status="go",
        required_ready_streak=1,
        latest_ready_streak=1,
    )

    result = progress_checker.run_gateway_sla_fail_nightly_progress(
        readiness_runs_dir=readiness_root,
        governance_runs_dir=governance_root,
        required_ready_streak=1,
        runs_dir=tmp_path / "progress-runs",
    )
    summary = result["summary_payload"]

    assert summary["decision_status"] == "go"
    assert summary["observed"]["readiness"]["valid_count"] == 1
    assert summary["observed"]["governance"]["valid_count"] == 1


def test_progress_hold_when_window_is_insufficient(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    governance_root = tmp_path / "governance-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "ready", "ready"],
        window_observed=10,
    )

    result = progress_checker.run_gateway_sla_fail_nightly_progress(
        readiness_runs_dir=readiness_root,
        governance_runs_dir=governance_root,
        policy="report_only",
        runs_dir=tmp_path / "progress-runs",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["decision_status"] == "hold"
    assert summary["observed"]["readiness"]["remaining_for_window"] == 4
    assert "insufficient_window_observed" in summary["recommendation"]["reason_codes"]
    assert "governance_history_missing" in summary["recommendation"]["reason_codes"]


def test_progress_hold_when_ready_streak_is_below_threshold(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    governance_root = tmp_path / "governance-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["not_ready", "ready", "ready"],
        window_observed=14,
    )
    _seed_governance_history(
        governance_root,
        start=datetime(2026, 3, 1, 1, 0, 0, tzinfo=timezone.utc),
        decisions=["hold"],
        latest_ready_streak=2,
    )

    result = progress_checker.run_gateway_sla_fail_nightly_progress(
        readiness_runs_dir=readiness_root,
        governance_runs_dir=governance_root,
        policy="report_only",
        runs_dir=tmp_path / "progress-runs",
    )
    summary = result["summary_payload"]
    assert summary["status"] == "ok"
    assert summary["decision_status"] == "hold"
    assert summary["observed"]["readiness"]["remaining_for_streak"] == 1
    assert "ready_streak_below_threshold" in summary["recommendation"]["reason_codes"]
    assert "latest_governance_hold" in summary["recommendation"]["reason_codes"]


def test_progress_counts_invalid_or_mismatched_histories(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    governance_root = tmp_path / "governance-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "ready", "ready"],
        window_observed=14,
    )
    _seed_governance_history(
        governance_root,
        start=datetime(2026, 3, 1, 1, 0, 0, tzinfo=timezone.utc),
        decisions=["go"],
        latest_ready_streak=3,
    )

    mismatch = readiness_root / "20260310_000000-gateway-sla-fail-readiness" / "readiness_summary.json"
    _write_readiness_summary(
        mismatch,
        checked_at_utc="2026-03-10T00:00:00+00:00",
        readiness_status="ready",
        readiness_window=10,
    )
    bad_governance = governance_root / "20260311_000000-gateway-sla-governance" / "governance_summary.json"
    bad_governance.parent.mkdir(parents=True, exist_ok=True)
    bad_governance.write_text("{bad", encoding="utf-8")

    result = progress_checker.run_gateway_sla_fail_nightly_progress(
        readiness_runs_dir=readiness_root,
        governance_runs_dir=governance_root,
        policy="report_only",
        runs_dir=tmp_path / "progress-runs",
    )
    summary = result["summary_payload"]
    assert summary["status"] == "ok"
    assert summary["decision_status"] == "hold"
    assert summary["observed"]["readiness"]["invalid_or_mismatched_count"] >= 1
    assert summary["observed"]["governance"]["invalid_or_mismatched_count"] >= 1
    assert "invalid_or_mismatched_readiness_present" in summary["recommendation"]["reason_codes"]
    assert "invalid_or_mismatched_governance_present" in summary["recommendation"]["reason_codes"]
    assert summary["warnings"]


def test_progress_returns_error_when_no_valid_readiness_history(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    governance_root = tmp_path / "governance-runs"
    broken = readiness_root / "20260301_000000-gateway-sla-fail-readiness" / "readiness_summary.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text(json.dumps({"schema_version": "gateway_sla_fail_nightly_readiness_v1", "status": "error"}))

    result = progress_checker.run_gateway_sla_fail_nightly_progress(
        readiness_runs_dir=readiness_root,
        governance_runs_dir=governance_root,
        policy="report_only",
        runs_dir=tmp_path / "progress-runs",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 2
    assert summary["status"] == "error"
    assert summary["decision_status"] == "hold"
    assert summary["error"] is not None


def test_progress_exit_policy_fail_if_not_go_returns_two(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    governance_root = tmp_path / "governance-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "ready"],
        window_observed=14,
    )
    _seed_governance_history(
        governance_root,
        start=datetime(2026, 3, 1, 1, 0, 0, tzinfo=timezone.utc),
        decisions=["hold"],
        latest_ready_streak=2,
    )

    result = progress_checker.run_gateway_sla_fail_nightly_progress(
        readiness_runs_dir=readiness_root,
        governance_runs_dir=governance_root,
        policy="fail_if_not_go",
        runs_dir=tmp_path / "progress-runs",
    )
    assert result["summary_payload"]["status"] == "ok"
    assert result["summary_payload"]["decision_status"] == "hold"
    assert result["exit_code"] == 2


def test_progress_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_fail_nightly_progress.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        progress_checker.parse_args()
    assert exc.value.code == 0
