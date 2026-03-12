from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.check_gateway_sla_fail_nightly_integrity as integrity_checker


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _paths(runs_dir: Path) -> dict[str, Path]:
    return {
        "readiness": runs_dir / "nightly-gateway-sla-readiness" / "readiness_summary.json",
        "governance": runs_dir / "nightly-gateway-sla-governance" / "governance_summary.json",
        "progress": runs_dir / "nightly-gateway-sla-progress" / "progress_summary.json",
        "transition": runs_dir / "nightly-gateway-sla-transition" / "transition_summary.json",
        "remediation": runs_dir / "nightly-gateway-sla-remediation" / "remediation_summary.json",
        "manual_cadence": runs_dir / "nightly-gateway-sla-manual-cadence" / "cadence_brief.json",
    }


def _write_summary_with_history(
    latest_path: Path,
    *,
    run_name: str,
    schema_version: str,
    payload: dict,
) -> None:
    run_dir = latest_path.parent / run_name
    run_json_path = run_dir / "run.json"
    history_summary_path = run_dir / latest_path.name
    enriched_payload = {
        "schema_version": schema_version,
        "status": "ok",
        "checked_at_utc": "2026-03-12T08:00:00+00:00",
        **payload,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(latest_path),
            "history_summary_json": str(history_summary_path),
        },
    }
    _write_json(run_json_path, {"mode": run_name, "status": "ok", "paths": {"summary_json": str(latest_path)}})
    _write_json(history_summary_path, enriched_payload)
    _write_json(latest_path, enriched_payload)


def _write_manual_cadence(
    latest_path: Path,
    *,
    attention_state: str = "ready_for_accounted_run",
    accounted_dispatch_allowed: bool = True,
    decision_status: str = "allow_accounted_dispatch",
    next_accounted_dispatch_at_utc: str | None = None,
    reason_codes: list[str] | None = None,
) -> None:
    _write_json(
        latest_path,
        {
            "schema_version": "gateway_sla_manual_cadence_brief_v1",
            "status": "ok",
            "checked_at_utc": "2026-03-12T08:05:00+00:00",
            "attention_state": attention_state,
            "decision": {
                "accounted_dispatch_allowed": accounted_dispatch_allowed,
                "decision_status": decision_status,
                "next_accounted_dispatch_at_utc": next_accounted_dispatch_at_utc,
                "reason_codes": [] if reason_codes is None else reason_codes,
            },
            "paths": {
                "run_dir": str(latest_path.parent / "20260312_080500-gateway-sla-manual-cadence-brief"),
                "run_json": str(
                    latest_path.parent / "20260312_080500-gateway-sla-manual-cadence-brief" / "run.json"
                ),
                "summary_json": str(latest_path),
            },
        },
    )


def _write_required_sources(runs_dir: Path) -> dict[str, Path]:
    p = _paths(runs_dir)
    _write_summary_with_history(
        p["readiness"],
        run_name="20260312_080000-gateway-sla-fail-readiness",
        schema_version="gateway_sla_fail_nightly_readiness_v1",
        payload={
            "readiness_status": "ready",
            "criteria": {
                "readiness_window": 14,
                "required_baseline_count": 5,
                "max_warn_ratio": 0.2,
                "window_observed": 14,
            },
            "window_summary": {"invalid_or_error_count": 0},
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
        },
    )
    _write_summary_with_history(
        p["governance"],
        run_name="20260312_080001-gateway-sla-governance",
        schema_version="gateway_sla_fail_nightly_governance_v1",
        payload={
            "decision_status": "go",
            "criteria": {
                "required_ready_streak": 3,
                "expected_readiness_window": 14,
                "expected_required_baseline_count": 5,
                "expected_max_warn_ratio": 0.2,
                "history_limit": 60,
            },
            "observed": {"latest_ready_streak": 3, "invalid_or_mismatched_count": 0},
            "recommendation": {
                "target_critical_policy": "fail_nightly",
                "switch_surface": "nightly_only",
                "reason_codes": [],
            },
        },
    )
    _write_summary_with_history(
        p["progress"],
        run_name="20260312_080002-gateway-sla-fail-progress",
        schema_version="gateway_sla_fail_nightly_progress_v1",
        payload={
            "decision_status": "go",
            "criteria": {
                "required_ready_streak": 3,
                "expected_readiness_window": 14,
                "expected_required_baseline_count": 5,
                "expected_max_warn_ratio": 0.2,
                "readiness_history_limit": 60,
                "governance_history_limit": 60,
            },
            "observed": {
                "readiness": {
                    "invalid_or_mismatched_count": 0,
                    "remaining_for_window": 0,
                    "remaining_for_streak": 0,
                },
                "governance": {"invalid_or_mismatched_count": 0},
            },
            "recommendation": {"target_critical_policy": "fail_nightly", "reason_codes": []},
        },
    )
    _write_summary_with_history(
        p["transition"],
        run_name="20260312_080003-gateway-sla-transition",
        schema_version="gateway_sla_fail_nightly_transition_v1",
        payload={
            "decision_status": "go",
            "allow_switch": True,
            "criteria": {
                "required_ready_streak": 3,
                "expected_readiness_window": 14,
                "expected_required_baseline_count": 5,
                "expected_max_warn_ratio": 0.2,
                "readiness_history_limit": 60,
                "governance_history_limit": 60,
                "progress_history_limit": 60,
            },
            "observed": {
                "readiness": {"valid_count": 14, "invalid_or_mismatched_count": 0},
                "governance": {"valid_count": 14, "invalid_or_mismatched_count": 0},
                "progress": {"valid_count": 14, "invalid_or_mismatched_count": 0},
                "aggregated": {"invalid_or_mismatched_count": 0, "latest_ready_streak": 3},
            },
            "recommendation": {
                "target_critical_policy": "fail_nightly",
                "switch_surface": "nightly_only",
                "reason_codes": [],
            },
        },
    )
    _write_summary_with_history(
        p["remediation"],
        run_name="20260312_080004-gateway-sla-fail-remediation",
        schema_version="gateway_sla_fail_nightly_remediation_v1",
        payload={
            "policy": "report_only",
            "sources": {},
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
        },
    )
    return p


def test_integrity_happy_path_returns_clean(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _write_required_sources(runs_dir)
    _write_manual_cadence(p["manual_cadence"])

    result = integrity_checker.run_gateway_sla_fail_nightly_integrity(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 12, 8, 10, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["decision"]["integrity_status"] == "clean"
    assert summary["decision"]["reason_codes"] == []
    assert summary["observed"]["telemetry_ok"] is True
    assert summary["observed"]["dual_write_ok"] is True
    assert summary["observed"]["anti_double_count_ok"] is True
    assert summary["observed"]["utc_guardrail_status"] == "ok"
    assert summary["observed"]["invalid_counts"] == {
        "governance": 0,
        "progress_readiness": 0,
        "progress_governance": 0,
        "transition_aggregated": 0,
    }


def test_integrity_telemetry_counter_violation_returns_attention(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _write_required_sources(runs_dir)
    _write_manual_cadence(p["manual_cadence"])

    governance_payload = json.loads(p["governance"].read_text(encoding="utf-8"))
    governance_payload["observed"]["invalid_or_mismatched_count"] = 1
    history_path = Path(governance_payload["paths"]["history_summary_json"])
    _write_json(history_path, governance_payload)
    _write_json(p["governance"], governance_payload)

    result = integrity_checker.run_gateway_sla_fail_nightly_integrity(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 12, 8, 10, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["decision"]["integrity_status"] == "attention"
    assert "telemetry_counters_nonzero" in summary["decision"]["reason_codes"]
    assert summary["observed"]["telemetry_ok"] is False
    assert summary["observed"]["invalid_counts"]["governance"] == 1


def test_integrity_dual_write_history_mismatch_returns_attention(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _write_required_sources(runs_dir)
    _write_manual_cadence(p["manual_cadence"])

    remediation_payload = json.loads(p["remediation"].read_text(encoding="utf-8"))
    history_path = Path(remediation_payload["paths"]["history_summary_json"])
    history_path.unlink()

    result = integrity_checker.run_gateway_sla_fail_nightly_integrity(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 12, 8, 10, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["decision"]["integrity_status"] == "attention"
    assert "dual_write_invariant_broken" in summary["decision"]["reason_codes"]
    assert "anti_double_count_invariant_broken" in summary["decision"]["reason_codes"]
    assert summary["observed"]["dual_write_ok"] is False
    assert summary["observed"]["anti_double_count_ok"] is False


def test_integrity_utc_guardrail_inconsistency_returns_attention(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    p = _write_required_sources(runs_dir)
    _write_manual_cadence(
        p["manual_cadence"],
        attention_state="wait_for_utc_reset",
        accounted_dispatch_allowed=True,
        decision_status="block_accounted_dispatch",
        next_accounted_dispatch_at_utc=None,
        reason_codes=[],
    )

    result = integrity_checker.run_gateway_sla_fail_nightly_integrity(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 12, 8, 10, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]

    assert result["exit_code"] == 0
    assert summary["decision"]["integrity_status"] == "attention"
    assert "utc_guardrail_inconsistent" in summary["decision"]["reason_codes"]
    assert summary["observed"]["utc_guardrail_status"] == "attention"


def test_integrity_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_fail_nightly_integrity.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        integrity_checker.parse_args()
    assert exc.value.code == 0
