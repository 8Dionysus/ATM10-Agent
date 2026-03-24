from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import scripts.operator_product_safe_actions as safe_actions
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


class _FakeStreamlit:
    def __init__(self) -> None:
        self.subheaders: list[str] = []
        self.dataframes: list[object] = []
        self.successes: list[str] = []
        self.infos: list[str] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.captions: list[str] = []
        self.json_payloads: list[object] = []

    def subheader(self, value: str) -> None:
        self.subheaders.append(value)

    def dataframe(self, value: object, **_kwargs: object) -> None:
        self.dataframes.append(value)

    def success(self, value: str) -> None:
        self.successes.append(value)

    def info(self, value: str) -> None:
        self.infos.append(value)

    def error(self, value: str) -> None:
        self.errors.append(value)

    def warning(self, value: str) -> None:
        self.warnings.append(value)

    def caption(self, value: str) -> None:
        self.captions.append(value)

    def json(self, value: object) -> None:
        self.json_payloads.append(value)

    def write(self, value: object) -> None:
        self.infos.append(str(value))


def test_canonical_summary_sources_returns_expected_paths(tmp_path: Path) -> None:
    sources = panel.canonical_summary_sources(tmp_path)
    assert list(sources.keys()) == [
        "phase_a",
        "retrieve",
        "eval",
        "gateway_core",
        "gateway_hybrid",
        "gateway_automation",
        "gateway_combo_a",
        "gateway_http_core",
        "gateway_http_hybrid",
        "gateway_http_automation",
        "gateway_http_combo_a",
        "cross_service_suite",
        "cross_service_suite_combo_a",
        "combo_a_operating_cycle",
    ]
    assert sources["phase_a"] == tmp_path / "ci-smoke-phase-a" / "smoke_summary.json"
    assert sources["gateway_hybrid"] == tmp_path / "ci-smoke-gateway-hybrid" / "gateway_smoke_summary.json"
    assert sources["gateway_combo_a"] == tmp_path / "ci-smoke-gateway-combo-a" / "gateway_smoke_summary.json"
    assert sources["gateway_http_automation"] == (
        tmp_path
        / "ci-smoke-gateway-http-automation"
        / "gateway_http_smoke_summary.json"
    )
    assert sources["gateway_http_combo_a"] == (
        tmp_path
        / "ci-smoke-gateway-http-combo-a"
        / "gateway_http_smoke_summary.json"
    )
    assert sources["cross_service_suite"] == (
        tmp_path
        / "ci-smoke-cross-service-suite"
        / "cross_service_benchmark_suite.json"
    )
    assert sources["cross_service_suite_combo_a"] == (
        tmp_path
        / "nightly-combo-a-cross-service-suite"
        / "cross_service_benchmark_suite.json"
    )
    assert sources["combo_a_operating_cycle"] == (
        tmp_path
        / "nightly-combo-a-operating-cycle"
        / "operating_cycle_summary.json"
    )


def test_sync_runs_dir_state_keeps_operator_runs_dir_aligned() -> None:
    session_state = {
        "runs_dir": "D:/runs/old",
        "operator_runs_dir": "D:/runs/old",
    }

    panel.sync_runs_dir_state(session_state, "D:/runs/new")

    assert session_state["runs_dir"] == "D:/runs/new"
    assert session_state["operator_runs_dir"] == "D:/runs/new"


def test_sync_runs_dir_state_preserves_explicit_operator_runs_override() -> None:
    session_state = {
        "runs_dir": "D:/runs/old",
        "operator_runs_dir": "D:/operator/explicit",
    }

    panel.sync_runs_dir_state(session_state, "D:/runs/new")

    assert session_state["runs_dir"] == "D:/runs/new"
    assert session_state["operator_runs_dir"] == "D:/operator/explicit"


def test_streamlit_operator_panel_uses_stretch_width_not_deprecated_flag() -> None:
    source_path = panel.REPO_ROOT / "scripts" / "streamlit_operator_panel.py"
    source_text = source_path.read_text(encoding="utf-8")
    assert "use_container_width=" not in source_text
    assert 'width="stretch"' in source_text


def test_canonical_fail_nightly_progress_sources_returns_expected_paths(tmp_path: Path) -> None:
    sources = panel.canonical_fail_nightly_progress_sources(tmp_path)
    assert list(sources.keys()) == ["readiness", "governance", "progress"]
    assert sources["readiness"] == tmp_path / "nightly-gateway-sla-readiness" / "readiness_summary.json"
    assert sources["governance"] == tmp_path / "nightly-gateway-sla-governance" / "governance_summary.json"
    assert sources["progress"] == tmp_path / "nightly-gateway-sla-progress" / "progress_summary.json"


def test_canonical_fail_nightly_remediation_source_returns_expected_path(tmp_path: Path) -> None:
    assert panel.canonical_fail_nightly_remediation_source(tmp_path) == (
        tmp_path / "nightly-gateway-sla-remediation" / "remediation_summary.json"
    )


def test_canonical_fail_nightly_transition_source_returns_expected_path(tmp_path: Path) -> None:
    assert panel.canonical_fail_nightly_transition_source(tmp_path) == (
        tmp_path / "nightly-gateway-sla-transition" / "transition_summary.json"
    )


def test_canonical_fail_nightly_integrity_source_returns_expected_path(tmp_path: Path) -> None:
    assert panel.canonical_fail_nightly_integrity_source(tmp_path) == (
        tmp_path / "nightly-gateway-sla-integrity" / "integrity_summary.json"
    )


def test_canonical_operating_cycle_source_returns_expected_path(tmp_path: Path) -> None:
    assert panel.canonical_operating_cycle_source(tmp_path) == (
        tmp_path / "nightly-gateway-sla-operating-cycle" / "operating_cycle_summary.json"
    )


def test_canonical_combo_a_operating_cycle_source_returns_expected_path(tmp_path: Path) -> None:
    assert panel.canonical_combo_a_operating_cycle_source(tmp_path) == (
        tmp_path / "nightly-combo-a-operating-cycle" / "operating_cycle_summary.json"
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


def test_fetch_gateway_operator_snapshot_failure_returns_error() -> None:
    payload, error = panel.fetch_gateway_operator_snapshot("http://127.0.0.1:1", timeout_sec=0.1)
    assert payload is None
    assert error is not None


def test_fetch_gateway_operator_snapshot_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "schema_version": "gateway_operator_status_v1",
                    "status": "ok",
                    "gateway": {"status": "ok"},
                    "stack_services": {},
                    "latest_metrics": {"summary_matrix": []},
                    "warnings": {"metrics": [], "service_probes": []},
                }
            ).encode("utf-8")

    monkeypatch.setattr(panel.request, "urlopen", lambda req, timeout: _FakeResponse())
    payload, error = panel.fetch_gateway_operator_snapshot("http://127.0.0.1:8770", timeout_sec=0.1)
    assert error is None
    assert payload is not None
    assert payload["schema_version"] == "gateway_operator_status_v1"


def test_fetch_gateway_operator_snapshot_rejects_schema_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps({"schema_version": "wrong", "status": "ok"}).encode("utf-8")

    monkeypatch.setattr(panel.request, "urlopen", lambda req, timeout: _FakeResponse())
    payload, error = panel.fetch_gateway_operator_snapshot("http://127.0.0.1:8770", timeout_sec=0.1)
    assert payload is None
    assert error is not None


def test_fetch_gateway_operator_runs_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "schema_version": "gateway_operator_runs_v1",
                    "status": "ok",
                    "rows": [{"source": "phase_a", "status": "ok"}],
                }
            ).encode("utf-8")

    monkeypatch.setattr(panel.request, "urlopen", lambda req, timeout: _FakeResponse())
    payload, error = panel.fetch_gateway_operator_runs("http://127.0.0.1:8770", timeout_sec=0.1)
    assert error is None
    assert payload is not None
    assert payload["schema_version"] == "gateway_operator_runs_v1"


def test_fetch_gateway_operator_history_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "schema_version": "gateway_operator_history_v1",
                    "status": "ok",
                    "rows": [],
                    "warnings": [],
                }
            ).encode("utf-8")

    monkeypatch.setattr(panel.request, "urlopen", lambda req, timeout: _FakeResponse())
    payload, error = panel.fetch_gateway_operator_history(
        "http://127.0.0.1:8770",
        timeout_sec=0.1,
        selected_sources=["phase_a"],
        selected_statuses=["ok"],
        limit_per_source=3,
    )
    assert error is None
    assert payload is not None
    assert payload["schema_version"] == "gateway_operator_history_v1"


def test_fetch_gateway_safe_actions_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "schema_version": "gateway_operator_safe_actions_v1",
                    "status": "ok",
                    "catalog": [],
                    "recent_runs": [],
                }
            ).encode("utf-8")

    monkeypatch.setattr(panel.request, "urlopen", lambda req, timeout: _FakeResponse())
    payload, error = panel.fetch_gateway_safe_actions("http://127.0.0.1:8770", timeout_sec=0.1)
    assert error is None
    assert payload is not None
    assert payload["schema_version"] == "gateway_operator_safe_actions_v1"


def test_safe_action_catalog_includes_cross_service_suite_smoke() -> None:
    catalog = safe_actions.safe_action_catalog()
    action_keys = {item["action_key"] for item in catalog}
    assert "cross_service_suite_smoke" in action_keys
    assert "cross_service_suite_combo_a_smoke" in action_keys
    assert "combo_a_operating_cycle_smoke" in action_keys
    assert "gateway_local_combo_a" in action_keys
    assert "gateway_http_combo_a" in action_keys
    assert "gateway_sla_operating_cycle_smoke" in action_keys


def test_run_gateway_safe_action_surfaces_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _HttpError(panel.url_error.HTTPError):
        def __init__(self):
            super().__init__(
                url="http://127.0.0.1:8770/v1/operator/safe-actions/run",
                code=400,
                msg="Bad Request",
                hdrs=None,
                fp=None,
            )

        def read(self) -> bytes:
            return json.dumps({"error": "payload.confirm must be true"}).encode("utf-8")

    def _boom(req, timeout):
        raise _HttpError()

    monkeypatch.setattr(panel.request, "urlopen", _boom)
    payload, error = panel.run_gateway_safe_action(
        "http://127.0.0.1:8770",
        timeout_sec=0.1,
        action_key="gateway_local_core",
        confirm=True,
    )
    assert payload is None
    assert "payload.confirm must be true" in str(error)


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


def test_resolve_safe_action_supports_hybrid_smokes(tmp_path: Path) -> None:
    local_command, local_summary = panel.resolve_safe_action("gateway_local_hybrid", tmp_path)
    http_command, http_summary = panel.resolve_safe_action("gateway_http_hybrid", tmp_path)

    assert "scripts/gateway_v1_smoke.py" in local_command
    assert "hybrid" in local_command
    assert str(local_summary).endswith("gateway_smoke_summary.json")
    assert "scripts/gateway_v1_http_smoke.py" in http_command
    assert "hybrid" in http_command
    assert str(http_summary).endswith("gateway_http_smoke_summary.json")


def test_resolve_safe_action_supports_combo_a_smokes(tmp_path: Path) -> None:
    local_command, local_summary = panel.resolve_safe_action("gateway_local_combo_a", tmp_path)
    http_command, http_summary = panel.resolve_safe_action("gateway_http_combo_a", tmp_path)
    suite_command, suite_summary = panel.resolve_safe_action("cross_service_suite_combo_a_smoke", tmp_path)

    assert "scripts/gateway_v1_smoke.py" in local_command
    assert "combo_a" in local_command
    assert str(local_summary).endswith("gateway_smoke_summary.json")

    assert "scripts/gateway_v1_http_smoke.py" in http_command
    assert "combo_a" in http_command
    assert str(http_summary).endswith("gateway_http_smoke_summary.json")

    assert "scripts/cross_service_benchmark_suite.py" in suite_command
    assert "--profile" in suite_command
    assert "combo_a" in suite_command
    assert str(suite_summary).endswith("cross_service_benchmark_suite.json")


def test_resolve_safe_action_supports_combo_a_operating_cycle(tmp_path: Path) -> None:
    command, summary_path = panel.resolve_safe_action("combo_a_operating_cycle_smoke", tmp_path)
    assert "scripts/run_combo_a_operating_cycle.py" in command
    assert "--scenario" not in command
    assert str(summary_path).endswith("operating_cycle_summary.json")


def test_resolve_safe_action_supports_gateway_sla_operating_cycle(tmp_path: Path) -> None:
    command, summary_path = panel.resolve_safe_action("gateway_sla_operating_cycle_smoke", tmp_path)
    assert "scripts/run_gateway_sla_operating_cycle.py" in command
    assert "--scenario" not in command
    assert str(summary_path).endswith("operating_cycle_summary.json")


def test_run_safe_action_fails_when_summary_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed = subprocess.CompletedProcess(args=["python"], returncode=0, stdout="ok", stderr="")

    def _fake_run(*args, **kwargs):
        return completed

    monkeypatch.setattr(safe_actions.subprocess, "run", _fake_run)
    result = panel.run_safe_action("gateway_local_core", tmp_path)
    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["error"] is not None
    assert isinstance(result["timestamp_utc"], str)


def test_safe_actions_tab_source_uses_gateway_and_not_local_subprocess() -> None:
    source_text = panel.REPO_ROOT.joinpath("scripts", "streamlit_operator_panel.py").read_text(encoding="utf-8")
    assert "run_gateway_safe_action(" in source_text
    assert "Safe Actions require a reachable gateway operator API." in source_text
    assert "Operator triage" in source_text
    assert "Pilot runtime" in source_text
    assert "Combo A Promotion" in source_text
    assert "Current Policy" in source_text
    assert "Why Hold" in source_text
    assert "Next Action" in source_text
    assert "Live Readiness" in source_text
    assert "Manual Fallback Status" in source_text
    assert "Startup diagnostics" in source_text
    assert "Attention services" in source_text
    assert "Next step" in source_text
    assert "Governance diagnostics" in source_text


def test_render_stack_health_tab_renders_snapshot_driven_operator_triage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(panel, "st", fake_st)
    monkeypatch.setattr(panel, "_render_combo_a_promotion_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel, "_render_operator_startup_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel, "_render_snapshot_warnings", lambda *args, **kwargs: None)

    panel._render_stack_health_tab(
        health_payload={"status": "ok"},
        health_error=None,
        operator_snapshot_payload={
            "schema_version": "gateway_operator_status_v1",
            "status": "ok",
            "stack_services": {
                "gateway_v1_http_service": {
                    "configured": True,
                    "status": "ok",
                    "payload": {"auth_enabled": False, "api_docs_exposed": False},
                    "url": None,
                    "error": None,
                }
            },
            "operator_context": {
                "triage": {
                    "overall_state": "attention",
                    "primary_surface": "governance",
                    "primary_code": "remediation_backlog_pending",
                    "primary_message": "Resolve the remediation backlog before promoting nightly policy.",
                    "next_step_code": "run_safe_action",
                    "next_step": "Run safe action gateway_sla_operating_cycle_smoke from the gateway operator surface.",
                    "next_safe_action": "gateway_sla_operating_cycle_smoke",
                    "attention_services": ["voice_runtime_service"],
                    "stack_rollup": {
                        "total_services": 5,
                        "configured_services": 2,
                        "healthy_services": 1,
                        "attention_services": 1,
                        "not_configured_services": 3,
                    },
                    "startup_overall_state": "healthy",
                    "governance_decision_status": "remediate",
                    "governance_top_blocker": "remediation_backlog_pending",
                    "combo_a_availability_status": "partial",
                    "combo_a_promotion_state": "hold",
                },
                "profiles": {"combo_a": {}},
            },
            "warnings": {"service_probes": [], "combo_a_policy_surface": []},
        },
        operator_snapshot_error=None,
        operator_startup_payload=None,
        operator_startup_warnings=[],
    )

    assert "Operator triage" in fake_st.subheaders
    triage_table = next(
        item
        for item in fake_st.dataframes
        if isinstance(item, list)
        and item
        and isinstance(item[0], dict)
        and item[0].get("primary_surface") == "governance"
    )
    assert triage_table[0]["overall_state"] == "attention"
    assert triage_table[0]["next_safe_action"] == "gateway_sla_operating_cycle_smoke"
    assert triage_table[0]["attention_service_count"] == 1
    assert any("Resolve the remediation backlog" in item for item in fake_st.infos)
    assert any("Run safe action gateway_sla_operating_cycle_smoke" in item for item in fake_st.infos)


def test_render_stack_health_tab_does_not_synthesize_operator_triage_without_snapshot_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(panel, "st", fake_st)
    monkeypatch.setattr(panel, "_render_combo_a_promotion_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel, "_render_operator_startup_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel, "_render_snapshot_warnings", lambda *args, **kwargs: None)

    panel._render_stack_health_tab(
        health_payload={"status": "ok"},
        health_error=None,
        operator_snapshot_payload={
            "schema_version": "gateway_operator_status_v1",
            "status": "ok",
            "stack_services": {},
            "operator_context": {"profiles": {"combo_a": {}}},
            "warnings": {"service_probes": [], "combo_a_policy_surface": []},
        },
        operator_snapshot_error=None,
        operator_startup_payload=None,
        operator_startup_warnings=[],
    )

    assert "Operator triage" not in fake_st.subheaders


def test_render_stack_health_tab_renders_pilot_runtime_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(panel, "st", fake_st)
    monkeypatch.setattr(panel, "_render_combo_a_promotion_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel, "_render_operator_startup_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel, "_render_snapshot_warnings", lambda *args, **kwargs: None)

    panel._render_stack_health_tab(
        health_payload={"status": "ok"},
        health_error=None,
        operator_snapshot_payload={
            "schema_version": "gateway_operator_status_v1",
            "status": "ok",
            "stack_services": {},
            "operator_context": {
                "pilot_runtime": {
                    "status": "running",
                    "state": "idle",
                    "hotkey": "F8",
                    "input_device_index": 1,
                    "vlm_provider": "openvino",
                    "text_provider": "openvino",
                    "provider_init": {
                        "vlm": {"status": "ok", "provider": "openvino"},
                        "text": {"status": "ok", "provider": "openvino"},
                    },
                    "last_turn_id": "turn-1",
                    "degraded_services": ["gateway"],
                    "last_error": None,
                    "paths": {"latest_status_json": "runs/pilot_runtime_status_latest.json"},
                },
                "last_turn_summary": {
                    "turn_id": "turn-1",
                    "status": "degraded",
                    "timestamp_utc": "2026-03-22T18:00:00+00:00",
                    "degraded_flags": ["retrieval_only_fallback"],
                    "answer_language": "ru",
                    "vision_provider": "openvino_genai_vlm_v1",
                    "grounded_reply_provider": "openvino_genai_grounded_reply_v1",
                    "tts_engine": "windows_sapi_fallback",
                    "session_window_found": True,
                    "session_atm10_probable": True,
                    "session_foreground": True,
                    "session_process_name": "javaw.exe",
                    "session_window_title": "Minecraft 1.21.1 - ATM10",
                    "session_reason_codes": [],
                    "hud_state_status": "partial",
                    "hud_line_count": 2,
                    "quest_update_count": 1,
                    "has_player_state": True,
                    "hud_reason_codes": ["ocr_unavailable", "mod_hook_not_configured"],
                    "answer_preview": "Pilot degraded mode. Quest book is still the next step.",
                },
                "pilot_readiness": {
                    "readiness_status": "attention",
                    "actionable_message": "Pilot evidence is valid, but it comes from fixture artifacts.",
                    "blocking_reason_codes": ["pilot_turn_not_live_evidence"],
                    "next_step_code": "complete_live_pilot_turn",
                    "next_step": "Complete one live push-to-talk turn.",
                    "evidence": {
                        "last_turn_fresh_within_window": True,
                        "live_turn_evidence": False,
                        "session_window_found": True,
                        "session_atm10_probable": True,
                        "session_foreground": True,
                        "hud_state_status": "partial",
                    },
                    "paths": {"summary_json": "runs/pilot-runtime-readiness/readiness_summary.json"},
                },
                "profiles": {"combo_a": {}},
            },
            "warnings": {
                "service_probes": [],
                "combo_a_policy_surface": [],
                "pilot_runtime": [],
                "pilot_readiness": [],
            },
        },
        operator_snapshot_error=None,
        operator_startup_payload=None,
        operator_startup_warnings=[],
    )

    assert "Pilot runtime" in fake_st.subheaders
    assert "Pilot readiness" in fake_st.subheaders
    pilot_table = next(
        item
        for item in fake_st.dataframes
        if isinstance(item, list) and item and isinstance(item[0], dict) and item[0].get("last_turn_id") == "turn-1"
    )
    assert pilot_table[0]["status"] == "running"
    assert pilot_table[0]["vlm_provider"] == "openvino"
    assert pilot_table[0]["text_provider"] == "openvino"
    evidence_table = next(
        item
        for item in fake_st.dataframes
        if isinstance(item, list)
        and item
        and isinstance(item[0], dict)
        and "window_found" in item[0]
    )
    assert evidence_table[0]["window_found"] is True
    assert evidence_table[0]["hud_line_count"] == 2
    readiness_table = next(
        item
        for item in fake_st.dataframes
        if isinstance(item, list)
        and item
        and isinstance(item[0], dict)
        and item[0].get("readiness_status") == "attention"
    )
    assert readiness_table[0]["next_step_code"] == "complete_live_pilot_turn"
    assert any(
        isinstance(item, list)
        and item
        and isinstance(item[0], dict)
        and item[0].get("turn_id") == "turn-1"
        for item in fake_st.dataframes
    )
    last_turn_table = next(
        item
        for item in fake_st.dataframes
        if isinstance(item, list)
        and item
        and isinstance(item[0], dict)
        and item[0].get("turn_id") == "turn-1"
    )
    assert last_turn_table[0]["answer_language"] == "ru"
    assert last_turn_table[0]["vision_provider"] == "openvino_genai_vlm_v1"
    assert last_turn_table[0]["tts_engine"] == "windows_sapi_fallback"


def test_render_pilot_readiness_section_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(panel, "st", fake_st)
    monkeypatch.setattr(panel, "_render_snapshot_warnings", lambda *args, **kwargs: None)

    panel._render_pilot_readiness_section(
        {
            "readiness_status": "ready",
            "actionable_message": "Pilot live acceptance is green.",
            "blocking_reason_codes": [],
            "next_step_code": "none",
            "next_step": "No action required.",
            "evidence": {
                "last_turn_fresh_within_window": True,
                "live_turn_evidence": True,
                "session_window_found": True,
                "session_atm10_probable": True,
                "session_foreground": True,
                "hud_state_status": "partial",
            },
            "paths": {"summary_json": "runs/pilot-runtime-readiness/readiness_summary.json"},
        },
        [],
    )

    assert "Pilot readiness" in fake_st.subheaders
    assert fake_st.successes == ["Pilot live acceptance is green."]
    readiness_table = next(
        item
        for item in fake_st.dataframes
        if isinstance(item, list)
        and item
        and isinstance(item[0], dict)
        and item[0].get("readiness_status") == "ready"
    )
    assert readiness_table[0]["last_turn_fresh"] is True
    assert readiness_table[0]["session_atm10_probable"] is True
    assert readiness_table[0]["hud_state_status"] == "partial"


def test_render_pilot_readiness_section_not_available(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(panel, "st", fake_st)
    monkeypatch.setattr(panel, "_render_snapshot_warnings", lambda *args, **kwargs: None)

    panel._render_pilot_readiness_section(None, [])

    assert "Pilot readiness" in fake_st.subheaders
    assert fake_st.infos == ["Pilot readiness summary is not available yet."]


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


def test_build_metrics_rows_expands_cross_service_suite_summary(tmp_path: Path) -> None:
    summary_path = tmp_path / "ci-smoke-cross-service-suite" / "cross_service_benchmark_suite.json"
    _write_json(
        summary_path,
        {
            "schema_version": "cross_service_benchmark_suite_v1",
            "status": "ok",
            "summary_matrix": [
                {
                    "source": "voice_asr",
                    "backend": "whisper_genai",
                    "status": "ok",
                    "sla_status": "pass",
                    "sample_count": 2,
                    "latency_p95_ms": 12.5,
                    "quality_primary_name": "text_similarity_avg",
                    "quality_primary_value": 1.0,
                    "summary_json": "runs/voice_asr/service_sla_summary.json",
                },
                {
                    "source": "retrieval",
                    "backend": "in_memory",
                    "status": "ok",
                    "sla_status": "pass",
                    "sample_count": 3,
                    "latency_p95_ms": 4.0,
                    "quality_primary_name": "mean_mrr_at_k",
                    "quality_primary_value": 1.0,
                    "summary_json": "runs/retrieval/service_sla_summary.json",
                },
            ],
        },
    )

    rows = panel.build_metrics_rows({"cross_service_suite": summary_path})
    assert len(rows) == 2
    assert rows[0]["source"] == "voice_asr"
    assert rows[1]["source"] == "retrieval"


def test_build_run_explorer_rows_expands_cross_service_suite_children(tmp_path: Path) -> None:
    summary_path = tmp_path / "ci-smoke-cross-service-suite" / "cross_service_benchmark_suite.json"
    _write_json(
        summary_path,
        {
            "schema_version": "cross_service_benchmark_suite_v1",
            "status": "ok",
            "services": {
                "voice_asr": {"status": "ok"},
                "voice_tts": {"status": "error"},
            },
            "degraded_services": ["voice_tts"],
            "paths": {
                "run_dir": "runs/cross-service",
                "run_json": "runs/cross-service/run.json",
                "child_runs": {
                    "voice_asr": {
                        "run_dir": "runs/cross-service/voice-asr",
                        "run_json": "runs/cross-service/voice-asr/run.json",
                        "summary_json": "runs/cross-service/voice-asr/service_sla_summary.json",
                    },
                    "voice_tts": {
                        "run_dir": "runs/cross-service/voice-tts",
                        "run_json": "runs/cross-service/voice-tts/run.json",
                        "summary_json": "runs/cross-service/voice-tts/service_sla_summary.json",
                    },
                },
            },
        },
    )

    rows = panel.build_run_explorer_rows({"cross_service_suite": summary_path})
    assert len(rows) == 3
    assert rows[0]["source"] == "cross_service_suite"
    assert rows[1]["source"] == "cross_service_suite:voice_asr"
    assert rows[2]["source"] == "cross_service_suite:voice_tts"


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
    assert rows[0]["surface"] == "retrieval"
    assert rows[0]["mode"] == "retrieve_demo"
    assert rows[0]["scenario"] is None
    assert rows[0]["results_count"] == 3
    assert rows[0]["result_summary"] == "results=3"


def test_build_metrics_history_rows_supports_hybrid_gateway_sources(tmp_path: Path) -> None:
    roots = panel.canonical_history_roots(tmp_path)
    run_dir = _create_history_run(
        root=roots["gateway_hybrid"],
        run_name="20260228_100700-gateway-v1-smoke-hybrid",
        mode="gateway_v1_smoke",
        scenario="hybrid",
        timestamp_utc="2026-02-28T10:07:00+00:00",
    )
    _write_json(
        run_dir / "run.json",
        {
            "mode": "gateway_v1_smoke",
            "status": "ok",
            "scenario": "hybrid",
            "timestamp_utc": "2026-02-28T10:07:00+00:00",
            "result": {"request_count": 1, "failed_requests_count": 0},
            "paths": {
                "run_json": str(run_dir / "run.json"),
                "summary_json": str(tmp_path / "ci-smoke-gateway-hybrid" / "gateway_smoke_summary.json"),
            },
        },
    )

    rows, warnings = panel.build_metrics_history_rows(
        tmp_path,
        selected_sources=["gateway_hybrid"],
        selected_statuses=["ok", "error"],
        limit_per_source=10,
    )
    assert warnings == []
    assert len(rows) == 1
    assert rows[0]["source"] == "gateway_hybrid"
    assert rows[0]["surface"] == "gateway_local"
    assert rows[0]["mode"] == "gateway_v1_smoke"
    assert rows[0]["scenario"] == "hybrid"
    assert rows[0]["request_count"] == 1
    assert rows[0]["failed_requests_count"] == 0
    assert rows[0]["result_summary"] == "requests=1, failed=0"


def test_build_metrics_history_rows_supports_cross_service_suite_source(tmp_path: Path) -> None:
    roots = panel.canonical_history_roots(tmp_path)
    run_dir = _create_history_run(
        root=roots["cross_service_suite"],
        run_name="20260322_190000-cross-service-suite",
        mode="cross_service_benchmark_suite",
        timestamp_utc="2026-03-22T19:00:00+00:00",
    )
    summary_path = run_dir / "cross_service_benchmark_suite.json"
    _write_json(
        run_dir / "run.json",
        {
            "mode": "cross_service_benchmark_suite",
            "status": "ok",
            "timestamp_utc": "2026-03-22T19:00:00+00:00",
            "paths": {
                "run_json": str(run_dir / "run.json"),
                "summary_json": str(summary_path),
            },
        },
    )
    _write_json(
        summary_path,
        {
            "schema_version": "cross_service_benchmark_suite_v1",
            "status": "ok",
            "overall_sla_status": "breach",
            "services": {
                "voice_asr": {},
                "voice_tts": {},
                "retrieval": {},
                "kag_file": {},
            },
            "degraded_services": ["voice_tts"],
        },
    )

    rows, warnings = panel.build_metrics_history_rows(
        tmp_path,
        selected_sources=["cross_service_suite"],
        selected_statuses=["ok", "error"],
        limit_per_source=10,
    )
    assert warnings == []
    assert len(rows) == 1
    assert rows[0]["source"] == "cross_service_suite"
    assert rows[0]["surface"] == "cross_service_suite"
    assert rows[0]["mode"] == "cross_service_benchmark_suite"
    assert rows[0]["scenario"] is None
    assert rows[0]["request_count"] == 4
    assert rows[0]["failed_requests_count"] == 1
    assert rows[0]["details"] == "breach"
    assert rows[0]["result_summary"] == "sla=breach, services=4, degraded=1"


def test_build_metrics_history_rows_supports_combo_a_operating_cycle_source(tmp_path: Path) -> None:
    roots = panel.canonical_history_roots(tmp_path)
    run_dir = _create_history_run(
        root=roots["combo_a_operating_cycle"],
        run_name="20260322_191000-combo-a-operating-cycle",
        mode="combo_a_operating_cycle",
        scenario="combo_a_policy",
        timestamp_utc="2026-03-22T19:10:00+00:00",
    )
    summary_path = run_dir / "operating_cycle_summary.json"
    _write_json(
        run_dir / "run.json",
        {
            "mode": "combo_a_operating_cycle",
            "status": "ok",
            "scenario": "combo_a_policy",
            "timestamp_utc": "2026-03-22T19:10:00+00:00",
            "paths": {
                "run_json": str(run_dir / "run.json"),
                "summary_json": str(summary_path),
            },
        },
    )
    _write_json(
        summary_path,
        {
            "schema_version": "combo_a_operating_cycle_summary_v1",
            "status": "ok",
            "effective_policy": "observe_only",
            "promotion_state": "hold",
            "blocking_reason_codes": ["required_sources_not_fresh"],
        },
    )

    rows, warnings = panel.build_metrics_history_rows(
        tmp_path,
        selected_sources=["combo_a_operating_cycle"],
        selected_statuses=["ok", "error"],
        limit_per_source=10,
    )
    assert warnings == []
    assert len(rows) == 1
    assert rows[0]["surface"] == "combo_a_policy"
    assert rows[0]["mode"] == "combo_a_operating_cycle"
    assert rows[0]["scenario"] == "combo_a_policy"
    assert rows[0]["details"] == "observe_only/hold"
    assert rows[0]["failed_requests_count"] == 1
    assert rows[0]["result_summary"] == "policy=observe_only/hold, blockers=1"


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


def test_load_fail_nightly_remediation_snapshot_not_available_yet(tmp_path: Path) -> None:
    snapshot, warnings = panel.load_fail_nightly_remediation_snapshot(tmp_path)
    assert snapshot is None
    assert warnings == []


def test_load_fail_nightly_remediation_snapshot_happy_path(tmp_path: Path) -> None:
    summary_path = panel.canonical_fail_nightly_remediation_source(tmp_path)
    _write_json(
        summary_path,
        {
            "schema_version": "gateway_sla_fail_nightly_remediation_v1",
            "status": "ok",
            "checked_at_utc": "2026-03-12T08:00:00+00:00",
            "policy": "report_only",
            "observed": {
                "readiness_status": "not_ready",
                "governance_decision_status": "hold",
                "progress_decision_status": "hold",
                "transition_allow_switch": False,
                "remaining_for_window": 12,
                "remaining_for_streak": 3,
                "attention_state": "ready_for_accounted_run",
            },
            "reason_codes": ["insufficient_window", "ready_streak_below_threshold"],
            "candidate_items": [
                {
                    "id": "window_accumulation",
                    "priority": "medium",
                    "summary": "Accumulate more accounted runs.",
                    "source_refs": ["progress", "readiness"],
                }
            ],
            "paths": {"summary_json": str(summary_path)},
        },
    )

    snapshot, warnings = panel.load_fail_nightly_remediation_snapshot(tmp_path)
    assert warnings == []
    assert snapshot is not None
    assert snapshot["status"] == "ok"
    assert snapshot["policy"] == "report_only"
    assert snapshot["observed"]["remaining_for_window"] == 12
    assert snapshot["candidate_items"][0]["id"] == "window_accumulation"


def test_load_fail_nightly_remediation_snapshot_invalid_json_is_warning(tmp_path: Path) -> None:
    summary_path = panel.canonical_fail_nightly_remediation_source(tmp_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("{bad", encoding="utf-8")

    snapshot, warnings = panel.load_fail_nightly_remediation_snapshot(tmp_path)
    assert snapshot is None
    assert warnings
    assert any("failed to parse JSON" in item for item in warnings)


def test_load_fail_nightly_transition_snapshot_happy_path(tmp_path: Path) -> None:
    summary_path = panel.canonical_fail_nightly_transition_source(tmp_path)
    _write_json(
        summary_path,
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
            "recommendation": {
                "target_critical_policy": "fail_nightly",
                "switch_surface": "nightly_only",
                "reason_codes": [],
            },
            "paths": {"summary_json": str(summary_path)},
        },
    )

    snapshot, warnings = panel.load_fail_nightly_transition_snapshot(tmp_path)
    assert warnings == []
    assert snapshot is not None
    assert snapshot["decision_status"] == "allow"
    assert snapshot["allow_switch"] is True
    assert snapshot["recommendation"]["target_critical_policy"] == "fail_nightly"


def test_load_latest_operator_startup_status_happy_path(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260322_120000-start-operator-product"
    run_dir.mkdir(parents=True, exist_ok=True)
    run_json_path = run_dir / "run.json"
    startup_plan_json = run_dir / "startup_plan.json"
    startup_plan_json.write_text("{}", encoding="utf-8")
    _write_json(
        run_json_path,
        {
            "schema_version": "operator_product_startup_v1",
            "mode": "start_operator_product",
            "status": "running",
            "profile": "operator_product_core",
            "timestamp_utc": "2026-03-22T12:00:00+00:00",
            "gateway_url": "http://127.0.0.1:8770",
            "streamlit_url": "http://127.0.0.1:8501",
            "paths": {
                "run_json": str(run_json_path),
                "startup_plan_json": str(startup_plan_json),
                "gateway_log": str(run_dir / "gateway.log"),
                "streamlit_log": str(run_dir / "streamlit.log"),
            },
            "session_state": {
                "gateway": {
                    "service_name": "gateway",
                    "managed": True,
                    "configured": True,
                    "effective_url": "http://127.0.0.1:8770",
                    "status": "running",
                    "pid": 1234,
                    "last_probe": {"status": "ok"},
                }
            },
            "child_processes": {"gateway": {"pid": 1234, "return_code": None}},
            "startup_checkpoints": [{"stage": "probe", "status": "ok"}],
            "last_checkpoint": {"stage": "probe", "status": "ok"},
        },
    )

    snapshot, warnings = panel.load_latest_operator_startup_status(tmp_path)
    assert warnings == []
    assert snapshot is not None
    assert snapshot["status"] == "running"
    assert snapshot["checkpoint_count"] == 1
    assert snapshot["session_state"]["gateway"]["pid"] == 1234
    assert snapshot["diagnostics"]["overall_state"] == "healthy"
    assert snapshot["diagnostics"]["service_rollup"]["total_services"] == 1
    assert snapshot["diagnostics"]["service_rollup"]["healthy_services"] == 1
    assert snapshot["diagnostics"]["service_rollup"]["attention_services"] == 0
    assert snapshot["diagnostics"]["next_step_code"] == "none"
    assert snapshot["diagnostics"]["next_step"] is None


def test_load_latest_operator_startup_status_builds_attention_service_triage(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260322_121500-start-operator-product"
    run_dir.mkdir(parents=True, exist_ok=True)
    run_json_path = run_dir / "run.json"
    startup_plan_json = run_dir / "startup_plan.json"
    startup_plan_json.write_text("{}", encoding="utf-8")
    _write_json(
        run_json_path,
        {
            "schema_version": "operator_product_startup_v1",
            "mode": "start_operator_product",
            "status": "running",
            "profile": "operator_product_core",
            "timestamp_utc": "2026-03-22T12:15:00+00:00",
            "gateway_url": "http://127.0.0.1:8770",
            "streamlit_url": "http://127.0.0.1:8501",
            "paths": {
                "run_json": str(run_json_path),
                "startup_plan_json": str(startup_plan_json),
                "gateway_log": str(run_dir / "gateway.log"),
                "streamlit_log": str(run_dir / "streamlit.log"),
            },
            "session_state": {
                "gateway": {
                    "service_name": "gateway",
                    "managed": True,
                    "configured": True,
                    "effective_url": "http://127.0.0.1:8770",
                    "status": "running",
                    "pid": 1234,
                    "last_probe": {"status": "ok"},
                    "log_path": str(run_dir / "gateway.log"),
                },
                "streamlit": {
                    "service_name": "streamlit",
                    "managed": True,
                    "configured": True,
                    "effective_url": "http://127.0.0.1:8501",
                    "status": "starting",
                    "pid": 1235,
                    "log_path": str(run_dir / "streamlit.log"),
                },
                "qdrant": {
                    "service_name": "qdrant",
                    "managed": False,
                    "configured": True,
                    "effective_url": "http://127.0.0.1:6333",
                    "status": "error",
                    "error": "connection refused",
                },
                "neo4j": {
                    "service_name": "neo4j",
                    "managed": False,
                    "configured": False,
                    "status": "not_configured",
                },
            },
            "child_processes": {
                "gateway": {"pid": 1234, "return_code": None},
                "streamlit": {"pid": 1235, "return_code": None},
            },
            "startup_checkpoints": [{"stage": "launch", "status": "ok"}],
            "last_checkpoint": {"stage": "launch", "status": "ok"},
        },
    )

    snapshot, warnings = panel.load_latest_operator_startup_status(tmp_path)
    assert warnings == []
    assert snapshot is not None
    assert snapshot["diagnostics"]["overall_state"] == "degraded"
    assert snapshot["diagnostics"]["primary_issue"] == "qdrant: connection refused"
    assert snapshot["diagnostics"]["service_rollup"] == {
        "total_services": 4,
        "configured_services": 3,
        "managed_services": 2,
        "healthy_services": 1,
        "attention_services": 2,
        "not_configured_services": 1,
        "unknown_services": 0,
    }
    attention_services = snapshot["diagnostics"]["attention_services"]
    assert [item["service_name"] for item in attention_services] == ["streamlit", "qdrant"]
    assert attention_services[0]["attention_kind"] == "pending"
    assert attention_services[1]["attention_kind"] == "service_error"
    assert snapshot["diagnostics"]["next_step_code"] == "check_service_connectivity"
    assert snapshot["diagnostics"]["next_step"] == "Check connectivity and credentials for qdrant."


def test_build_operator_governance_summary_prefers_repair_and_transition_when_available() -> None:
    summary = panel.build_operator_governance_summary(
        progress_snapshot={
            "reason_codes": ["insufficient_window_observed"],
            "remaining_for_window": 4,
            "remaining_for_streak": 1,
            "missing_sources": [],
            "source_paths": {"readiness": "runs/readiness.json"},
        },
        transition_snapshot={
            "allow_switch": True,
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            "paths": {"summary_json": "runs/transition.json"},
        },
        remediation_snapshot={
            "candidate_items": [{"id": "window_accumulation"}],
            "reason_codes": ["window_accumulation"],
            "paths": {"summary_json": "runs/remediation.json"},
        },
        integrity_snapshot={
            "decision": {"integrity_status": "attention", "reason_codes": ["required_sources_unhealthy"]},
            "paths": {"summary_json": "runs/integrity.json"},
        },
        operating_cycle_snapshot={
            "triage": {
                "remaining_for_window": 4,
                "remaining_for_streak": 1,
                "candidate_item_count": 1,
                "attention_state": "run_recovery_only",
            },
            "interpretation": {
                "telemetry_repair_required": True,
                "remediation_backlog_primary": False,
                "blocked_manual_gate": False,
                "next_action_hint": "repair_telemetry_first",
            },
            "cycle": {"operating_mode": "manual_fallback", "manual_execution_mode": "accounted"},
            "paths": {"summary_json": "runs/operating_cycle.json"},
        },
    )

    assert summary is not None
    assert summary["decision_status"] == "repair"
    assert summary["recommended_policy"] == "fail_nightly"
    assert summary["effective_gateway_sla_policy"] == "signal_only"
    assert summary["promotion_state"] == "blocked"
    assert "telemetry_repair_required" in summary["blocking_reason_codes"]
    assert summary["profile_scope"] == "baseline_first"
    assert summary["recommended_actions"][0]["action_key"] == "gateway_sla_operating_cycle_smoke"
    assert summary["next_action_hint"] == "repair_telemetry_first"
    assert summary["integrity_status"] == "attention"
    assert summary["diagnostics"]["top_blocker"] == "telemetry_repair_required"
    assert summary["diagnostics"]["next_safe_action"] == "gateway_sla_operating_cycle_smoke"


def test_build_operator_governance_summary_diagnostics_allow_state() -> None:
    summary = panel.build_operator_governance_summary(
        progress_snapshot={
            "reason_codes": [],
            "remaining_for_window": 0,
            "remaining_for_streak": 0,
            "missing_sources": [],
            "source_paths": {"readiness": "runs/readiness.json"},
        },
        transition_snapshot={
            "allow_switch": True,
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
            "paths": {"summary_json": "runs/transition.json"},
        },
        remediation_snapshot={
            "candidate_items": [],
            "reason_codes": [],
            "paths": {"summary_json": "runs/remediation.json"},
        },
        integrity_snapshot={
            "decision": {"integrity_status": "clean", "reason_codes": []},
            "paths": {"summary_json": "runs/integrity.json"},
        },
        operating_cycle_snapshot={
            "effective_policy": "fail_nightly",
            "promotion_state": "eligible",
            "blocking_reason_codes": [],
            "recommended_actions": [
                {
                    "action_key": "gateway_sla_operating_cycle_smoke",
                    "reason": "keep policy evidence fresh",
                }
            ],
            "triage": {
                "remaining_for_window": 0,
                "remaining_for_streak": 0,
                "candidate_item_count": 0,
                "attention_state": "ready_for_accounted_run",
            },
            "interpretation": {
                "telemetry_repair_required": False,
                "remediation_backlog_primary": False,
                "blocked_manual_gate": False,
            },
            "cycle": {"operating_mode": "reuse_fresh_latest", "manual_execution_mode": "accounted"},
            "paths": {"summary_json": "runs/operating_cycle.json"},
        },
    )

    assert summary is not None
    assert summary["promotion_state"] == "eligible"
    assert summary["diagnostics"]["top_blocker"] == "none"
    assert summary["diagnostics"]["next_safe_action"] == "gateway_sla_operating_cycle_smoke"


def test_build_operator_governance_summary_diagnostics_missing_source_fallback() -> None:
    summary = panel.build_operator_governance_summary(
        progress_snapshot=None,
        transition_snapshot=None,
        remediation_snapshot=None,
        integrity_snapshot=None,
        operating_cycle_snapshot={
            "effective_policy": "signal_only",
            "promotion_state": "hold",
            "blocking_reason_codes": [],
            "recommended_actions": [],
            "triage": {
                "remaining_for_window": 0,
                "remaining_for_streak": 0,
                "candidate_item_count": 0,
                "attention_state": "ready_for_accounted_run",
            },
            "interpretation": {
                "telemetry_repair_required": False,
                "remediation_backlog_primary": False,
                "blocked_manual_gate": False,
            },
            "paths": {"summary_json": "runs/operating_cycle.json"},
        },
    )

    assert summary is not None
    assert summary["status"] == "degraded"
    assert summary["diagnostics"]["top_blocker"] == "required_sources_not_fresh"
    assert summary["diagnostics"]["next_safe_action"] == "gateway_sla_operating_cycle_smoke"


def test_load_fail_nightly_remediation_snapshot_schema_mismatch_is_warning(tmp_path: Path) -> None:
    summary_path = panel.canonical_fail_nightly_remediation_source(tmp_path)
    _write_json(
        summary_path,
        {
            "schema_version": "wrong_schema_v1",
            "status": "ok",
        },
    )

    snapshot, warnings = panel.load_fail_nightly_remediation_snapshot(tmp_path)
    assert snapshot is None
    assert warnings
    assert any("schema_version mismatch" in item for item in warnings)


def test_load_fail_nightly_integrity_snapshot_not_available_yet(tmp_path: Path) -> None:
    snapshot, warnings = panel.load_fail_nightly_integrity_snapshot(tmp_path)
    assert snapshot is None
    assert warnings == []


def test_load_fail_nightly_integrity_snapshot_happy_path(tmp_path: Path) -> None:
    summary_path = panel.canonical_fail_nightly_integrity_source(tmp_path)
    _write_json(
        summary_path,
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
            "paths": {"summary_json": str(summary_path)},
        },
    )

    snapshot, warnings = panel.load_fail_nightly_integrity_snapshot(tmp_path)
    assert warnings == []
    assert snapshot is not None
    assert snapshot["decision"]["integrity_status"] == "clean"
    assert snapshot["observed"]["telemetry_ok"] is True


def test_load_fail_nightly_integrity_snapshot_invalid_json_is_warning(tmp_path: Path) -> None:
    summary_path = panel.canonical_fail_nightly_integrity_source(tmp_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("{bad", encoding="utf-8")

    snapshot, warnings = panel.load_fail_nightly_integrity_snapshot(tmp_path)
    assert snapshot is None
    assert warnings
    assert any("failed to parse JSON" in item for item in warnings)


def test_load_operating_cycle_snapshot_not_available_yet(tmp_path: Path) -> None:
    snapshot, warnings = panel.load_operating_cycle_snapshot(tmp_path)
    assert snapshot is None
    assert warnings == []


def test_load_operating_cycle_snapshot_happy_path(tmp_path: Path) -> None:
    summary_path = panel.canonical_operating_cycle_source(tmp_path)
    _write_json(
        summary_path,
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
                "candidate_item_ids": [
                    "regression_investigation",
                    "window_accumulation",
                    "ready_streak_stabilization",
                ],
                "integrity_status": "clean",
                "attention_state": "ready_for_accounted_run",
                "earliest_go_candidate_at_utc": "2026-03-22T21:53:16.661488+00:00",
                "next_accounted_dispatch_at_utc": None,
                "invalid_counts": {
                    "governance": 0,
                    "progress_readiness": 0,
                    "progress_governance": 0,
                    "transition_aggregated": 0,
                },
            },
            "interpretation": {
                "telemetry_repair_required": False,
                "remediation_backlog_primary": True,
                "blocked_manual_gate": False,
                "next_action_hint": "continue_g2_backlog",
            },
            "paths": {
                "summary_json": str(summary_path),
                "brief_md": str(summary_path.parent / "triage_brief.md"),
            },
        },
    )

    snapshot, warnings = panel.load_operating_cycle_snapshot(tmp_path)
    assert warnings == []
    assert snapshot is not None
    assert snapshot["status"] == "ok"
    assert snapshot["policy"] == "report_only"
    assert snapshot["effective_policy"] == "signal_only"
    assert snapshot["promotion_state"] == "blocked"
    assert snapshot["enforcement_surface"] == "nightly_only"
    assert snapshot["blocking_reason_codes"] == ["remediation_backlog_pending"]
    assert snapshot["recommended_actions"][0]["action_key"] == "gateway_sla_operating_cycle_smoke"
    assert snapshot["next_review_at_utc"] == "2026-03-22T21:53:16.661488+00:00"
    assert snapshot["profile_scope"] == "baseline_first"
    assert snapshot["cycle"]["manual_execution_mode"] == "accounted"
    assert snapshot["triage"]["remaining_for_window"] == 11
    assert snapshot["interpretation"]["next_action_hint"] == "continue_g2_backlog"
    assert snapshot["paths"]["summary_json"] == str(summary_path)
    assert snapshot["paths"]["brief_md"] == str(summary_path.parent / "triage_brief.md")


def test_load_operating_cycle_snapshot_invalid_json_is_warning(tmp_path: Path) -> None:
    summary_path = panel.canonical_operating_cycle_source(tmp_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("{bad", encoding="utf-8")

    snapshot, warnings = panel.load_operating_cycle_snapshot(tmp_path)
    assert snapshot is None
    assert warnings
    assert any("failed to parse JSON" in item for item in warnings)


def test_load_operating_cycle_snapshot_schema_mismatch_is_warning(tmp_path: Path) -> None:
    summary_path = panel.canonical_operating_cycle_source(tmp_path)
    _write_json(
        summary_path,
        {
            "schema_version": "wrong_schema_v1",
            "status": "ok",
        },
    )

    snapshot, warnings = panel.load_operating_cycle_snapshot(tmp_path)
    assert snapshot is None
    assert warnings
    assert any("schema_version mismatch" in item for item in warnings)


def test_load_combo_a_operating_cycle_snapshot_happy_path(tmp_path: Path) -> None:
    summary_path = panel.canonical_combo_a_operating_cycle_source(tmp_path)
    _write_json(
        summary_path,
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
                "services": {
                    "qdrant": {"status": "ok", "configured": True},
                    "neo4j": {"status": "ok", "configured": True},
                },
            },
            "sources": {},
            "paths": {
                "summary_json": str(summary_path),
                "summary_md": str(summary_path.parent / "summary.md"),
            },
        },
    )

    snapshot, warnings = panel.load_combo_a_operating_cycle_snapshot(tmp_path)
    assert warnings == []
    assert snapshot is not None
    assert snapshot["effective_policy"] == "observe_only"
    assert snapshot["promotion_state"] == "hold"
    assert snapshot["availability_status"] == "partial"
    assert snapshot["recommended_actions"][0]["action_key"] == "cross_service_suite_combo_a_smoke"
    assert snapshot["paths"]["summary_json"] == str(summary_path)
