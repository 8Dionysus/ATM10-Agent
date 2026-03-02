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


def _write_optional_progress_sources(runs_dir: Path) -> None:
    sources = panel.canonical_fail_nightly_progress_sources(runs_dir)
    sources["readiness"].parent.mkdir(parents=True, exist_ok=True)
    sources["governance"].parent.mkdir(parents=True, exist_ok=True)
    sources["progress"].parent.mkdir(parents=True, exist_ok=True)
    sources["transition"].parent.mkdir(parents=True, exist_ok=True)
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
                "status": "ok",
                "decision_status": "go",
                "observed": {"readiness": {"remaining_for_window": 0, "remaining_for_streak": 0}},
                "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            }
        ),
        encoding="utf-8",
    )
    sources["transition"].write_text(
        json.dumps(
            {
                "schema_version": "gateway_sla_fail_nightly_transition_v1",
                "status": "ok",
                "decision_status": "allow",
                "allow_switch": True,
                "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            }
        ),
        encoding="utf-8",
    )


def test_streamlit_operator_panel_smoke_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel_runs_dir = tmp_path / "panel-runs"
    _write_canonical_sources(panel_runs_dir)

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
    assert len(summary["optional_missing_sources"]) == 4
    assert summary["ops_readiness_contract_ok"] is True


def test_streamlit_operator_panel_smoke_happy_path_with_optional_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel_runs_dir = tmp_path / "panel-runs"
    _write_canonical_sources(panel_runs_dir)
    _write_optional_progress_sources(panel_runs_dir)

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
    assert summary["ops_readiness_contract_ok"] is True


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
        "ops_readiness_contract_ok",
        "ops_readiness_missing_fields",
        "ops_readiness_warnings",
        "ops_readiness_snapshot",
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
