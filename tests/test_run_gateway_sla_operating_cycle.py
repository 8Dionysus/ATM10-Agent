from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.run_gateway_sla_operating_cycle as operating_cycle


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _summary_path(runs_dir: Path, name: str) -> Path:
    mapping = {
        "readiness": runs_dir / "nightly-gateway-sla-readiness" / "readiness_summary.json",
        "governance": runs_dir / "nightly-gateway-sla-governance" / "governance_summary.json",
        "progress": runs_dir / "nightly-gateway-sla-progress" / "progress_summary.json",
        "transition": runs_dir / "nightly-gateway-sla-transition" / "transition_summary.json",
        "remediation": runs_dir / "nightly-gateway-sla-remediation" / "remediation_summary.json",
        "integrity": runs_dir / "nightly-gateway-sla-integrity" / "integrity_summary.json",
        "cadence": runs_dir / "nightly-gateway-sla-manual-cadence" / "cadence_brief.json",
        "manual_runner": runs_dir / "nightly-gateway-sla-manual-runner" / "manual_nightly_summary.json",
    }
    return mapping[name]


def _readiness_payload(*, checked_at_utc: str) -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_readiness_v1",
        "status": "ok",
        "checked_at_utc": checked_at_utc,
        "readiness_status": "not_ready",
    }


def _governance_payload(*, checked_at_utc: str) -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_governance_v1",
        "status": "ok",
        "checked_at_utc": checked_at_utc,
        "decision_status": "hold",
    }


def _progress_payload(*, checked_at_utc: str, remaining_window: int = 11, remaining_streak: int = 3) -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_progress_v1",
        "status": "ok",
        "checked_at_utc": checked_at_utc,
        "decision_status": "hold",
        "observed": {
            "readiness": {
                "remaining_for_window": remaining_window,
                "remaining_for_streak": remaining_streak,
            }
        },
    }


def _transition_payload(*, checked_at_utc: str) -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_transition_v1",
        "status": "ok",
        "checked_at_utc": checked_at_utc,
        "decision_status": "hold",
        "allow_switch": False,
    }


def _remediation_payload(*, checked_at_utc: str, candidate_ids: list[str] | None = None) -> dict:
    candidate_ids = candidate_ids or ["regression_investigation", "window_accumulation"]
    return {
        "schema_version": "gateway_sla_fail_nightly_remediation_v1",
        "status": "ok",
        "checked_at_utc": checked_at_utc,
        "reason_codes": ["latest_not_ready"],
        "candidate_items": [{"id": item_id, "priority": "medium", "summary": item_id} for item_id in candidate_ids],
    }


def _integrity_payload(
    *,
    checked_at_utc: str,
    integrity_status: str = "clean",
    reason_codes: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "gateway_sla_fail_nightly_integrity_v1",
        "status": "ok",
        "checked_at_utc": checked_at_utc,
        "observed": {
            "invalid_counts": {
                "governance": 0,
                "progress_readiness": 0,
                "progress_governance": 0,
                "transition_aggregated": 0,
            }
        },
        "decision": {
            "integrity_status": integrity_status,
            "reason_codes": reason_codes or [],
        },
    }


def _cadence_payload(
    *,
    checked_at_utc: str,
    attention_state: str = "ready_for_accounted_run",
    decision_status: str = "allow_accounted_dispatch",
    next_dispatch: str | None = None,
) -> dict:
    return {
        "schema_version": "gateway_sla_manual_cadence_brief_v1",
        "status": "ok",
        "checked_at_utc": checked_at_utc,
        "attention_state": attention_state,
        "decision": {
            "decision_status": decision_status,
            "next_accounted_dispatch_at_utc": next_dispatch,
        },
        "forecast": {
            "earliest_go_candidate_at_utc": "2026-03-22T21:53:16+00:00",
        },
    }


def _manual_runner_payload(
    *,
    checked_at_utc: str,
    execution_mode: str = "accounted",
    decision_status: str = "allow_accounted_dispatch",
    next_dispatch: str | None = None,
) -> dict:
    return {
        "schema_version": "gateway_sla_manual_nightly_runner_v1",
        "status": "ok",
        "checked_at_utc": checked_at_utc,
        "execution_mode": execution_mode,
        "decision": {
            "decision_status": decision_status,
            "next_accounted_dispatch_at_utc": next_dispatch,
        },
    }


def test_operating_cycle_reuses_fresh_manual_backed_snapshot(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    manual_checked = "2026-03-12T21:53:15+00:00"
    checked = "2026-03-12T21:53:16+00:00"
    _write_json(_summary_path(runs_dir, "manual_runner"), _manual_runner_payload(checked_at_utc=manual_checked))
    _write_json(_summary_path(runs_dir, "readiness"), _readiness_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "governance"), _governance_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "progress"), _progress_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "transition"), _transition_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "remediation"), _remediation_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "integrity"), _integrity_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "cadence"), _cadence_payload(checked_at_utc=checked))

    result = operating_cycle.run_gateway_sla_operating_cycle(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 12, 22, 2, 55, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["cycle"]["source"] == "manual"
    assert summary["cycle"]["operating_mode"] == "reuse_fresh_latest"
    assert summary["cycle"]["used_manual_fallback"] is False
    assert summary["triage"]["remaining_for_window"] == 11
    assert summary["triage"]["candidate_item_count"] == 2
    assert summary["interpretation"]["telemetry_repair_required"] is False
    assert summary["interpretation"]["remediation_backlog_primary"] is True


def test_operating_cycle_reuses_fresh_nightly_snapshot_without_manual_runner(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    checked = "2026-03-12T03:40:00+00:00"
    _write_json(_summary_path(runs_dir, "readiness"), _readiness_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "governance"), _governance_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "progress"), _progress_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "transition"), _transition_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "remediation"), _remediation_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "integrity"), _integrity_payload(checked_at_utc=checked))

    result = operating_cycle.run_gateway_sla_operating_cycle(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 12, 22, 2, 55, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["cycle"]["source"] == "nightly"
    assert summary["cycle"]["operating_mode"] == "reuse_fresh_latest"
    assert summary["cycle"]["used_manual_fallback"] is False


def test_operating_cycle_runs_manual_fallback_in_fixed_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs"
    stale_checked = "2026-03-11T21:53:16+00:00"
    _write_json(_summary_path(runs_dir, "readiness"), _readiness_payload(checked_at_utc=stale_checked))
    _write_json(_summary_path(runs_dir, "governance"), _governance_payload(checked_at_utc=stale_checked))
    _write_json(_summary_path(runs_dir, "progress"), _progress_payload(checked_at_utc=stale_checked, remaining_window=12))
    _write_json(_summary_path(runs_dir, "transition"), _transition_payload(checked_at_utc=stale_checked))
    _write_json(_summary_path(runs_dir, "remediation"), _remediation_payload(checked_at_utc=stale_checked))
    _write_json(_summary_path(runs_dir, "integrity"), _integrity_payload(checked_at_utc=stale_checked))

    call_order: list[str] = []
    fresh_manual_checked = "2026-03-12T21:53:15+00:00"
    fresh_checked = "2026-03-12T21:53:16+00:00"

    def fake_manual_runner(**_: object) -> dict:
        call_order.append("manual_nightly")
        _write_json(_summary_path(runs_dir, "manual_runner"), _manual_runner_payload(checked_at_utc=fresh_manual_checked))
        _write_json(_summary_path(runs_dir, "readiness"), _readiness_payload(checked_at_utc=fresh_checked))
        _write_json(_summary_path(runs_dir, "governance"), _governance_payload(checked_at_utc=fresh_checked))
        _write_json(_summary_path(runs_dir, "progress"), _progress_payload(checked_at_utc=fresh_checked, remaining_window=11))
        _write_json(_summary_path(runs_dir, "transition"), _transition_payload(checked_at_utc=fresh_checked))
        return {"exit_code": 0}

    def fake_cadence(**_: object) -> dict:
        call_order.append("cadence")
        _write_json(_summary_path(runs_dir, "cadence"), _cadence_payload(checked_at_utc=fresh_checked))
        return {"exit_code": 0}

    def fake_remediation(**_: object) -> dict:
        call_order.append("remediation")
        _write_json(_summary_path(runs_dir, "remediation"), _remediation_payload(checked_at_utc=fresh_checked))
        return {"exit_code": 0}

    def fake_integrity(**_: object) -> dict:
        call_order.append("integrity")
        _write_json(_summary_path(runs_dir, "integrity"), _integrity_payload(checked_at_utc=fresh_checked))
        return {"exit_code": 0}

    monkeypatch.setattr(operating_cycle, "run_gateway_sla_manual_nightly", fake_manual_runner)
    monkeypatch.setattr(operating_cycle, "run_gateway_sla_manual_cadence_brief", fake_cadence)
    monkeypatch.setattr(operating_cycle, "run_gateway_sla_fail_nightly_remediation", fake_remediation)
    monkeypatch.setattr(operating_cycle, "run_gateway_sla_fail_nightly_integrity", fake_integrity)

    result = operating_cycle.run_gateway_sla_operating_cycle(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 12, 22, 2, 55, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert call_order == ["manual_nightly", "cadence", "remediation", "integrity"]
    assert summary["cycle"]["source"] == "manual"
    assert summary["cycle"]["operating_mode"] == "manual_fallback"
    assert summary["cycle"]["used_manual_fallback"] is True
    assert summary["triage"]["remaining_for_window"] == 11


def test_operating_cycle_prioritizes_telemetry_repair_for_integrity_attention(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    manual_checked = "2026-03-12T21:53:15+00:00"
    checked = "2026-03-12T21:53:16+00:00"
    _write_json(_summary_path(runs_dir, "manual_runner"), _manual_runner_payload(checked_at_utc=manual_checked))
    _write_json(_summary_path(runs_dir, "readiness"), _readiness_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "governance"), _governance_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "progress"), _progress_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "transition"), _transition_payload(checked_at_utc=checked))
    _write_json(_summary_path(runs_dir, "remediation"), _remediation_payload(checked_at_utc=checked))
    _write_json(
        _summary_path(runs_dir, "integrity"),
        _integrity_payload(
            checked_at_utc=checked,
            integrity_status="attention",
            reason_codes=["dual_write_invariant_broken"],
        ),
    )
    _write_json(_summary_path(runs_dir, "cadence"), _cadence_payload(checked_at_utc=checked))

    result = operating_cycle.run_gateway_sla_operating_cycle(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 12, 22, 2, 55, tzinfo=timezone.utc),
    )

    interpretation = result["summary_payload"]["interpretation"]
    assert interpretation["telemetry_repair_required"] is True
    assert interpretation["remediation_backlog_primary"] is False
    assert interpretation["next_action_hint"] == "repair_telemetry_first"


def test_operating_cycle_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_gateway_sla_operating_cycle.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        operating_cycle.parse_args()
    assert exc.value.code == 0
