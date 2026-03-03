from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import scripts.check_gateway_sla_fail_nightly_governance as governance_checker


def _write_readiness_summary(
    path: Path,
    *,
    checked_at_utc: str,
    status: str = "ok",
    readiness_status: str = "ready",
    readiness_window: int = 14,
    required_baseline_count: int = 5,
    max_warn_ratio: float = 0.20,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": "gateway_sla_fail_nightly_readiness_v1",
        "status": status,
        "readiness_status": readiness_status,
        "checked_at_utc": checked_at_utc,
        "criteria": {
            "readiness_window": readiness_window,
            "required_baseline_count": required_baseline_count,
            "max_warn_ratio": max_warn_ratio,
            "window_observed": readiness_window,
        },
        "window_summary": {
            "critical_count": 0,
            "warn_count": 0,
            "none_count": readiness_window,
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


def _seed_readiness_history(
    root: Path,
    *,
    start: datetime,
    statuses: list[str],
    readiness_window: int = 14,
    required_baseline_count: int = 5,
    max_warn_ratio: float = 0.20,
) -> None:
    for index, status in enumerate(statuses):
        checked_at = start + timedelta(days=index)
        _write_readiness_summary(
            root / f"{checked_at.strftime('%Y%m%d_%H%M%S')}-gateway-sla-fail-readiness" / "readiness_summary.json",
            checked_at_utc=checked_at.astimezone(timezone.utc).isoformat(),
            readiness_status=status,
            readiness_window=readiness_window,
            required_baseline_count=required_baseline_count,
            max_warn_ratio=max_warn_ratio,
        )


def test_governance_happy_path_go(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["not_ready", "ready", "ready", "ready"],
    )

    result = governance_checker.run_gateway_sla_fail_nightly_governance(
        readiness_runs_dir=readiness_root,
        history_limit=60,
        required_ready_streak=3,
        policy="report_only",
        runs_dir=tmp_path / "governance-runs",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["decision_status"] == "go"
    assert summary["observed"]["latest_ready_streak"] == 3
    assert summary["recommendation"]["target_critical_policy"] == "fail_nightly"


def test_governance_writes_latest_and_history_summary_outputs(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    governance_root = tmp_path / "governance-runs"
    latest_summary_path = governance_root / "governance_summary.json"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "ready", "ready"],
    )

    result = governance_checker.run_gateway_sla_fail_nightly_governance(
        readiness_runs_dir=readiness_root,
        required_ready_streak=3,
        runs_dir=governance_root,
        summary_json=latest_summary_path,
    )
    summary = result["summary_payload"]
    history_summary_path = Path(summary["paths"]["history_summary_json"])

    assert Path(summary["paths"]["summary_json"]) == latest_summary_path
    assert latest_summary_path.is_file()
    assert history_summary_path.is_file()
    assert history_summary_path.parent == result["run_dir"]
    assert json.loads(history_summary_path.read_text(encoding="utf-8"))["schema_version"] == summary["schema_version"]


def test_governance_ignores_top_level_latest_alias_when_history_rows_exist(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "ready"],
    )
    _write_readiness_summary(
        readiness_root / "readiness_summary.json",
        checked_at_utc="2026-03-20T00:00:00+00:00",
        readiness_status="not_ready",
    )

    result = governance_checker.run_gateway_sla_fail_nightly_governance(
        readiness_runs_dir=readiness_root,
        required_ready_streak=2,
        runs_dir=tmp_path / "governance-runs",
    )
    summary = result["summary_payload"]

    assert summary["decision_status"] == "go"
    assert summary["observed"]["valid_readiness_count"] == 2
    assert summary["observed"]["latest_readiness_status"] == "ready"


def test_governance_uses_top_level_latest_alias_as_legacy_fallback(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    _write_readiness_summary(
        readiness_root / "readiness_summary.json",
        checked_at_utc="2026-03-20T00:00:00+00:00",
        readiness_status="ready",
    )

    result = governance_checker.run_gateway_sla_fail_nightly_governance(
        readiness_runs_dir=readiness_root,
        required_ready_streak=1,
        runs_dir=tmp_path / "governance-runs",
    )
    summary = result["summary_payload"]

    assert summary["decision_status"] == "go"
    assert summary["observed"]["valid_readiness_count"] == 1
    assert summary["observed"]["latest_readiness_status"] == "ready"


def test_governance_hold_when_latest_not_ready(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "ready", "not_ready"],
    )

    result = governance_checker.run_gateway_sla_fail_nightly_governance(
        readiness_runs_dir=readiness_root,
        required_ready_streak=3,
        policy="report_only",
        runs_dir=tmp_path / "governance-runs",
    )
    summary = result["summary_payload"]
    assert summary["decision_status"] == "hold"
    assert summary["observed"]["latest_readiness_status"] == "not_ready"
    assert "latest_not_ready" in summary["recommendation"]["reason_codes"]


def test_governance_hold_when_ready_streak_below_threshold(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["not_ready", "ready", "ready"],
    )

    result = governance_checker.run_gateway_sla_fail_nightly_governance(
        readiness_runs_dir=readiness_root,
        required_ready_streak=3,
        policy="report_only",
        runs_dir=tmp_path / "governance-runs",
    )
    summary = result["summary_payload"]
    assert summary["decision_status"] == "hold"
    assert summary["observed"]["latest_readiness_status"] == "ready"
    assert summary["observed"]["latest_ready_streak"] == 2
    assert "ready_streak_below_threshold" in summary["recommendation"]["reason_codes"]


def test_governance_mismatch_criteria_counts_invalid_and_holds(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "ready", "ready"],
    )
    _write_readiness_summary(
        readiness_root / "20260310_000000-gateway-sla-fail-readiness" / "readiness_summary.json",
        checked_at_utc="2026-03-10T00:00:00+00:00",
        readiness_status="ready",
        readiness_window=10,
    )

    result = governance_checker.run_gateway_sla_fail_nightly_governance(
        readiness_runs_dir=readiness_root,
        expected_readiness_window=14,
        required_ready_streak=3,
        policy="report_only",
        runs_dir=tmp_path / "governance-runs",
    )
    summary = result["summary_payload"]
    assert summary["decision_status"] == "hold"
    assert summary["observed"]["invalid_or_mismatched_count"] >= 1
    assert "invalid_or_mismatched_readiness_present" in summary["recommendation"]["reason_codes"]


def test_governance_skips_invalid_files_with_warnings(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "ready", "ready"],
    )
    bad = readiness_root / "20260302_010000-gateway-sla-fail-readiness" / "readiness_summary.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{bad", encoding="utf-8")

    result = governance_checker.run_gateway_sla_fail_nightly_governance(
        readiness_runs_dir=readiness_root,
        required_ready_streak=3,
        policy="report_only",
        runs_dir=tmp_path / "governance-runs",
    )
    summary = result["summary_payload"]
    assert summary["status"] == "ok"
    assert summary["warnings"]
    assert summary["decision_status"] == "hold"


def test_governance_error_when_no_valid_readiness_summaries(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    path = readiness_root / "20260301_000000-gateway-sla-fail-readiness" / "readiness_summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "gateway_sla_fail_nightly_readiness_v1", "status": "error"}))

    result = governance_checker.run_gateway_sla_fail_nightly_governance(
        readiness_runs_dir=readiness_root,
        runs_dir=tmp_path / "governance-runs",
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 2
    assert summary["status"] == "error"
    assert summary["decision_status"] == "hold"
    assert summary["error"] is not None


def test_governance_exit_policy_report_only_hold_returns_zero(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "not_ready"],
    )
    result = governance_checker.run_gateway_sla_fail_nightly_governance(
        readiness_runs_dir=readiness_root,
        required_ready_streak=3,
        policy="report_only",
        runs_dir=tmp_path / "governance-runs",
    )
    assert result["summary_payload"]["decision_status"] == "hold"
    assert result["exit_code"] == 0


def test_governance_exit_policy_fail_if_not_go_returns_two(tmp_path: Path) -> None:
    readiness_root = tmp_path / "readiness-runs"
    _seed_readiness_history(
        readiness_root,
        start=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        statuses=["ready", "not_ready"],
    )
    result = governance_checker.run_gateway_sla_fail_nightly_governance(
        readiness_runs_dir=readiness_root,
        required_ready_streak=3,
        policy="fail_if_not_go",
        runs_dir=tmp_path / "governance-runs",
    )
    assert result["summary_payload"]["decision_status"] == "hold"
    assert result["exit_code"] == 2


def test_governance_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_fail_nightly_governance.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        governance_checker.parse_args()
    assert exc.value.code == 0
