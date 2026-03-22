from __future__ import annotations

import json
from pathlib import Path

import scripts.operator_product_snapshot as operator_snapshot


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
    assert governance["recommended_actions"][0]["action_key"] == "gateway_sla_operating_cycle_smoke"
    assert combo_a["effective_policy"] == "observe_only"
    assert combo_a["promotion_state"] == "hold"
    assert combo_a["operating_cycle_path"] == str(operator_snapshot.canonical_combo_a_operating_cycle_source(runs_dir))
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
