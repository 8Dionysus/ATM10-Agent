from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import scripts.bootstrap_gateway_sla_nightly_history as bootstrap


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _summary_payload_for_script(script_name: str) -> dict[str, Any]:
    if script_name == "gateway_v1_http_smoke.py":
        return {
            "status": "ok",
            "request_count": 1,
            "failed_requests_count": 0,
            "requests": [{"status": "ok"}],
        }
    if script_name == "check_gateway_sla.py":
        return {
            "schema_version": "gateway_sla_summary_v1",
            "status": "ok",
            "sla_status": "pass",
            "metrics": {"request_count": 1},
            "exit_code": 0,
        }
    if script_name == "check_gateway_sla_fail_nightly_readiness.py":
        return {
            "schema_version": "gateway_sla_fail_nightly_readiness_v1",
            "status": "ok",
            "readiness_status": "ready",
            "criteria": {"window_observed": 14},
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            "exit_code": 0,
        }
    if script_name == "check_gateway_sla_fail_nightly_governance.py":
        return {
            "schema_version": "gateway_sla_fail_nightly_governance_v1",
            "status": "ok",
            "decision_status": "go",
            "observed": {"latest_ready_streak": 3},
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            "exit_code": 0,
        }
    if script_name == "check_gateway_sla_fail_nightly_progress.py":
        return {
            "schema_version": "gateway_sla_fail_nightly_progress_v1",
            "status": "ok",
            "decision_status": "go",
            "observed": {
                "readiness": {
                    "latest_ready_streak": 3,
                    "remaining_for_window": 0,
                    "remaining_for_streak": 0,
                }
            },
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            "exit_code": 0,
        }
    if script_name == "check_gateway_sla_fail_nightly_transition.py":
        return {
            "schema_version": "gateway_sla_fail_nightly_transition_v1",
            "status": "ok",
            "decision_status": "allow",
            "allow_switch": True,
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            "exit_code": 0,
        }
    return {"status": "ok"}


def _fake_runner_factory(
    *,
    fail_script_name: str | None = None,
    commands_out: list[list[str]] | None = None,
):
    def _runner(command: list[str], _cwd: Path) -> subprocess.CompletedProcess[str]:
        if commands_out is not None:
            commands_out.append(list(command))

        script_name = Path(command[1]).name if len(command) >= 2 else ""
        if "--summary-json" in command:
            idx = command.index("--summary-json")
            summary_path = Path(command[idx + 1])
            _write_json(summary_path, _summary_payload_for_script(script_name))

        if fail_script_name is not None and script_name == fail_script_name:
            return subprocess.CompletedProcess(command, returncode=2, stdout="", stderr="forced failure")
        return subprocess.CompletedProcess(command, returncode=0, stdout="ok", stderr="")

    return _runner


def test_bootstrap_happy_path_writes_contract_and_markdown(tmp_path: Path) -> None:
    commands: list[list[str]] = []
    result = bootstrap.run_bootstrap_gateway_sla_nightly_history(
        iterations=2,
        runs_dir=tmp_path / "runs",
        policy="report_only",
        strict_stop=False,
        now=datetime(2026, 3, 2, 0, 0, 0, tzinfo=timezone.utc),
        command_runner=_fake_runner_factory(commands_out=commands),
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["schema_version"] == "gateway_sla_bootstrap_summary_v1"
    assert summary["status"] == "ok"
    assert summary["iterations"] == 2
    assert len(summary["steps"]) == 14
    assert summary["steps"][0]["step"] == "gateway_v1_http_smoke_core"
    assert summary["steps"][0]["summary_paths"]["summary_json"]
    assert summary["steps"][2]["summary_paths"] == {}
    assert summary["decision"]["allow_switch"] is True
    assert Path(summary["paths"]["summary_json"]).is_file()
    assert Path(summary["paths"]["summary_md"]).is_file()
    assert len(commands) == 14


def test_bootstrap_strict_stop_returns_two_and_stops_early(tmp_path: Path) -> None:
    commands: list[list[str]] = []
    result = bootstrap.run_bootstrap_gateway_sla_nightly_history(
        iterations=3,
        runs_dir=tmp_path / "runs",
        policy="report_only",
        strict_stop=True,
        command_runner=_fake_runner_factory(
            fail_script_name="check_gateway_sla_fail_nightly_governance.py",
            commands_out=commands,
        ),
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 2
    assert summary["status"] == "error"
    assert summary["execution"]["stopped_early"] is True
    assert summary["execution"]["interrupted_step"] == "check_gateway_sla_fail_nightly_governance"
    assert len(summary["steps"]) < 21


def test_bootstrap_report_only_continues_on_failure_and_returns_zero(tmp_path: Path) -> None:
    result = bootstrap.run_bootstrap_gateway_sla_nightly_history(
        iterations=2,
        runs_dir=tmp_path / "runs",
        policy="report_only",
        strict_stop=False,
        command_runner=_fake_runner_factory(fail_script_name="check_gateway_sla.py"),
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "error"
    assert summary["execution"]["had_step_error"] is True
    assert summary["execution"]["stopped_early"] is False
    assert len(summary["steps"]) == 14


def test_bootstrap_fail_on_step_error_returns_two(tmp_path: Path) -> None:
    result = bootstrap.run_bootstrap_gateway_sla_nightly_history(
        iterations=1,
        runs_dir=tmp_path / "runs",
        policy="fail_on_step_error",
        strict_stop=False,
        command_runner=_fake_runner_factory(fail_script_name="check_gateway_sla.py"),
    )
    assert result["summary_payload"]["status"] == "error"
    assert result["exit_code"] == 2


def test_bootstrap_summary_contains_latest_and_decision_fields(tmp_path: Path) -> None:
    result = bootstrap.run_bootstrap_gateway_sla_nightly_history(
        iterations=1,
        runs_dir=tmp_path / "runs",
        policy="report_only",
        strict_stop=False,
        command_runner=_fake_runner_factory(),
    )
    summary = result["summary_payload"]
    for key in ("latest", "decision", "steps", "started_at_utc", "finished_at_utc"):
        assert key in summary
    for key in ("readiness", "governance", "progress", "transition"):
        assert key in summary["latest"]
    for key in ("allow_switch", "target_critical_policy", "reason_codes"):
        assert key in summary["decision"]


def test_bootstrap_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["bootstrap_gateway_sla_nightly_history.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        bootstrap.parse_args()
    assert exc.value.code == 0


def test_bootstrap_parse_args_custom_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bootstrap_gateway_sla_nightly_history.py",
            "--iterations",
            "5",
            "--runs-dir",
            "runs/custom-bootstrap",
            "--policy",
            "fail_on_step_error",
            "--strict-stop",
        ],
    )
    args = bootstrap.parse_args()
    assert args.iterations == 5
    assert args.runs_dir == Path("runs/custom-bootstrap")
    assert args.policy == "fail_on_step_error"
    assert args.strict_stop is True
