from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.streamlit_operator_panel as panel
import scripts.streamlit_operator_panel_smoke as smoke


class _FakeProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        if self.returncode is None:
            self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            self.returncode = 0
        return int(self.returncode)

    def kill(self) -> None:
        self.returncode = -9


class _FakeThread:
    def join(self, timeout: float | None = None) -> None:
        _ = timeout


def _write_canonical_sources(runs_dir: Path) -> None:
    for path in panel.canonical_summary_sources(runs_dir).values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": "ok", "paths": {"run_dir": str(path.parent)}}), encoding="utf-8")


def _write_required_canonical_sources(runs_dir: Path) -> None:
    for source_name, path in panel.canonical_summary_sources(runs_dir).items():
        if source_name in smoke.OPTIONAL_SUMMARY_SOURCE_KEYS:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": "ok", "paths": {"run_dir": str(path.parent)}}), encoding="utf-8")


def _write_optional_progress_sources(runs_dir: Path) -> None:
    sources = panel.canonical_fail_nightly_progress_sources(runs_dir)
    sources["readiness"].parent.mkdir(parents=True, exist_ok=True)
    sources["governance"].parent.mkdir(parents=True, exist_ok=True)
    sources["progress"].parent.mkdir(parents=True, exist_ok=True)
    sources["readiness"].write_text(
        json.dumps(
            {
                "schema_version": "gateway_sla_fail_nightly_readiness_v1",
                "readiness_status": "ready",
                "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            }
        ),
        encoding="utf-8",
    )
    sources["governance"].write_text(
        json.dumps(
            {
                "schema_version": "gateway_sla_fail_nightly_governance_v1",
                "decision_status": "go",
                "observed": {"latest_ready_streak": 3},
                "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            }
        ),
        encoding="utf-8",
    )
    sources["progress"].write_text(
        json.dumps(
            {
                "schema_version": "gateway_sla_fail_nightly_progress_v1",
                "decision_status": "go",
                "observed": {"readiness": {"remaining_for_window": 0, "remaining_for_streak": 0}},
                "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            }
        ),
        encoding="utf-8",
    )
    remediation_path = panel.canonical_fail_nightly_remediation_source(runs_dir)
    remediation_path.parent.mkdir(parents=True, exist_ok=True)
    remediation_path.write_text(
        json.dumps(
            {
                "schema_version": "gateway_sla_fail_nightly_remediation_v1",
                "status": "ok",
                "policy": "report_only",
                "checked_at_utc": "2026-03-12T08:00:00+00:00",
                "observed": {
                    "readiness_status": "ready",
                    "governance_decision_status": "go",
                    "progress_decision_status": "go",
                    "transition_allow_switch": True,
                    "remaining_for_window": 0,
                    "remaining_for_streak": 0,
                },
                "reason_codes": [],
                "candidate_items": [],
                "paths": {"summary_json": str(remediation_path)},
            }
        ),
        encoding="utf-8",
    )
    transition_path = panel.canonical_fail_nightly_transition_source(runs_dir)
    transition_path.parent.mkdir(parents=True, exist_ok=True)
    transition_path.write_text(
        json.dumps(
            {
                "schema_version": "gateway_sla_fail_nightly_transition_v1",
                "status": "ok",
                "decision_status": "allow",
                "allow_switch": True,
                "checked_at_utc": "2026-03-12T08:05:00+00:00",
                "policy": "report_only",
                "observed": {
                    "progress": {
                        "remaining_for_window": 0,
                        "remaining_for_streak": 0,
                    }
                },
                "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
                "paths": {"summary_json": str(transition_path)},
            }
        ),
        encoding="utf-8",
    )
    integrity_path = panel.canonical_fail_nightly_integrity_source(runs_dir)
    integrity_path.parent.mkdir(parents=True, exist_ok=True)
    integrity_path.write_text(
        json.dumps(
            {
                "schema_version": "gateway_sla_fail_nightly_integrity_v1",
                "status": "ok",
                "checked_at_utc": "2026-03-12T08:10:00+00:00",
                "observed": {
                    "telemetry_ok": True,
                    "dual_write_ok": True,
                    "anti_double_count_ok": True,
                    "utc_guardrail_status": "ok",
                    "invalid_counts": {
                        "governance": 0,
                        "progress_readiness": 0,
                        "progress_governance": 0,
                        "transition_aggregated": 0,
                    },
                    "utc_guardrail": {
                        "attention_state": "ready_for_accounted_run",
                        "decision_status": "allow_accounted_dispatch",
                        "accounted_dispatch_allowed": True,
                        "next_accounted_dispatch_at_utc": None,
                        "reason_codes": [],
                    },
                },
                "decision": {"integrity_status": "clean", "reason_codes": []},
                "paths": {"summary_json": str(integrity_path)},
            }
        ),
        encoding="utf-8",
    )


def _write_operating_cycle_source(runs_dir: Path) -> None:
    summary_path = panel.canonical_operating_cycle_source(runs_dir)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": "gateway_sla_operating_cycle_v1",
                "status": "ok",
                "checked_at_utc": "2026-03-12T22:10:02.928361+00:00",
                "policy": "report_only",
                "effective_policy": "signal_only",
                "promotion_state": "blocked",
                "enforcement_surface": "nightly_only",
                "blocking_reason_codes": ["remediation_backlog_pending"],
                "recommended_actions": [
                    {
                        "action_key": "gateway_sla_operating_cycle_smoke",
                        "reason": "Refresh the promoted-policy decision surface after the next nightly evidence update.",
                    }
                ],
                "next_review_at_utc": "2026-03-22T21:53:16.661488+00:00",
                "profile_scope": "baseline_first",
                "actionable_message": "Resolve the remediation backlog before promoting nightly policy.",
                "cycle": {
                    "source": "manual",
                    "operating_mode": "reuse_fresh_latest",
                    "used_manual_fallback": False,
                    "manual_execution_mode": "accounted",
                    "manual_decision_status": "allow_accounted_dispatch",
                },
                "triage": {
                    "readiness_status": "not_ready",
                    "governance_decision_status": "hold",
                    "progress_decision_status": "hold",
                    "remaining_for_window": 11,
                    "remaining_for_streak": 3,
                    "transition_allow_switch": False,
                    "candidate_item_count": 3,
                    "integrity_status": "clean",
                    "attention_state": "ready_for_accounted_run",
                    "earliest_go_candidate_at_utc": "2026-03-22T21:53:16.661488+00:00",
                    "next_accounted_dispatch_at_utc": None,
                },
                "interpretation": {
                    "telemetry_repair_required": False,
                    "remediation_backlog_primary": True,
                    "blocked_manual_gate": False,
                    "next_action_hint": "continue_g2_backlog",
                },
                "paths": {
                    "summary_json": str(summary_path),
                },
            }
        ),
        encoding="utf-8",
    )


def _write_combo_a_operating_cycle_source(runs_dir: Path) -> None:
    summary_path = panel.canonical_combo_a_operating_cycle_source(runs_dir)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": "combo_a_operating_cycle_v1",
                "status": "ok",
                "checked_at_utc": "2026-03-22T18:10:00+00:00",
                "scenario": "combo_a_policy",
                "policy": "report_only",
                "effective_policy": "observe_only",
                "promotion_state": "hold",
                "enforcement_surface": "nightly_only",
                "blocking_reason_codes": ["cross_service_suite_combo_a_breach"],
                "recommended_actions": [
                    {
                        "action_key": "cross_service_suite_combo_a_smoke",
                        "reason": "Refresh the Combo A cross-service suite artifact before the next nightly review.",
                    }
                ],
                "next_review_at_utc": "2026-03-23T18:10:00+00:00",
                "profile_scope": "combo_a",
                "availability_status": "partial",
                "actionable_message": "Combo A promotion is held until the live cross-service suite is green again.",
                "live_readiness": {
                    "profile": "combo_a",
                    "available": False,
                    "availability_status": "partial",
                    "services": {},
                },
                "sources": {},
                "paths": {
                    "summary_json": str(summary_path),
                },
            }
        ),
        encoding="utf-8",
    )


def test_streamlit_operator_panel_smoke_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel_runs_dir = tmp_path / "panel-runs"
    _write_required_canonical_sources(panel_runs_dir)

    fake_process = _FakeProcess()

    def _fake_launch(command: list[str]):
        _ = command
        return fake_process, ["Local URL: http://127.0.0.1:8501"], _FakeThread()

    monkeypatch.setattr(smoke, "_launch_streamlit_process", _fake_launch)
    monkeypatch.setattr(smoke, "_wait_for_startup", lambda *args, **kwargs: (True, None))

    result = smoke.run_streamlit_operator_panel_smoke(
        panel_runs_dir=panel_runs_dir,
        runs_dir=tmp_path / "smoke-runs",
        summary_json=tmp_path / "smoke-runs" / "summary.json",
        now=datetime(2026, 2, 27, 22, 0, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is True
    assert result["exit_code"] == 0
    summary = result["summary_payload"]
    assert summary["schema_version"] == "streamlit_smoke_summary_v1"
    assert summary["status"] == "ok"
    assert summary["startup_ok"] is True
    assert summary["tabs_detected"] == list(panel.TAB_NAMES)
    assert summary["mobile_layout_contract_ok"] is True
    assert summary["viewport_baseline"] == {"width": 390, "height": 844, "orientation": "portrait"}
    assert summary["missing_sources"] == []
    assert summary["required_missing_sources"] == []
    assert len(summary["optional_missing_sources"]) == 11
    assert str(panel.canonical_summary_sources(panel_runs_dir)["gateway_combo_a"]) in summary["optional_missing_sources"]
    assert str(panel.canonical_summary_sources(panel_runs_dir)["gateway_http_combo_a"]) in summary["optional_missing_sources"]
    assert str(panel.canonical_summary_sources(panel_runs_dir)["cross_service_suite_combo_a"]) in summary["optional_missing_sources"]
    assert str(panel.canonical_summary_sources(panel_runs_dir)["combo_a_operating_cycle"]) in summary["optional_missing_sources"]
    assert str(panel.canonical_operating_cycle_source(panel_runs_dir)) in summary["optional_missing_sources"]
    assert str(panel.canonical_fail_nightly_remediation_source(panel_runs_dir)) in summary["optional_missing_sources"]
    assert str(panel.canonical_fail_nightly_transition_source(panel_runs_dir)) in summary["optional_missing_sources"]
    assert str(panel.canonical_fail_nightly_integrity_source(panel_runs_dir)) in summary["optional_missing_sources"]


def test_streamlit_operator_panel_smoke_happy_path_with_optional_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel_runs_dir = tmp_path / "panel-runs"
    _write_canonical_sources(panel_runs_dir)
    _write_optional_progress_sources(panel_runs_dir)
    _write_operating_cycle_source(panel_runs_dir)
    _write_combo_a_operating_cycle_source(panel_runs_dir)

    fake_process = _FakeProcess()
    monkeypatch.setattr(
        smoke,
        "_launch_streamlit_process",
        lambda command: (fake_process, ["Local URL: http://127.0.0.1:8501"], _FakeThread()),
    )
    monkeypatch.setattr(smoke, "_wait_for_startup", lambda *args, **kwargs: (True, None))

    result = smoke.run_streamlit_operator_panel_smoke(
        panel_runs_dir=panel_runs_dir,
        runs_dir=tmp_path / "smoke-runs",
        summary_json=tmp_path / "smoke-runs" / "summary.json",
        now=datetime(2026, 2, 27, 22, 0, 30, tzinfo=timezone.utc),
    )
    assert result["ok"] is True
    assert result["exit_code"] == 0
    summary = result["summary_payload"]
    assert summary["required_missing_sources"] == []
    assert summary["optional_missing_sources"] == []
    assert summary["missing_sources"] == []


def test_streamlit_operator_panel_smoke_timeout_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel_runs_dir = tmp_path / "panel-runs"
    _write_canonical_sources(panel_runs_dir)
    fake_process = _FakeProcess()

    monkeypatch.setattr(
        smoke,
        "_launch_streamlit_process",
        lambda command: (fake_process, [], _FakeThread()),
    )
    monkeypatch.setattr(
        smoke,
        "_wait_for_startup",
        lambda *args, **kwargs: (False, "streamlit startup timeout after 45.0s"),
    )

    result = smoke.run_streamlit_operator_panel_smoke(
        panel_runs_dir=panel_runs_dir,
        runs_dir=tmp_path / "smoke-runs",
        summary_json=tmp_path / "smoke-runs" / "summary.json",
        now=datetime(2026, 2, 27, 22, 1, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert result["summary_payload"]["status"] == "error"
    assert result["summary_payload"]["startup_ok"] is False


def test_streamlit_operator_panel_smoke_missing_streamlit_dependency_is_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel_runs_dir = tmp_path / "panel-runs"
    _write_canonical_sources(panel_runs_dir)

    monkeypatch.setattr(
        smoke,
        "_streamlit_dependency_error",
        lambda: (
            "runtime missing dependency: streamlit is not available in the active interpreter "
            "(python.exe). Repair with: python -m pip install -r requirements.txt."
        ),
    )

    def _unexpected_launch(_command: list[str]):
        raise AssertionError("_launch_streamlit_process must not be called when streamlit is missing")

    monkeypatch.setattr(smoke, "_launch_streamlit_process", _unexpected_launch)

    result = smoke.run_streamlit_operator_panel_smoke(
        panel_runs_dir=panel_runs_dir,
        runs_dir=tmp_path / "smoke-runs",
        summary_json=tmp_path / "smoke-runs" / "summary.json",
        now=datetime(2026, 2, 27, 22, 0, 45, tzinfo=timezone.utc),
    )
    assert result["ok"] is False
    assert result["exit_code"] == 2
    summary = result["summary_payload"]
    assert summary["status"] == "error"
    assert summary["startup_ok"] is False
    assert summary["required_missing_sources"] == []
    assert summary["optional_missing_sources"] == []
    assert summary["errors"]

    run_payload = result["run_payload"]
    assert run_payload["error_code"] == "runtime_missing_dependency"
    assert "Repair with: python -m pip install -r requirements.txt." in str(run_payload["error"])

    startup_log = Path(summary["paths"]["startup_log"]).read_text(encoding="utf-8")
    assert "runtime missing dependency" in startup_log
    assert "requirements.txt" in startup_log


def test_streamlit_operator_panel_smoke_early_crash_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel_runs_dir = tmp_path / "panel-runs"
    _write_canonical_sources(panel_runs_dir)
    fake_process = _FakeProcess()
    fake_process.returncode = 1

    monkeypatch.setattr(
        smoke,
        "_launch_streamlit_process",
        lambda command: (fake_process, ["process crashed"], _FakeThread()),
    )
    monkeypatch.setattr(
        smoke,
        "_wait_for_startup",
        lambda *args, **kwargs: (False, "streamlit process exited early with code 1"),
    )

    result = smoke.run_streamlit_operator_panel_smoke(
        panel_runs_dir=panel_runs_dir,
        runs_dir=tmp_path / "smoke-runs",
        summary_json=tmp_path / "smoke-runs" / "summary.json",
        now=datetime(2026, 2, 27, 22, 2, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert result["summary_payload"]["errors"]


def test_streamlit_operator_panel_smoke_missing_sources_is_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel_runs_dir = tmp_path / "panel-runs"
    fake_process = _FakeProcess()

    monkeypatch.setattr(
        smoke,
        "_launch_streamlit_process",
        lambda command: (fake_process, ["Local URL: http://127.0.0.1:8501"], _FakeThread()),
    )
    monkeypatch.setattr(smoke, "_wait_for_startup", lambda *args, **kwargs: (True, None))

    result = smoke.run_streamlit_operator_panel_smoke(
        panel_runs_dir=panel_runs_dir,
        runs_dir=tmp_path / "smoke-runs",
        summary_json=tmp_path / "smoke-runs" / "summary.json",
        now=datetime(2026, 2, 27, 22, 3, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is False
    assert result["exit_code"] == 2
    summary = result["summary_payload"]
    assert summary["status"] == "error"
    assert summary["missing_sources"]
    assert summary["required_missing_sources"] == summary["missing_sources"]


def test_streamlit_operator_panel_smoke_summary_has_required_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel_runs_dir = tmp_path / "panel-runs"
    _write_canonical_sources(panel_runs_dir)
    fake_process = _FakeProcess()
    monkeypatch.setattr(
        smoke,
        "_launch_streamlit_process",
        lambda command: (fake_process, ["Local URL: http://127.0.0.1:8501"], _FakeThread()),
    )
    monkeypatch.setattr(smoke, "_wait_for_startup", lambda *args, **kwargs: (True, None))
    result = smoke.run_streamlit_operator_panel_smoke(
        panel_runs_dir=panel_runs_dir,
        runs_dir=tmp_path / "smoke-runs",
        summary_json=tmp_path / "smoke-runs" / "summary.json",
        now=datetime(2026, 2, 27, 22, 4, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]
    for field in (
        "schema_version",
        "status",
        "startup_ok",
        "tabs_detected",
        "mobile_layout_contract_ok",
        "mobile_layout_policy",
        "viewport_baseline",
        "missing_sources",
        "required_missing_sources",
        "optional_missing_sources",
        "errors",
        "paths",
        "exit_code",
    ):
        assert field in summary


def test_streamlit_operator_panel_smoke_mobile_contract_violation_is_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel_runs_dir = tmp_path / "panel-runs"
    _write_canonical_sources(panel_runs_dir)
    fake_process = _FakeProcess()
    monkeypatch.setattr(
        smoke,
        "_launch_streamlit_process",
        lambda command: (fake_process, ["Local URL: http://127.0.0.1:8501"], _FakeThread()),
    )
    monkeypatch.setattr(smoke, "_wait_for_startup", lambda *args, **kwargs: (True, None))

    result = smoke.run_streamlit_operator_panel_smoke(
        panel_runs_dir=panel_runs_dir,
        runs_dir=tmp_path / "smoke-runs",
        summary_json=tmp_path / "smoke-runs" / "summary.json",
        viewport_width=900,
        viewport_height=500,
        compact_breakpoint_px=768,
        now=datetime(2026, 2, 27, 22, 5, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is False
    assert result["exit_code"] == 2
    summary = result["summary_payload"]
    assert summary["status"] == "error"
    assert summary["mobile_layout_contract_ok"] is False
    assert summary["errors"]


def test_streamlit_operator_panel_smoke_cli_help_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["streamlit_operator_panel_smoke.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        smoke.parse_args()
    assert exc.value.code == 0
