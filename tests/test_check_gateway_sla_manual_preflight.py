from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest

import scripts.check_gateway_sla_manual_preflight as preflight_checker


def _build_run_payload(
    *,
    run_id: int,
    created_at: str,
    event: str = "workflow_dispatch",
    head_branch: str = "master",
    status: str = "completed",
    conclusion: str = "success",
) -> dict[str, Any]:
    return {
        "id": run_id,
        "run_number": run_id,
        "html_url": f"https://github.com/org/repo/actions/runs/{run_id}",
        "created_at": created_at,
        "event": event,
        "head_branch": head_branch,
        "status": status,
        "conclusion": conclusion,
    }


def _api_getter_with(payload: Mapping[str, Any], capture: dict[str, Any]) -> preflight_checker.ApiGetter:
    def _getter(url: str, headers: Mapping[str, str]) -> Mapping[str, Any]:
        capture["url"] = url
        capture["headers"] = dict(headers)
        return payload

    return _getter


def test_preflight_allows_accounted_dispatch_when_no_today_runs(tmp_path: Path) -> None:
    now = datetime(2026, 3, 3, 10, 3, 14, tzinfo=timezone.utc)
    payload = {
        "workflow_runs": [
            _build_run_payload(run_id=111, created_at="2026-03-02T23:55:00Z"),
            _build_run_payload(run_id=112, created_at="2026-03-02T11:00:00Z"),
        ]
    }
    capture: dict[str, Any] = {}
    result = preflight_checker.run_gateway_sla_manual_preflight(
        repo="owner/repo",
        workflow="gateway-sla-readiness-nightly.yml",
        branch="master",
        event="workflow_dispatch",
        max_runs_per_utc_day=1,
        policy="report_only",
        runs_dir=tmp_path / "runs",
        now=now,
        env={"GITHUB_TOKEN": "token"},
        api_getter=_api_getter_with(payload, capture),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["decision"]["accounted_dispatch_allowed"] is True
    assert summary["observed"]["today_dispatch_count"] == 0
    assert summary["decision"]["reason_codes"] == []
    assert summary["decision"]["next_accounted_dispatch_at_utc"] is None
    assert summary["inputs"]["token_source"] == "env"
    assert "token_env" not in summary["inputs"]
    assert result["run_payload"]["params"]["token_source"] == "env"
    assert "token_env" not in result["run_payload"]["params"]
    assert "branch=master" in capture["url"]
    assert "event=workflow_dispatch" in capture["url"]


def test_preflight_blocks_when_today_quota_is_exhausted(tmp_path: Path) -> None:
    now = datetime(2026, 3, 3, 10, 3, 14, tzinfo=timezone.utc)
    payload = {
        "workflow_runs": [
            _build_run_payload(run_id=201, created_at="2026-03-03T00:48:55Z"),
        ]
    }

    result = preflight_checker.run_gateway_sla_manual_preflight(
        repo="owner/repo",
        max_runs_per_utc_day=1,
        policy="report_only",
        runs_dir=tmp_path / "runs",
        now=now,
        env={"GITHUB_TOKEN": "token"},
        api_getter=lambda _url, _headers: payload,
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["decision"]["accounted_dispatch_allowed"] is False
    assert summary["decision"]["decision_status"] == "block_accounted_dispatch"
    assert summary["decision"]["reason_codes"] == ["utc_day_quota_exhausted"]
    assert summary["decision"]["next_accounted_dispatch_at_utc"] == "2026-03-04T00:00:00+00:00"


def test_preflight_fail_if_blocked_returns_two(tmp_path: Path) -> None:
    now = datetime(2026, 3, 3, 10, 3, 14, tzinfo=timezone.utc)
    payload = {
        "workflow_runs": [
            _build_run_payload(run_id=301, created_at="2026-03-03T06:00:00Z"),
        ]
    }

    result = preflight_checker.run_gateway_sla_manual_preflight(
        repo="owner/repo",
        max_runs_per_utc_day=1,
        policy="fail_if_blocked",
        runs_dir=tmp_path / "runs",
        now=now,
        env={"GITHUB_TOKEN": "token"},
        api_getter=lambda _url, _headers: payload,
    )

    assert result["summary_payload"]["decision"]["accounted_dispatch_allowed"] is False
    assert result["exit_code"] == 2


def test_preflight_ignores_non_matching_branch_or_event_rows(tmp_path: Path) -> None:
    now = datetime(2026, 3, 3, 10, 3, 14, tzinfo=timezone.utc)
    payload = {
        "workflow_runs": [
            _build_run_payload(run_id=401, created_at="2026-03-03T02:00:00Z", event="push", head_branch="master"),
            _build_run_payload(
                run_id=402,
                created_at="2026-03-03T03:00:00Z",
                event="workflow_dispatch",
                head_branch="develop",
            ),
            _build_run_payload(
                run_id=403,
                created_at="2026-03-02T03:00:00Z",
                event="workflow_dispatch",
                head_branch="master",
            ),
        ]
    }

    result = preflight_checker.run_gateway_sla_manual_preflight(
        repo="owner/repo",
        branch="master",
        event="workflow_dispatch",
        max_runs_per_utc_day=1,
        policy="report_only",
        runs_dir=tmp_path / "runs",
        now=now,
        env={"GITHUB_TOKEN": "token"},
        api_getter=lambda _url, _headers: payload,
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["decision"]["accounted_dispatch_allowed"] is True
    assert summary["observed"]["today_dispatch_count"] == 0
    assert summary["observed"]["workflow_runs_observed"] == 1


def test_preflight_returns_error_when_token_is_missing(tmp_path: Path) -> None:
    now = datetime(2026, 3, 3, 10, 3, 14, tzinfo=timezone.utc)
    result = preflight_checker.run_gateway_sla_manual_preflight(
        repo="owner/repo",
        runs_dir=tmp_path / "runs",
        now=now,
        env={},
        api_getter=lambda _url, _headers: {"workflow_runs": []},
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 2
    assert summary["status"] == "error"
    assert "missing GitHub token" in str(summary["error"])
    assert "GITHUB_TOKEN" not in str(summary["error"])
    assert summary["inputs"]["token_source"] == "env"
    assert "token_env" not in summary["inputs"]


def test_preflight_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_manual_preflight.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        preflight_checker.parse_args()
    assert exc.value.code == 0
