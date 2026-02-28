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
        "missing_sources",
        "errors",
        "paths",
        "exit_code",
    ):
        assert field in summary


def test_streamlit_operator_panel_smoke_cli_help_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["streamlit_operator_panel_smoke.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        smoke.parse_args()
    assert exc.value.code == 0
