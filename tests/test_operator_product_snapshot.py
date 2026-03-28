from __future__ import annotations

import json
from pathlib import Path

import scripts.operator_product_snapshot as operator_snapshot
from src.agent_core.host_profiles import host_profile_payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_operating_cycle_summary(runs_dir: Path) -> Path:
    summary_path = operator_snapshot.canonical_operating_cycle_source(runs_dir)
    _write_json(
        summary_path,
        {
            "schema_version": "gateway_sla_operating_cycle_v1",
            "status": "ok",
            "checked_at_utc": "2026-03-22T18:00:00+00:00",
            "policy": "report_only",
            "effective_policy": "signal_only",
            "promotion_state": "blocked",
            "enforcement_surface": "nightly_only",
            "blocking_reason_codes": ["remediation_backlog_pending"],
            "recommended_actions": [
                {
                    "action_key": "gateway_sla_operating_cycle_smoke",
                    "label": "Gateway SLA operating cycle smoke",
                    "reason": "Refresh the promoted-policy decision surface after the next nightly evidence update.",
                    "surface": "gateway_safe_action",
                }
            ],
            "next_review_at_utc": "2026-03-23T03:35:00+00:00",
            "profile_scope": "baseline_first",
            "actionable_message": "Resolve the remediation backlog before promoting nightly policy.",
            "cycle": {
                "source": "manual",
                "operating_mode": "reuse_fresh_latest",
                "used_manual_fallback": False,
                "manual_execution_mode": "accounted",
                "manual_decision_status": "allow_accounted_dispatch",
                "next_accounted_dispatch_at_utc": "2026-03-23T03:35:00+00:00",
            },
            "triage": {
                "remaining_for_window": 2,
                "remaining_for_streak": 1,
                "transition_allow_switch": False,
                "candidate_item_count": 1,
                "integrity_status": "clean",
                "attention_state": "ready_for_accounted_run",
            },
            "interpretation": {
                "telemetry_repair_required": False,
                "remediation_backlog_primary": True,
                "blocked_manual_gate": False,
                "next_action_hint": "continue_g2_backlog",
            },
            "paths": {
                "summary_json": str(summary_path),
                "history_summary_json": str(summary_path.parent / "20260322_180000-gateway-sla-operating-cycle" / "operating_cycle_summary.json"),
                "brief_md": str(summary_path.parent / "triage_brief.md"),
                "history_brief_md": str(summary_path.parent / "20260322_180000-gateway-sla-operating-cycle" / "triage_brief.md"),
            },
        },
    )
    return summary_path


def _write_clean_operating_cycle_summary(runs_dir: Path) -> Path:
    summary_path = operator_snapshot.canonical_operating_cycle_source(runs_dir)
    _write_json(
        summary_path,
        {
            "schema_version": "gateway_sla_operating_cycle_v1",
            "status": "ok",
            "checked_at_utc": "2026-03-22T18:00:00+00:00",
            "policy": "report_only",
            "effective_policy": "fail_nightly",
            "promotion_state": "eligible",
            "enforcement_surface": "nightly_only",
            "blocking_reason_codes": [],
            "recommended_actions": [],
            "next_review_at_utc": "2026-03-23T03:35:00+00:00",
            "profile_scope": "baseline_first",
            "actionable_message": "Operator surfaces are green.",
            "cycle": {
                "source": "manual",
                "operating_mode": "reuse_fresh_latest",
                "used_manual_fallback": False,
                "manual_execution_mode": "accounted",
                "manual_decision_status": "allow_accounted_dispatch",
                "next_accounted_dispatch_at_utc": "2026-03-23T03:35:00+00:00",
            },
            "triage": {
                "remaining_for_window": 0,
                "remaining_for_streak": 0,
                "transition_allow_switch": True,
                "candidate_item_count": 0,
                "integrity_status": "clean",
                "attention_state": "ready_for_accounted_run",
            },
            "interpretation": {
                "telemetry_repair_required": False,
                "remediation_backlog_primary": False,
                "blocked_manual_gate": False,
                "next_action_hint": "continue",
            },
            "paths": {"summary_json": str(summary_path)},
        },
    )
    return summary_path


def _clean_policy_surface_context() -> tuple[dict[str, object], dict[str, list[str]]]:
    return (
        {
            "progress": {
                "status": "ok",
                "decision_status": "allow",
                "missing_sources": [],
                "reason_codes": [],
                "source_paths": {},
            },
            "transition": {
                "status": "ok",
                "allow_switch": True,
                "recommendation": {
                    "target_critical_policy": "fail_nightly",
                    "reason_codes": [],
                },
            },
            "remediation": {
                "status": "ok",
                "candidate_items": [],
                "reason_codes": [],
            },
            "integrity": {
                "status": "ok",
                "decision": {
                    "integrity_status": "clean",
                    "reason_codes": [],
                },
            },
            "operating_cycle": {
                "status": "ok",
                "effective_policy": "fail_nightly",
                "promotion_state": "eligible",
                "profile_scope": "baseline_first",
                "blocking_reason_codes": [],
                "recommended_actions": [],
                "actionable_message": "Operator surfaces are green.",
            },
            "governance": {
                "schema_version": "gateway_operator_governance_summary_v1",
                "status": "ok",
                "decision_status": "allow",
                "recommended_policy": "fail_nightly",
                "effective_gateway_sla_policy": "fail_nightly",
                "promotion_state": "eligible",
                "enforcement_surface": "nightly_only",
                "blocking_reason_codes": [],
                "recommended_actions": [],
                "next_review_at_utc": "2026-03-23T03:35:00+00:00",
                "profile_scope": "baseline_first",
                "actionable_message": "Operator surfaces are green.",
                "reason_codes": [],
                "next_action_hint": "continue",
                "transition_allow_switch": True,
                "remaining_for_window": 0,
                "remaining_for_streak": 0,
                "candidate_item_count": 0,
                "attention_state": "ready_for_accounted_run",
                "integrity_status": "clean",
                "operating_mode": "reuse_fresh_latest",
                "manual_execution_mode": "accounted",
                "degraded_sources": [],
                "available_sources": [
                    "progress",
                    "transition",
                    "remediation",
                    "integrity",
                    "operating_cycle",
                ],
                "missing_sources": [],
                "source_paths": {},
            },
        },
        {
            "progress": [],
            "transition": [],
            "remediation": [],
            "integrity": [],
            "operating_cycle": [],
        },
    )


def _write_combo_a_operating_cycle_summary(runs_dir: Path) -> Path:
    summary_path = operator_snapshot.canonical_combo_a_operating_cycle_source(runs_dir)
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
                    "label": "Cross-service suite Combo A smoke",
                    "reason": "Refresh the Combo A cross-service suite artifact before the next nightly review.",
                    "surface": "gateway_safe_action",
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
                    "qdrant": {"service_name": "qdrant", "status": "ok", "configured": True},
                    "neo4j": {"service_name": "neo4j", "status": "ok", "configured": True},
                },
            },
            "sources": {},
            "paths": {
                "summary_json": str(summary_path),
                "history_summary_json": str(summary_path.parent / "20260322_181000-combo-a-operating-cycle" / "operating_cycle_summary.json"),
                "summary_md": str(summary_path.parent / "summary.md"),
                "history_summary_md": str(summary_path.parent / "20260322_181000-combo-a-operating-cycle" / "summary.md"),
            },
        },
    )
    return summary_path


def _write_operator_startup_run(
    operator_runs_dir: Path,
    *,
    run_name: str = "20260322_120000-start-operator-product",
    status: str = "running",
    error: str | None = None,
    checkpoint_status: str = "ok",
    checkpoint_message: str | None = None,
    gateway_probe_status: str = "ok",
    gateway_probe_error: str | None = None,
    pilot_runtime_runs_dir: Path | None = None,
    last_return_event: dict[str, object] | None = None,
    return_loop_state: dict[str, object] | None = None,
) -> Path:
    run_dir = operator_runs_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    startup_plan_json = run_dir / "startup_plan.json"
    startup_plan_json.write_text("{}", encoding="utf-8")
    run_json_path = run_dir / "run.json"
    _write_json(
        run_json_path,
        {
            "schema_version": "operator_product_startup_v1",
            "mode": "start_operator_product",
            "status": status,
            "profile": "operator_product_core",
            "host_profile": host_profile_payload("ov_intel_core_ultra_local"),
            "timestamp_utc": "2026-03-22T12:00:00+00:00",
            "gateway_url": "http://127.0.0.1:8770",
            "streamlit_url": "http://127.0.0.1:8501",
            "error": error,
            "artifact_roots": {
                "operator_runs_dir": str(operator_runs_dir),
                "pilot_runtime_runs_dir": None if pilot_runtime_runs_dir is None else str(pilot_runtime_runs_dir),
            },
            "paths": {
                "run_json": str(run_json_path),
                "startup_plan_json": str(startup_plan_json),
                "gateway_log": str(run_dir / "gateway.log"),
                "streamlit_log": str(run_dir / "streamlit.log"),
                "pilot_runtime_log": str(run_dir / "pilot_runtime.log"),
                "latest_return_event_json": str(run_dir / "return" / "latest_return_event.json"),
                "return_events_jsonl": str(run_dir / "return" / "return_events.jsonl"),
            },
            "session_state": {
                "gateway": {
                    "service_name": "gateway",
                    "managed": True,
                    "configured": True,
                    "effective_url": "http://127.0.0.1:8770",
                    "status": "running",
                    "pid": 4321,
                    "last_probe": {
                        "status": gateway_probe_status,
                        "error": gateway_probe_error,
                    },
                },
                **(
                    {
                        "pilot_runtime": {
                            "service_name": "pilot_runtime",
                            "managed": True,
                            "configured": True,
                            "effective_url": None,
                            "runs_dir": str(pilot_runtime_runs_dir),
                            "status": "running",
                            "pid": 5432,
                            "last_probe": {"status": "ok"},
                        }
                    }
                    if pilot_runtime_runs_dir is not None
                    else {}
                ),
            },
            "child_processes": {
                "gateway": {"pid": 4321, "return_code": None},
                **({"pilot_runtime": {"pid": 5432, "return_code": None}} if pilot_runtime_runs_dir is not None else {}),
            },
            "startup_checkpoints": [
                {
                    "stage": "probe",
                    "status": checkpoint_status,
                    "message": checkpoint_message,
                }
            ],
            "last_checkpoint": {
                "stage": "probe",
                "status": checkpoint_status,
                "message": checkpoint_message,
            },
            "last_return_event": last_return_event,
            "return_loop_state": return_loop_state,
        },
    )
    if last_return_event is not None:
        return_dir = run_dir / "return"
        return_dir.mkdir(parents=True, exist_ok=True)
        _write_json(return_dir / "latest_return_event.json", last_return_event)
        (return_dir / "return_events.jsonl").write_text(
            json.dumps(last_return_event, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return run_json_path


def _write_pilot_runtime_status(
    pilot_runs_dir: Path,
    *,
    last_return_event: dict[str, object] | None = None,
    return_loop_state: dict[str, object] | None = None,
) -> None:
    pilot_runs_dir.mkdir(parents=True, exist_ok=True)
    turn_dir = pilot_runs_dir / "20260322_120500-pilot-runtime" / "turns" / "20260322_120501-pilot-turn"
    turn_dir.mkdir(parents=True, exist_ok=True)
    turn_json = turn_dir / "pilot_turn.json"
    session_probe_json = turn_dir / "session_probe.json"
    live_hud_state_json = turn_dir / "live_hud_state.json"
    _write_json(
        session_probe_json,
        {
            "schema_version": "atm10_session_probe_v1",
            "checked_at_utc": "2026-03-22T12:05:02+00:00",
            "status": "ok",
            "window_found": True,
            "process_name": "javaw.exe",
            "window_title": "Minecraft 1.21.1 - ATM10",
            "foreground": True,
            "window_bounds": {
                "left": 0,
                "top": 0,
                "right": 320,
                "bottom": 180,
                "width": 320,
                "height": 180,
            },
            "capture_target_kind": "monitor",
            "atm10_probable": True,
            "reason_codes": [],
        },
    )
    _write_json(
        live_hud_state_json,
        {
            "schema_version": "live_hud_state_v1",
            "checked_at_utc": "2026-03-22T12:05:02+00:00",
            "status": "partial",
            "sources": {
                "screenshot": {"status": "ok", "path": str(turn_dir / "screenshot.png")},
                "mod_hook": {"status": "not_configured", "path": None},
                "ocr": {"status": "unavailable", "path": None},
            },
            "hud_lines": ["Quest book", "Collect 16 wood"],
            "quest_updates": [{"id": "quest:start", "text": "Collect 16 wood"}],
            "player_state": {"dimension": "minecraft:overworld"},
            "context_tags": ["hud", "quest"],
            "text_preview": "Quest book Collect 16 wood",
            "hud_line_count": 2,
            "quest_update_count": 1,
            "has_player_state": True,
            "reason_codes": ["ocr_unavailable", "mod_hook_not_configured"],
        },
    )
    _write_json(
        turn_json,
        {
            "schema_version": "pilot_turn_v1",
            "turn_id": "20260322_120501-pilot-turn",
            "status": "degraded",
            "timestamp_utc": "2026-03-22T12:05:01+00:00",
            "completed_at_utc": "2026-03-22T12:05:03+00:00",
            "degraded_flags": ["retrieval_only_fallback"],
            "degraded_services": ["gateway"],
            "answer_language": "ru",
            "reply_mode": "visual_only_fallback",
            "transcript_quality": {
                "status": "low_signal",
                "reason_codes": ["short_ascii_when_russian_expected"],
                "expected_language": "ru",
                "detected_language": "en",
                "transcript_used": False,
            },
            "session": {
                "status": "ok",
                "window_found": True,
                "atm10_probable": True,
                "foreground": True,
                "process_name": "javaw.exe",
                "window_title": "Minecraft 1.21.1 - ATM10",
                "reason_codes": [],
            },
            "hud_state": {
                "status": "partial",
                "hud_line_count": 2,
                "quest_update_count": 1,
                "has_player_state": True,
                "text_preview": "Quest book Collect 16 wood",
                "reason_codes": ["ocr_unavailable", "mod_hook_not_configured"],
            },
            "vision": {
                "provider": "openvino_genai_vlm_v1",
                "model": "qwen2.5-vl-7b-instruct-int4-ov",
            },
            "grounded_reply": {
                "provider": "openvino_genai_grounded_reply_v1",
                "model": "qwen3-8b-int4-cw-ov",
                "answer_language": "ru",
            },
            "tts": {
                "status": "ok",
                "chunk_engines": ["windows_sapi_fallback"],
            },
            "answer_text": "Pilot degraded mode (retrieval_only_fallback). Quest book is the next step.",
            "paths": {
                "turn_json": str(turn_json),
                "screenshot_png": str(turn_dir / "screenshot.png"),
                "tts_audio_wav": str(turn_dir / "tts_audio_out.wav"),
                "session_probe_json": str(session_probe_json),
                "live_hud_state_json": str(live_hud_state_json),
            },
        },
    )
    _write_json(
        pilot_runs_dir / "pilot_runtime_status_latest.json",
        {
            "schema_version": "pilot_runtime_status_v1",
            "status": "running",
            "state": "idle",
            "hotkey": "F8",
            "host_profile": host_profile_payload("ov_intel_core_ultra_local"),
            "effective_config": {
                "host_profile_id": "ov_intel_core_ultra_local",
                "input_device_index": 1,
                "asr_language": "ru",
                "asr_max_new_tokens": 64,
                "asr_warmup": {"requested": True},
                "vlm_provider": "openvino",
                "text_provider": "openvino",
                "pilot_vlm_max_new_tokens": 64,
                "pilot_text_max_new_tokens": 96,
                "pilot_hybrid_timeout_sec": 1.5,
            },
            "provider_init": {
                "vlm": {"status": "ok", "provider": "openvino", "warmup": {"requested": True, "ok": True}},
                "text": {"status": "ok", "provider": "openvino", "warmup": {"requested": True, "ok": True}},
            },
            "last_turn_id": "20260322_120501-pilot-turn",
            "last_turn_started_at_utc": "2026-03-22T12:05:01+00:00",
            "last_turn_completed_at_utc": "2026-03-22T12:05:03+00:00",
            "degraded_services": ["gateway"],
            "last_return_event": last_return_event,
            "return_loop_state": return_loop_state,
            "last_error": None,
            "latency_summary": {"total_sec": 2.1},
            "paths": {
                "run_dir": str(pilot_runs_dir / "20260322_120500-pilot-runtime"),
                "status_json": str(pilot_runs_dir / "20260322_120500-pilot-runtime" / "pilot_runtime_status.json"),
                "latest_status_json": str(pilot_runs_dir / "pilot_runtime_status_latest.json"),
                "last_turn_json": str(turn_json),
                "latest_return_event_json": str(pilot_runs_dir / "return" / "latest_return_event.json"),
                "return_events_jsonl": str(pilot_runs_dir / "return" / "return_events.jsonl"),
            },
        },
    )
    if last_return_event is not None:
        return_dir = pilot_runs_dir / "return"
        return_dir.mkdir(parents=True, exist_ok=True)
        _write_json(return_dir / "latest_return_event.json", last_return_event)
        (return_dir / "return_events.jsonl").write_text(
            json.dumps(last_return_event, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _write_pilot_runtime_readiness_summary(
    runs_dir: Path,
    *,
    readiness_status: str = "attention",
    schema_version: str = "pilot_runtime_readiness_v1",
) -> Path:
    summary_path = operator_snapshot.canonical_pilot_runtime_readiness_source(runs_dir)
    _write_json(
        summary_path,
        {
            "schema_version": schema_version,
            "status": "ok",
            "checked_at_utc": "2026-03-22T12:06:00+00:00",
            "readiness_status": readiness_status,
            "actionable_message": "Pilot readiness summary for tests.",
            "blocking_reason_codes": ["pilot_turn_degraded"] if readiness_status != "ready" else [],
            "next_step_code": "repeat_live_pilot_turn" if readiness_status != "ready" else "none",
            "next_step": "Complete one live push-to-talk turn.",
            "sources": {
                "startup": {"status": "present", "fresh_within_window": True},
                "pilot_runtime_status": {"status": "present", "fresh_within_window": True},
                "pilot_turn": {"status": "present", "fresh_within_window": readiness_status == "ready"},
            },
            "evidence": {
                "last_turn_fresh_within_window": readiness_status == "ready",
                "live_turn_evidence": readiness_status == "ready",
                "session_window_found": True,
                "session_atm10_probable": True,
                "session_foreground": True,
                "hud_state_status": "partial" if readiness_status != "blocked" else "error",
            },
            "paths": {
                "summary_json": str(summary_path),
                "history_summary_json": str(summary_path.parent / "20260322_120600-pilot-runtime-readiness" / "readiness_summary.json"),
                "summary_md": str(summary_path.parent / "summary.md"),
                "history_summary_md": str(summary_path.parent / "20260322_120600-pilot-runtime-readiness" / "summary.md"),
            },
        },
    )
    return summary_path


def test_build_operator_product_snapshot_includes_policy_promotion_surface(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_operating_cycle_summary(runs_dir)
    _write_combo_a_operating_cycle_summary(runs_dir)

    payload = operator_snapshot.build_operator_product_snapshot(
        runs_dir=runs_dir,
        gateway_health={
            "status": "ok",
            "supported_operations": ["health", "retrieval_query"],
            "supported_profiles": ["baseline_first", "combo_a"],
        },
    )

    governance = payload["operator_context"]["governance"]
    combo_a = payload["operator_context"]["profiles"]["combo_a"]
    assert governance["effective_gateway_sla_policy"] == "signal_only"
    assert governance["promotion_state"] == "blocked"
    assert governance["profile_scope"] == "baseline_first"
    assert governance["diagnostics"]["top_blocker"] == "remediation_backlog_pending"
    assert governance["diagnostics"]["next_safe_action"] == "gateway_sla_operating_cycle_smoke"
    assert governance["recommended_actions"][0]["action_key"] == "gateway_sla_operating_cycle_smoke"
    assert combo_a["effective_policy"] == "observe_only"
    assert combo_a["promotion_state"] == "hold"
    assert combo_a["operating_cycle_path"] == str(operator_snapshot.canonical_combo_a_operating_cycle_source(runs_dir))
    assert payload["operator_context"]["triage"]["primary_surface"] == "startup"
    assert payload["operator_context"]["triage"]["primary_code"] == "launch_operator_product"
    assert payload["operator_context"]["triage"]["next_safe_action"] == "gateway_sla_operating_cycle_smoke"
    assert payload["latest_metrics"]["operating_cycle"]["effective_policy"] == "signal_only"
    assert payload["latest_metrics"]["combo_a_operating_cycle"]["effective_policy"] == "observe_only"


def test_build_operator_runs_payload_includes_policy_context(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_operating_cycle_summary(runs_dir)
    _write_combo_a_operating_cycle_summary(runs_dir)

    payload = operator_snapshot.build_operator_runs_payload(runs_dir)

    governance = payload["operator_context"]["governance"]
    operating_cycle = payload["operator_context"]["operating_cycle"]
    combo_a = payload["operator_context"]["profiles"]["combo_a"]
    assert governance["effective_gateway_sla_policy"] == "signal_only"
    assert governance["promotion_state"] == "blocked"
    assert governance["diagnostics"]["top_blocker"] == "remediation_backlog_pending"
    assert governance["diagnostics"]["next_safe_action"] == "gateway_sla_operating_cycle_smoke"
    assert operating_cycle["profile_scope"] == "baseline_first"
    assert payload["warnings"]["policy_surface"]["operating_cycle"] == []
    assert payload["warnings"]["policy_surface"]["combo_a_operating_cycle"] == []
    assert combo_a["effective_policy"] == "observe_only"
    assert combo_a["promotion_state"] == "hold"


def test_build_operator_history_payload_includes_policy_context(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_operating_cycle_summary(runs_dir)
    _write_combo_a_operating_cycle_summary(runs_dir)

    payload = operator_snapshot.build_operator_history_payload(runs_dir)

    governance = payload["operator_context"]["governance"]
    combo_a = payload["operator_context"]["profiles"]["combo_a"]
    assert governance["effective_gateway_sla_policy"] == "signal_only"
    assert governance["promotion_state"] == "blocked"
    assert governance["diagnostics"]["top_blocker"] == "remediation_backlog_pending"
    assert governance["diagnostics"]["next_safe_action"] == "gateway_sla_operating_cycle_smoke"
    assert payload["operator_warnings"]["policy_surface"]["operating_cycle"] == []
    assert payload["operator_warnings"]["policy_surface"]["combo_a_operating_cycle"] == []
    assert combo_a["effective_policy"] == "observe_only"
    assert combo_a["promotion_state"] == "hold"


def test_parse_history_row_prefers_run_local_cross_service_history_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "ci-smoke-cross-service-suite" / "20260322_181500-cross-service-benchmark-suite"
    run_dir.mkdir(parents=True, exist_ok=True)
    shared_summary_path = tmp_path / "runs" / "ci-smoke-cross-service-suite" / "cross_service_benchmark_suite.json"
    history_summary_path = run_dir / "cross_service_benchmark_suite.json"
    _write_json(
        shared_summary_path,
        {
            "overall_sla_status": "shared-latest",
            "services": {"gateway": {}, "voice": {}, "tts": {}},
            "degraded_services": ["gateway", "voice"],
        },
    )
    _write_json(
        history_summary_path,
        {
            "overall_sla_status": "run-local",
            "services": {"gateway": {}, "voice": {}},
            "degraded_services": ["voice"],
        },
    )
    _write_json(
        run_dir / "run.json",
        {
            "timestamp_utc": "2026-03-22T18:15:00+00:00",
            "mode": "cross_service_benchmark_suite",
            "status": "ok",
            "paths": {
                "summary_json": str(shared_summary_path),
                "history_summary_json": str(history_summary_path),
            },
        },
    )

    row, warning = operator_snapshot._parse_history_row("cross_service_suite", run_dir)

    assert warning is None
    assert row is not None
    assert row["details"] == "run-local"
    assert row["request_count"] == 2
    assert row["failed_requests_count"] == 1
    assert row["summary_json"] == str(history_summary_path)


def test_build_operator_product_snapshot_includes_startup_diagnostics_healthy(
    tmp_path: Path, monkeypatch
) -> None:
    runs_dir = tmp_path / "runs"
    _write_clean_operating_cycle_summary(runs_dir)
    monkeypatch.setattr(
        operator_snapshot,
        "load_operator_policy_surface_context",
        lambda _runs_dir: _clean_policy_surface_context(),
    )
    operator_runs_dir = tmp_path / "operator-runs"
    _write_operator_startup_run(
        operator_runs_dir,
        status="running",
        checkpoint_status="ok",
        gateway_probe_status="ok",
    )

    payload = operator_snapshot.build_operator_product_snapshot(
        runs_dir=runs_dir,
        operator_runs_dir=operator_runs_dir,
        gateway_health={
            "status": "ok",
            "supported_operations": ["health"],
            "supported_profiles": ["baseline_first", "combo_a"],
        },
    )

    startup = payload["operator_context"]["startup"]
    triage = payload["operator_context"]["triage"]
    assert startup["status"] == "running"
    assert startup["diagnostics"]["overall_state"] == "healthy"
    assert startup["diagnostics"]["primary_issue"] is None
    assert payload["operator_context"]["returning"] is None
    assert triage["overall_state"] == "healthy"
    assert triage["primary_surface"] == "none"
    assert triage["primary_code"] == "none"
    assert triage["next_safe_action"] is None
    assert triage["stack_rollup"]["total_services"] == 5
    assert triage["stack_rollup"]["healthy_services"] == 1
    assert triage["stack_rollup"]["not_configured_services"] == 4


def test_build_operator_product_snapshot_startup_diagnostics_prioritize_snapshot_error(
    tmp_path: Path, monkeypatch
) -> None:
    runs_dir = tmp_path / "runs"
    _write_clean_operating_cycle_summary(runs_dir)
    monkeypatch.setattr(
        operator_snapshot,
        "load_operator_policy_surface_context",
        lambda _runs_dir: _clean_policy_surface_context(),
    )
    operator_runs_dir = tmp_path / "operator-runs"
    _write_operator_startup_run(
        operator_runs_dir,
        status="error",
        error="gateway boot failed",
        checkpoint_status="error",
        checkpoint_message="snapshot probe failed",
        gateway_probe_status="error",
        gateway_probe_error="connection refused",
    )

    payload = operator_snapshot.build_operator_product_snapshot(
        runs_dir=runs_dir,
        operator_runs_dir=operator_runs_dir,
        gateway_health={
            "status": "ok",
            "supported_operations": ["health"],
            "supported_profiles": ["baseline_first", "combo_a"],
        },
    )

    startup = payload["operator_context"]["startup"]
    triage = payload["operator_context"]["triage"]
    assert startup["diagnostics"]["overall_state"] == "degraded"
    assert startup["diagnostics"]["primary_issue"] == "gateway boot failed"
    assert triage["overall_state"] == "attention"
    assert triage["primary_surface"] == "startup"
    assert triage["primary_message"] == "gateway boot failed"
    assert triage["primary_code"] == "inspect_managed_service"


def test_build_operator_product_snapshot_includes_pilot_runtime_context(
    tmp_path: Path, monkeypatch
) -> None:
    runs_dir = tmp_path / "runs"
    _write_clean_operating_cycle_summary(runs_dir)
    _write_pilot_runtime_readiness_summary(runs_dir, readiness_status="attention")
    monkeypatch.setattr(
        operator_snapshot,
        "load_operator_policy_surface_context",
        lambda _runs_dir: _clean_policy_surface_context(),
    )
    monkeypatch.setattr(
        operator_snapshot,
        "fetch_service_health",
        lambda *, service_name, service_url, timeout_sec, service_token=None: (
            {
                "service_name": service_name,
                "configured": service_name == "tts_runtime_service",
                "status": "ok" if service_name == "tts_runtime_service" else "not_configured",
                "url": service_url,
                "health_path": "/health",
                "payload": (
                    {
                        "status": "ok",
                        "preferred_tts_engine": "piper",
                        "piper_available": True,
                        "piper_prewarm_ok": True,
                        "tts_degraded_reason": None,
                    }
                    if service_name == "tts_runtime_service"
                    else None
                ),
                "error": None,
            }
        ),
    )
    operator_runs_dir = tmp_path / "operator-runs"
    pilot_runs_dir = tmp_path / "pilot-runtime"
    _write_pilot_runtime_status(pilot_runs_dir)
    _write_operator_startup_run(
        operator_runs_dir,
        status="running",
        checkpoint_status="ok",
        gateway_probe_status="ok",
        pilot_runtime_runs_dir=pilot_runs_dir,
    )

    payload = operator_snapshot.build_operator_product_snapshot(
        runs_dir=runs_dir,
        operator_runs_dir=operator_runs_dir,
        gateway_health={
            "status": "ok",
            "supported_operations": ["health"],
            "supported_profiles": ["baseline_first", "combo_a"],
        },
        tts_service_url="http://127.0.0.1:8780",
    )

    pilot_runtime = payload["operator_context"]["pilot_runtime"]
    pilot_readiness = payload["operator_context"]["pilot_readiness"]
    last_turn_summary = payload["operator_context"]["last_turn_summary"]
    assert pilot_runtime["status"] == "running"
    assert pilot_runtime["state"] == "idle"
    assert pilot_runtime["host_profile"]["id"] == "ov_intel_core_ultra_local"
    assert pilot_runtime["hotkey"] == "F8"
    assert pilot_runtime["input_device_index"] == 1
    assert pilot_runtime["asr_language"] == "ru"
    assert pilot_runtime["asr_max_new_tokens"] == 64
    assert pilot_runtime["vlm_provider"] == "openvino"
    assert pilot_runtime["text_provider"] == "openvino"
    assert pilot_runtime["pilot_vlm_max_new_tokens"] == 64
    assert pilot_runtime["pilot_text_max_new_tokens"] == 96
    assert pilot_runtime["pilot_hybrid_timeout_sec"] == 1.5
    assert pilot_runtime["provider_init"]["vlm"]["status"] == "ok"
    assert pilot_runtime["provider_init"]["vlm"]["warmup"]["ok"] is True
    assert pilot_runtime["preferred_tts_engine"] == "piper"
    assert pilot_runtime["active_tts_engine_last_turn"] == "windows_sapi_fallback"
    assert pilot_runtime["piper_available"] is True
    assert pilot_runtime["piper_prewarm_ok"] is True
    assert (
        pilot_runtime["tts_degraded_reason"]
        == "last_turn_used_windows_sapi_fallback_instead_of_piper"
    )
    assert pilot_runtime["last_turn_id"] == "20260322_120501-pilot-turn"
    assert pilot_runtime["paths"]["pilot_runs_dir"] == str(pilot_runs_dir)
    assert pilot_readiness["readiness_status"] == "attention"
    assert pilot_readiness["next_step_code"] == "repeat_live_pilot_turn"
    assert last_turn_summary["turn_id"] == "20260322_120501-pilot-turn"
    assert last_turn_summary["answer_language"] == "ru"
    assert last_turn_summary["reply_mode"] == "visual_only_fallback"
    assert last_turn_summary["transcript_quality_status"] == "low_signal"
    assert "short_ascii_when_russian_expected" in last_turn_summary["transcript_quality_reason_codes"]
    assert last_turn_summary["vision_provider"] == "openvino_genai_vlm_v1"
    assert last_turn_summary["grounded_reply_provider"] == "openvino_genai_grounded_reply_v1"
    assert last_turn_summary["tts_engine"] == "windows_sapi_fallback"
    assert last_turn_summary["preferred_tts_engine"] == "piper"
    assert last_turn_summary["piper_available"] is True
    assert last_turn_summary["piper_prewarm_ok"] is True
    assert (
        last_turn_summary["tts_degraded_reason"]
        == "last_turn_used_windows_sapi_fallback_instead_of_piper"
    )
    assert last_turn_summary["session_atm10_probable"] is True
    assert last_turn_summary["session_foreground"] is True
    assert last_turn_summary["hud_state_status"] == "partial"
    assert last_turn_summary["quest_update_count"] == 1
    assert "Quest book is the next step" in last_turn_summary["answer_preview"]
    assert payload["warnings"]["pilot_runtime"] == []
    assert payload["warnings"]["pilot_readiness"] == []
    assert payload["operator_context"]["startup"]["host_profile"]["id"] == "ov_intel_core_ultra_local"


def test_build_operator_product_snapshot_includes_returning_surface(
    tmp_path: Path, monkeypatch
) -> None:
    runs_dir = tmp_path / "runs"
    _write_clean_operating_cycle_summary(runs_dir)
    monkeypatch.setattr(
        operator_snapshot,
        "load_operator_policy_surface_context",
        lambda _runs_dir: _clean_policy_surface_context(),
    )
    operator_runs_dir = tmp_path / "operator-runs"
    startup_return_event = {
        "schema_version": "gateway_operator_return_event_v1",
        "event_id": "return-abc123",
        "timestamp_utc": "2026-03-22T12:00:30+00:00",
        "status": "open",
        "surface": "gateway",
        "reason_code": "gateway_snapshot_not_ready",
        "severity": "attention",
        "return_mode": "reprobe",
        "operator_visible": True,
        "anchor_refs": [
            {
                "artifact_kind": "startup_run",
                "label": "latest startup run",
                "ref_type": "path",
                "required": True,
                "ref": str(operator_runs_dir / "20260322_120000-start-operator-product" / "run.json"),
            }
        ],
        "recommended_safe_actions": ["gateway_http_core"],
        "triage_hint": "Re-probe the gateway operator snapshot and inspect the latest startup artifacts.",
        "loop_count": 1,
        "safe_stop_after": 2,
        "details": {"probe_error": "gateway operator snapshot not ready"},
    }
    _write_operator_startup_run(
        operator_runs_dir,
        status="error",
        checkpoint_status="error",
        checkpoint_message="gateway operator snapshot not ready",
        gateway_probe_status="error",
        gateway_probe_error="gateway operator snapshot not ready",
        last_return_event=startup_return_event,
        return_loop_state={
            "last_reason_code": "gateway_snapshot_not_ready",
            "occurrence_count": 1,
            "emitted_count": 1,
            "safe_stop_after": 2,
            "suppress_first_occurrence": False,
        },
    )

    payload = operator_snapshot.build_operator_product_snapshot(
        runs_dir=runs_dir,
        operator_runs_dir=operator_runs_dir,
        gateway_health={
            "status": "ok",
            "supported_operations": ["health"],
            "supported_profiles": ["baseline_first", "combo_a"],
        },
    )

    returning = payload["operator_context"]["returning"]
    assert returning is not None
    assert returning["schema_version"] == "gateway_operator_return_summary_v1"
    assert returning["status"] == "attention"
    assert returning["open_event_count"] == 1
    assert returning["latest_event"]["reason_code"] == "gateway_snapshot_not_ready"
    assert returning["recommended_safe_actions"] == ["gateway_http_core"]
    assert returning["next_step_code"] == "run_safe_action"
    assert returning["paths"]["latest_return_event_json"].endswith("latest_return_event.json")


def test_build_operator_product_snapshot_tolerates_invalid_pilot_readiness_summary(
    tmp_path: Path, monkeypatch
) -> None:
    runs_dir = tmp_path / "runs"
    _write_clean_operating_cycle_summary(runs_dir)
    _write_pilot_runtime_readiness_summary(runs_dir, schema_version="wrong_pilot_runtime_readiness_v1")
    monkeypatch.setattr(
        operator_snapshot,
        "load_operator_policy_surface_context",
        lambda _runs_dir: _clean_policy_surface_context(),
    )

    payload = operator_snapshot.build_operator_product_snapshot(
        runs_dir=runs_dir,
        gateway_health={
            "status": "ok",
            "supported_operations": ["health"],
            "supported_profiles": ["baseline_first", "combo_a"],
        },
    )

    assert payload["operator_context"]["pilot_readiness"] is None
    assert payload["warnings"]["pilot_readiness"]
    assert any("schema_version mismatch" in item for item in payload["warnings"]["pilot_readiness"])


def test_build_operator_product_snapshot_triage_prioritizes_governance_after_healthy_startup(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    _write_operating_cycle_summary(runs_dir)
    operator_runs_dir = tmp_path / "operator-runs"
    _write_operator_startup_run(
        operator_runs_dir,
        status="running",
        checkpoint_status="ok",
        gateway_probe_status="ok",
    )

    payload = operator_snapshot.build_operator_product_snapshot(
        runs_dir=runs_dir,
        operator_runs_dir=operator_runs_dir,
        gateway_health={
            "status": "ok",
            "supported_operations": ["health"],
            "supported_profiles": ["baseline_first", "combo_a"],
        },
    )

    triage = payload["operator_context"]["triage"]
    assert triage["overall_state"] == "attention"
    assert triage["primary_surface"] == "governance"
    assert triage["primary_code"] == "remediation_backlog_pending"
    assert triage["next_safe_action"] == "gateway_sla_operating_cycle_smoke"
    assert (
        triage["primary_message"]
        == "Resolve the remediation backlog before promoting nightly policy."
    )


def test_build_operator_product_snapshot_triage_prioritizes_service_probe_errors(
    tmp_path: Path, monkeypatch
) -> None:
    runs_dir = tmp_path / "runs"
    _write_clean_operating_cycle_summary(runs_dir)
    monkeypatch.setattr(
        operator_snapshot,
        "load_operator_policy_surface_context",
        lambda _runs_dir: _clean_policy_surface_context(),
    )
    operator_runs_dir = tmp_path / "operator-runs"
    _write_operator_startup_run(
        operator_runs_dir,
        status="running",
        checkpoint_status="ok",
        gateway_probe_status="ok",
    )

    def _fake_fetch_service_health(*, service_name: str, service_url: str | None, **_kwargs):
        if service_name == "voice_runtime_service":
            return {
                "service_name": service_name,
                "configured": True,
                "status": "error",
                "url": str(service_url),
                "health_path": "/health",
                "payload": None,
                "error": "connection refused",
            }
        return {
            "service_name": service_name,
            "configured": False,
            "status": "not_configured",
            "url": None,
            "health_path": "/health",
            "payload": None,
            "error": None,
        }

    monkeypatch.setattr(operator_snapshot, "fetch_service_health", _fake_fetch_service_health)
    monkeypatch.setattr(
        operator_snapshot,
        "probe_qdrant_service",
        lambda **_kwargs: {
            "service_name": "qdrant",
            "configured": False,
            "status": "not_configured",
            "url": None,
            "health_path": "/collections",
            "payload": None,
            "error": None,
        },
    )
    monkeypatch.setattr(
        operator_snapshot,
        "probe_neo4j_service",
        lambda **_kwargs: {
            "service_name": "neo4j",
            "configured": False,
            "status": "not_configured",
            "url": None,
            "health_path": "/",
            "payload": None,
            "error": None,
        },
    )

    payload = operator_snapshot.build_operator_product_snapshot(
        runs_dir=runs_dir,
        operator_runs_dir=operator_runs_dir,
        gateway_health={
            "status": "ok",
            "supported_operations": ["health"],
            "supported_profiles": ["baseline_first", "combo_a"],
        },
        voice_service_url="http://127.0.0.1:8765",
    )

    triage = payload["operator_context"]["triage"]
    assert triage["overall_state"] == "attention"
    assert triage["primary_surface"] == "services"
    assert triage["primary_code"] == "service_attention"
    assert triage["primary_message"] == "voice_runtime_service: connection refused"
    assert triage["next_step_code"] == "inspect_stack_service"
    assert triage["attention_services"] == ["voice_runtime_service"]
    assert triage["stack_rollup"]["configured_services"] == 2
    assert triage["stack_rollup"]["attention_services"] == 1


def test_build_operator_runs_payload_governance_diagnostics_missing_source_fallback(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    summary_path = operator_snapshot.canonical_operating_cycle_source(runs_dir)
    _write_json(
        summary_path,
        {
            "schema_version": "gateway_sla_operating_cycle_v1",
            "status": "ok",
            "checked_at_utc": "2026-03-22T18:00:00+00:00",
            "policy": "report_only",
            "effective_policy": "signal_only",
            "promotion_state": "hold",
            "enforcement_surface": "nightly_only",
            "blocking_reason_codes": [],
            "recommended_actions": [],
            "next_review_at_utc": "2026-03-23T03:35:00+00:00",
            "profile_scope": "baseline_first",
            "actionable_message": "Awaiting required sources.",
            "triage": {
                "remaining_for_window": 0,
                "remaining_for_streak": 0,
                "transition_allow_switch": False,
                "candidate_item_count": 0,
                "integrity_status": "clean",
                "attention_state": "ready_for_accounted_run",
            },
            "interpretation": {
                "telemetry_repair_required": False,
                "remediation_backlog_primary": False,
                "blocked_manual_gate": False,
                "next_action_hint": "wait_for_sources",
            },
            "paths": {"summary_json": str(summary_path)},
        },
    )

    payload = operator_snapshot.build_operator_runs_payload(runs_dir)
    governance = payload["operator_context"]["governance"]
    assert governance["status"] == "degraded"
    assert governance["diagnostics"]["top_blocker"] == "required_sources_not_fresh"
    assert governance["diagnostics"]["next_safe_action"] == "gateway_sla_operating_cycle_smoke"
