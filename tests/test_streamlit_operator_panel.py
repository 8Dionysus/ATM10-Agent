from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import scripts.streamlit_operator_panel as panel


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _create_history_run(
    *,
    root: Path,
    run_name: str,
    mode: str,
    status: str = "ok",
    scenario: str | None = None,
    timestamp_utc: str | None = None,
) -> Path:
    run_dir = root / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    run_payload = {
        "mode": mode,
        "status": status,
        "timestamp_utc": timestamp_utc or f"2026-02-28T{run_name[-6:-4]}:{run_name[-4:-2]}:{run_name[-2:]}+00:00",
        "paths": {"run_json": str(run_dir / "run.json")},
    }
    if scenario is not None:
        run_payload["scenario"] = scenario
    _write_json(run_dir / "run.json", run_payload)
    return run_dir


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


def test_canonical_fail_nightly_progress_sources_returns_expected_paths(tmp_path: Path) -> None:
    sources = panel.canonical_fail_nightly_progress_sources(tmp_path)
    assert list(sources.keys()) == ["readiness", "governance", "progress"]
    assert sources["readiness"] == tmp_path / "nightly-gateway-sla-readiness" / "readiness_summary.json"
    assert sources["governance"] == tmp_path / "nightly-gateway-sla-governance" / "governance_summary.json"
    assert sources["progress"] == tmp_path / "nightly-gateway-sla-progress" / "progress_summary.json"


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


def test_mobile_layout_policy_defaults() -> None:
    policy = panel.mobile_layout_policy()
    assert policy["schema_version"] == panel.MOBILE_LAYOUT_POLICY_SCHEMA
    assert policy["compact_breakpoint_px"] == panel.MOBILE_LAYOUT_BREAKPOINT_PX_DEFAULT
    assert policy["mobile_baseline_viewport"] == panel.MOBILE_BASELINE_VIEWPORT


def test_build_compact_mobile_css_contains_breakpoint_and_selectors() -> None:
    css = panel.build_compact_mobile_css(breakpoint_px=640)
    assert "@media (max-width: 640px)" in css
    assert "[data-testid=\"stHorizontalBlock\"]" in css
    assert "[data-testid=\"column\"]" in css
    assert "[data-testid=\"stDataFrame\"]" in css


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
    assert isinstance(result["timestamp_utc"], str)


def test_safe_actions_audit_append_and_load_newest_first(tmp_path: Path) -> None:
    panel.append_safe_action_audit(
        tmp_path,
        {
            "timestamp_utc": "2026-02-28T10:00:00+00:00",
            "action_key": "gateway_local_core",
            "command": "python scripts/gateway_v1_smoke.py --scenario core",
            "exit_code": 0,
            "status": "ok",
            "summary_json": "runs/a.json",
            "summary_status": "ok",
            "error": None,
            "ok": True,
        },
    )
    panel.append_safe_action_audit(
        tmp_path,
        {
            "timestamp_utc": "2026-02-28T10:00:05+00:00",
            "action_key": "gateway_http_core",
            "command": "python scripts/gateway_v1_http_smoke.py --scenario core",
            "exit_code": 2,
            "status": "error",
            "summary_json": "runs/b.json",
            "summary_status": "error",
            "error": "summary status error",
            "ok": False,
        },
    )

    loaded = panel.load_safe_action_audit(tmp_path, limit=10)
    assert len(loaded) == 2
    assert loaded[0]["action_key"] == "gateway_http_core"
    assert loaded[1]["action_key"] == "gateway_local_core"
    assert loaded[0]["summary_json"] == "runs/b.json"


def test_safe_actions_audit_missing_file_returns_empty(tmp_path: Path) -> None:
    loaded = panel.load_safe_action_audit(tmp_path, limit=10)
    assert loaded == []


def test_safe_actions_audit_corrupted_line_is_tolerated(tmp_path: Path) -> None:
    audit_path = panel.safe_actions_audit_log_path(tmp_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    valid_entry = {
        "timestamp_utc": "2026-02-28T10:00:00+00:00",
        "action_key": "gateway_local_core",
        "command": "python scripts/gateway_v1_smoke.py --scenario core",
        "exit_code": 0,
        "status": "ok",
        "summary_json": "runs/c.json",
        "summary_status": "ok",
        "error": None,
        "ok": True,
    }
    audit_path.write_text(
        json.dumps(valid_entry, ensure_ascii=False)
        + "\n"
        + "{bad-json-line"
        + "\n",
        encoding="utf-8",
    )

    loaded = panel.load_safe_action_audit(tmp_path, limit=10)
    assert len(loaded) == 2
    assert loaded[0]["action_key"] == "invalid_audit_entry"
    assert "invalid audit entry" in str(loaded[0]["error"])
    assert loaded[1]["action_key"] == "gateway_local_core"


def test_build_metrics_history_rows_collects_valid_rows(tmp_path: Path) -> None:
    roots = panel.canonical_history_roots(tmp_path)
    run_1 = _create_history_run(
        root=roots["retrieve"],
        run_name="20260228_100000",
        mode="retrieve_demo",
        timestamp_utc="2026-02-28T10:00:00+00:00",
    )
    run_2 = _create_history_run(
        root=roots["retrieve"],
        run_name="20260228_100500",
        mode="retrieve_demo",
        timestamp_utc="2026-02-28T10:05:00+00:00",
    )
    _write_json(run_1 / "retrieval_results.json", {"count": 2, "results": [{}, {}]})
    _write_json(run_2 / "retrieval_results.json", {"count": 3, "results": [{}, {}, {}]})

    rows, warnings = panel.build_metrics_history_rows(
        tmp_path,
        selected_sources=["retrieve"],
        selected_statuses=["ok", "error"],
        limit_per_source=10,
    )
    assert warnings == []
    assert len(rows) == 2
    assert rows[0]["run_dir"] == str(run_2)
    assert rows[1]["run_dir"] == str(run_1)
    assert rows[0]["results_count"] == 3


def test_build_metrics_history_rows_applies_source_filter(tmp_path: Path) -> None:
    roots = panel.canonical_history_roots(tmp_path)
    phase_run = _create_history_run(
        root=roots["phase_a"],
        run_name="20260228_101000",
        mode="phase_a_smoke",
        timestamp_utc="2026-02-28T10:10:00+00:00",
    )
    _create_history_run(
        root=roots["retrieve"],
        run_name="20260228_101500",
        mode="retrieve_demo",
        timestamp_utc="2026-02-28T10:15:00+00:00",
    )
    _write_json((roots["retrieve"] / "20260228_101500" / "retrieval_results.json"), {"count": 1, "results": [{}]})

    rows, _warnings = panel.build_metrics_history_rows(
        tmp_path,
        selected_sources=["phase_a"],
        selected_statuses=["ok", "error"],
        limit_per_source=10,
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "phase_a"
    assert rows[0]["run_dir"] == str(phase_run)


def test_build_metrics_history_rows_applies_status_filter(tmp_path: Path) -> None:
    roots = panel.canonical_history_roots(tmp_path)
    error_run = _create_history_run(
        root=roots["retrieve"],
        run_name="20260228_102000",
        mode="retrieve_demo",
        status="error",
        timestamp_utc="2026-02-28T10:20:00+00:00",
    )
    _create_history_run(
        root=roots["retrieve"],
        run_name="20260228_102500",
        mode="retrieve_demo",
        status="ok",
        timestamp_utc="2026-02-28T10:25:00+00:00",
    )
    _write_json((roots["retrieve"] / "20260228_102000" / "retrieval_results.json"), {"count": 1, "results": [{}]})
    _write_json((roots["retrieve"] / "20260228_102500" / "retrieval_results.json"), {"count": 1, "results": [{}]})

    rows, _warnings = panel.build_metrics_history_rows(
        tmp_path,
        selected_sources=["retrieve"],
        selected_statuses=["error"],
        limit_per_source=10,
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "error"
    assert rows[0]["run_dir"] == str(error_run)


def test_build_metrics_history_rows_applies_limit_per_source(tmp_path: Path) -> None:
    roots = panel.canonical_history_roots(tmp_path)
    for idx in range(3):
        run_name = f"20260228_10300{idx}"
        run_dir = _create_history_run(
            root=roots["phase_a"],
            run_name=run_name,
            mode="phase_a_smoke",
            timestamp_utc=f"2026-02-28T10:30:0{idx}+00:00",
        )
        _ = run_dir

    rows, _warnings = panel.build_metrics_history_rows(
        tmp_path,
        selected_sources=["phase_a"],
        selected_statuses=["ok", "error"],
        limit_per_source=2,
    )
    assert len(rows) == 2
    assert rows[0]["timestamp_utc"] == "2026-02-28T10:30:02+00:00"
    assert rows[1]["timestamp_utc"] == "2026-02-28T10:30:01+00:00"


def test_build_metrics_history_rows_skips_invalid_runs_with_warnings(tmp_path: Path) -> None:
    roots = panel.canonical_history_roots(tmp_path)
    missing_side_file_run = _create_history_run(
        root=roots["retrieve"],
        run_name="20260228_104000",
        mode="retrieve_demo",
        timestamp_utc="2026-02-28T10:40:00+00:00",
    )
    bad_run_dir = roots["eval"] / "20260228_104500"
    bad_run_dir.mkdir(parents=True, exist_ok=True)
    (bad_run_dir / "run.json").write_text("{bad", encoding="utf-8")
    _ = missing_side_file_run

    rows, warnings = panel.build_metrics_history_rows(
        tmp_path,
        selected_sources=["retrieve", "eval"],
        selected_statuses=["ok", "error"],
        limit_per_source=10,
    )
    assert rows == []
    assert warnings
    assert any("missing or invalid retrieval_results.json" in item for item in warnings)
    assert any("invalid run.json" in item for item in warnings)


def test_load_fail_nightly_progress_snapshot_not_available_yet(tmp_path: Path) -> None:
    snapshot, warnings = panel.load_fail_nightly_progress_snapshot(tmp_path)
    assert snapshot is None
    assert warnings == []


def test_load_fail_nightly_progress_snapshot_happy_path(tmp_path: Path) -> None:
    sources = panel.canonical_fail_nightly_progress_sources(tmp_path)
    _write_json(
        sources["readiness"],
        {
            "schema_version": "gateway_sla_fail_nightly_readiness_v1",
            "readiness_status": "ready",
            "criteria": {"window_observed": 14},
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
        },
    )
    _write_json(
        sources["governance"],
        {
            "schema_version": "gateway_sla_fail_nightly_governance_v1",
            "decision_status": "go",
            "observed": {"latest_ready_streak": 3},
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
        },
    )
    _write_json(
        sources["progress"],
        {
            "schema_version": "gateway_sla_fail_nightly_progress_v1",
            "decision_status": "go",
            "observed": {
                "readiness": {
                    "latest_ready_streak": 3,
                    "remaining_for_window": 0,
                    "remaining_for_streak": 0,
                }
            },
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
        },
    )

    snapshot, warnings = panel.load_fail_nightly_progress_snapshot(tmp_path)
    assert warnings == []
    assert snapshot is not None
    assert snapshot["readiness_status"] == "ready"
    assert snapshot["latest_ready_streak"] == 3
    assert snapshot["decision_status"] == "go"
    assert snapshot["remaining_for_window"] == 0
    assert snapshot["remaining_for_streak"] == 0
    assert snapshot["target_critical_policy"] == "fail_nightly"
    assert snapshot["reason_codes"] == []
    assert snapshot["missing_sources"] == []
    assert snapshot["available_sources"] == ["governance", "progress", "readiness"]


def test_load_fail_nightly_progress_snapshot_invalid_optional_json_is_warning(tmp_path: Path) -> None:
    sources = panel.canonical_fail_nightly_progress_sources(tmp_path)
    _write_json(
        sources["readiness"],
        {
            "schema_version": "gateway_sla_fail_nightly_readiness_v1",
            "readiness_status": "not_ready",
            "recommendation": {"target_critical_policy": "signal_only", "reason_codes": ["insufficient_window"]},
        },
    )
    sources["governance"].parent.mkdir(parents=True, exist_ok=True)
    sources["governance"].write_text("{bad", encoding="utf-8")

    snapshot, warnings = panel.load_fail_nightly_progress_snapshot(tmp_path)
    assert snapshot is not None
    assert snapshot["readiness_status"] == "not_ready"
    assert snapshot["decision_status"] is None
    assert "progress" in snapshot["missing_sources"]
    assert warnings
    assert any("failed to parse JSON" in item for item in warnings)
