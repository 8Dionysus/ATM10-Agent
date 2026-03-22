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


def test_build_operator_product_snapshot_includes_policy_promotion_surface(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_operating_cycle_summary(runs_dir)

    payload = operator_snapshot.build_operator_product_snapshot(
        runs_dir=runs_dir,
        gateway_health={
            "status": "ok",
            "supported_operations": ["health", "retrieval_query"],
            "supported_profiles": ["baseline_first", "combo_a"],
        },
    )

    governance = payload["operator_context"]["governance"]
    assert governance["effective_gateway_sla_policy"] == "signal_only"
    assert governance["promotion_state"] == "blocked"
    assert governance["profile_scope"] == "baseline_first"
    assert governance["recommended_actions"][0]["action_key"] == "gateway_sla_operating_cycle_smoke"
    assert payload["latest_metrics"]["operating_cycle"]["effective_policy"] == "signal_only"


def test_build_operator_runs_payload_includes_policy_context(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_operating_cycle_summary(runs_dir)

    payload = operator_snapshot.build_operator_runs_payload(runs_dir)

    governance = payload["operator_context"]["governance"]
    operating_cycle = payload["operator_context"]["operating_cycle"]
    assert governance["effective_gateway_sla_policy"] == "signal_only"
    assert governance["promotion_state"] == "blocked"
    assert operating_cycle["profile_scope"] == "baseline_first"
    assert payload["warnings"]["policy_surface"]["operating_cycle"] == []


def test_build_operator_history_payload_includes_policy_context(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_operating_cycle_summary(runs_dir)

    payload = operator_snapshot.build_operator_history_payload(runs_dir)

    governance = payload["operator_context"]["governance"]
    assert governance["effective_gateway_sla_policy"] == "signal_only"
    assert governance["promotion_state"] == "blocked"
    assert payload["operator_warnings"]["policy_surface"]["operating_cycle"] == []
