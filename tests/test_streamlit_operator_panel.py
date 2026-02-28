from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import scripts.streamlit_operator_panel as panel


def test_canonical_summary_sources_returns_expected_paths(tmp_path: Path) -> None:
    sources = panel.canonical_summary_sources(tmp_path)
    assert list(sources.keys()) == [
        "phase_a",
        "retrieve",
        "eval",
        "gateway_core",
        "gateway_automation",
        "gateway_http_core",
        "gateway_http_automation",
    ]
    assert sources["phase_a"] == tmp_path / "ci-smoke-phase-a" / "smoke_summary.json"
    assert sources["gateway_http_automation"] == (
        tmp_path
        / "ci-smoke-gateway-http-automation"
        / "gateway_http_smoke_summary.json"
    )


def test_load_json_object_handles_missing_and_bad_json(tmp_path: Path) -> None:
    payload, error = panel.load_json_object(tmp_path / "missing.json")
    assert payload is None
    assert error is not None

    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{bad", encoding="utf-8")
    payload, error = panel.load_json_object(bad_path)
    assert payload is None
    assert error is not None


def test_fetch_gateway_health_failure_returns_error() -> None:
    payload, error = panel.fetch_gateway_health("http://127.0.0.1:1", timeout_sec=0.1)
    assert payload is None
    assert error is not None


def test_tab_names_exact() -> None:
    assert panel.TAB_NAMES == (
        "Stack Health",
        "Run Explorer",
        "Latest Metrics",
        "Safe Actions",
    )


def test_resolve_safe_action_rejects_unknown(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        panel.resolve_safe_action("not_allowed", tmp_path)


def test_resolve_safe_action_builds_expected_command(tmp_path: Path) -> None:
    command, summary_path = panel.resolve_safe_action("gateway_http_core", tmp_path)
    assert command[0].endswith("python") or command[0].endswith("python.exe")
    assert "scripts/gateway_v1_http_smoke.py" in command
    assert "--scenario" in command
    assert "core" in command
    assert str(summary_path).endswith("gateway_http_smoke_summary.json")


def test_run_safe_action_fails_when_summary_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed = subprocess.CompletedProcess(args=["python"], returncode=0, stdout="ok", stderr="")

    def _fake_run(*args, **kwargs):
        return completed

    monkeypatch.setattr(panel.subprocess, "run", _fake_run)
    result = panel.run_safe_action("gateway_local_core", tmp_path)
    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"] is not None
