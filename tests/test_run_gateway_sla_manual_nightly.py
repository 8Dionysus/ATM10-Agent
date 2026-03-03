from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import scripts.run_gateway_sla_manual_nightly as manual_runner


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _runner_history_run(
    *,
    runs_dir: Path,
    timestamp_utc: str,
    execution_mode: str,
    progression_credit: bool,
) -> None:
    ts = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    run_dir = (
        runs_dir
        / "nightly-gateway-sla-manual-runner"
        / f"{ts.strftime('%Y%m%d_%H%M%S')}-gateway-sla-manual-nightly-runner"
    )
    _write_json(
        run_dir / "run.json",
        {
            "timestamp_utc": ts.isoformat(),
            "mode": "gateway_sla_manual_nightly_runner",
            "status": "ok",
            "result": {
                "execution_mode": execution_mode,
                "progression_credit": progression_credit,
                "exit_code": 0,
            },
        },
    )


def _ok_result(*, status: str = "ok", exit_code: int = 0, paths: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "ok": status == "ok",
        "exit_code": exit_code,
        "run_payload": {"paths": paths or {}},
        "summary_payload": {"status": status, "exit_code": exit_code, "paths": paths or {}},
    }


def _transition_ok(*, allow_switch: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "exit_code": 0,
        "run_payload": {"paths": {}},
        "summary_payload": {
            "status": "ok",
            "exit_code": 0,
            "allow_switch": allow_switch,
            "paths": {},
        },
    }


def _install_success_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    calls: list[str],
    allow_switch: bool = False,
) -> None:
    monkeypatch.setattr(
        manual_runner,
        "run_gateway_v1_http_smoke",
        lambda **_kwargs: calls.append("gateway_http_core") or _ok_result(),
    )
    monkeypatch.setattr(
        manual_runner,
        "run_gateway_sla_check",
        lambda **_kwargs: calls.append("gateway_sla_signal") or _ok_result(),
    )
    monkeypatch.setattr(
        manual_runner,
        "run_gateway_sla_trend_snapshot",
        lambda **_kwargs: calls.append("trend") or {
            "ok": True,
            "exit_code": 0,
            "run_payload": {"paths": {}},
            "snapshot_payload": {"status": "ok", "exit_code": 0, "paths": {}},
        },
    )
    monkeypatch.setattr(
        manual_runner,
        "run_gateway_sla_fail_nightly_readiness",
        lambda **_kwargs: calls.append("readiness") or _ok_result(),
    )
    monkeypatch.setattr(
        manual_runner,
        "run_gateway_sla_fail_nightly_governance",
        lambda **_kwargs: calls.append("governance") or _ok_result(),
    )
    monkeypatch.setattr(
        manual_runner,
        "run_gateway_sla_fail_nightly_progress",
        lambda **_kwargs: calls.append("progress") or _ok_result(),
    )
    monkeypatch.setattr(
        manual_runner,
        "run_gateway_sla_fail_nightly_transition",
        lambda **_kwargs: calls.append("transition") or _transition_ok(allow_switch=allow_switch),
    )
    monkeypatch.setattr(
        manual_runner,
        "run_gateway_sla_manual_cycle_summary",
        lambda **_kwargs: calls.append("manual_cycle_summary") or _ok_result(),
    )


def test_manual_runner_accounted_path_runs_full_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs"
    calls: list[str] = []
    _install_success_stubs(monkeypatch, calls=calls, allow_switch=False)

    result = manual_runner.run_gateway_sla_manual_nightly(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["execution_mode"] == "accounted"
    assert summary["decision"]["decision_status"] == "allow_accounted_dispatch"
    assert calls == [
        "gateway_http_core",
        "gateway_sla_signal",
        "trend",
        "readiness",
        "governance",
        "progress",
        "transition",
        "manual_cycle_summary",
    ]


def test_manual_runner_blocked_report_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs"
    _runner_history_run(
        runs_dir=runs_dir,
        timestamp_utc="2026-03-03T10:00:00+00:00",
        execution_mode="accounted",
        progression_credit=True,
    )
    calls: list[str] = []
    _install_success_stubs(monkeypatch, calls=calls, allow_switch=False)

    result = manual_runner.run_gateway_sla_manual_nightly(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["execution_mode"] == "blocked"
    assert summary["decision"]["decision_status"] == "block_accounted_dispatch"
    assert calls == ["manual_cycle_summary"]


def test_manual_runner_blocked_fail_if_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs"
    _runner_history_run(
        runs_dir=runs_dir,
        timestamp_utc="2026-03-03T10:00:00+00:00",
        execution_mode="accounted",
        progression_credit=True,
    )
    calls: list[str] = []
    _install_success_stubs(monkeypatch, calls=calls, allow_switch=False)

    result = manual_runner.run_gateway_sla_manual_nightly(
        runs_dir=runs_dir,
        policy="fail_if_blocked",
        now=datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 2
    assert summary["execution_mode"] == "blocked"
    assert calls == ["manual_cycle_summary"]


def test_manual_runner_recovery_mode_runs_transition_and_cycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs"
    _runner_history_run(
        runs_dir=runs_dir,
        timestamp_utc="2026-03-03T10:00:00+00:00",
        execution_mode="accounted",
        progression_credit=True,
    )
    _write_json(
        runs_dir / "nightly-gateway-sla-readiness" / "readiness_summary.json",
        {"schema_version": "gateway_sla_fail_nightly_readiness_v1", "status": "ok"},
    )
    _write_json(
        runs_dir / "nightly-gateway-sla-governance" / "governance_summary.json",
        {"schema_version": "gateway_sla_fail_nightly_governance_v1", "status": "ok"},
    )
    _write_json(
        runs_dir / "nightly-gateway-sla-progress" / "progress_summary.json",
        {"schema_version": "gateway_sla_fail_nightly_progress_v1", "status": "ok"},
    )
    calls: list[str] = []
    _install_success_stubs(monkeypatch, calls=calls, allow_switch=False)

    result = manual_runner.run_gateway_sla_manual_nightly(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["execution_mode"] == "recovery"
    assert summary["decision"]["decision_status"] == "allow_recovery_rerun"
    assert calls == ["transition", "manual_cycle_summary"]


def test_manual_runner_fail_fast_stops_on_first_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs"
    calls: list[str] = []
    monkeypatch.setattr(
        manual_runner,
        "run_gateway_v1_http_smoke",
        lambda **_kwargs: calls.append("gateway_http_core") or _ok_result(status="error", exit_code=2),
    )
    monkeypatch.setattr(
        manual_runner,
        "run_gateway_sla_manual_cycle_summary",
        lambda **_kwargs: calls.append("manual_cycle_summary") or _ok_result(),
    )

    result = manual_runner.run_gateway_sla_manual_nightly(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 2
    assert summary["execution_mode"] == "error"
    assert calls == ["gateway_http_core"]


def test_manual_runner_counts_only_accounted_progression_credit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs"
    _runner_history_run(
        runs_dir=runs_dir,
        timestamp_utc="2026-03-03T08:00:00+00:00",
        execution_mode="recovery",
        progression_credit=False,
    )
    _runner_history_run(
        runs_dir=runs_dir,
        timestamp_utc="2026-03-03T09:00:00+00:00",
        execution_mode="blocked",
        progression_credit=False,
    )
    calls: list[str] = []
    _install_success_stubs(monkeypatch, calls=calls, allow_switch=False)

    result = manual_runner.run_gateway_sla_manual_nightly(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["execution_mode"] == "accounted"
    assert summary["decision"]["decision_status"] == "allow_accounted_dispatch"


def test_manual_runner_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_gateway_sla_manual_nightly.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        manual_runner.parse_args()
    assert exc.value.code == 0
