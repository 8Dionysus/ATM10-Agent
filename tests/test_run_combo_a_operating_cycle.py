from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import scripts.run_combo_a_operating_cycle as combo_a_cycle


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _gateway_summary(*, finished_at_utc: str, surface: str, status: str = "ok") -> dict:
    return {
        "profile": "combo_a",
        "surface": surface,
        "scenario": "combo_a",
        "status": status,
        "ok": status == "ok",
        "finished_at_utc": finished_at_utc,
        "request_count": 4,
        "failed_requests_count": 0 if status == "ok" else 1,
    }


def _suite_summary(
    *,
    checked_at_utc: str,
    status: str = "ok",
    overall_sla_status: str = "pass",
    degraded_services: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "cross_service_benchmark_suite_v1",
        "checked_at_utc": checked_at_utc,
        "profile": "combo_a",
        "status": status,
        "overall_sla_status": overall_sla_status,
        "degraded_services": degraded_services or [],
        "services": {},
        "summary_matrix": [],
    }


def _healthz_payload(*, timestamp_utc: str, status: str = "ok") -> dict:
    return {
        "timestamp_utc": timestamp_utc,
        "status": status,
        "supported_profiles": ["baseline_first", "combo_a"],
    }


def _operator_snapshot_payload(
    *,
    checked_at_utc: str,
    availability_status: str = "ready",
    available: bool = True,
    service_statuses: dict[str, str] | None = None,
) -> dict:
    statuses = {
        "voice_runtime_service": "ok",
        "tts_runtime_service": "ok",
        "qdrant": "ok",
        "neo4j": "ok",
    }
    if service_statuses:
        statuses.update(service_statuses)
    return {
        "schema_version": "gateway_operator_status_v1",
        "checked_at_utc": checked_at_utc,
        "status": "ok",
        "operator_context": {
            "profiles": {
                "supported_profiles": ["baseline_first", "combo_a"],
                "combo_a": {
                    "profile": "combo_a",
                    "availability_status": availability_status,
                    "available": available,
                },
            }
        },
        "stack_services": {
            name: {
                "service_name": name,
                "configured": True,
                "status": status,
                "url": f"http://127.0.0.1/{name}",
                "error": None if status == "ok" else f"{name} unhealthy",
            }
            for name, status in statuses.items()
        },
    }


def _write_green_sources(runs_dir: Path, *, checked_at_utc: str) -> None:
    paths = combo_a_cycle._canonical_paths(runs_dir)
    _write_json(paths["gateway_combo_a"], _gateway_summary(finished_at_utc=checked_at_utc, surface="local"))
    _write_json(paths["gateway_http_combo_a"], _gateway_summary(finished_at_utc=checked_at_utc, surface="http"))
    _write_json(paths["cross_service_suite_combo_a"], _suite_summary(checked_at_utc=checked_at_utc))
    _write_json(paths["healthz"], _healthz_payload(timestamp_utc=checked_at_utc))
    _write_json(paths["operator_snapshot"], _operator_snapshot_payload(checked_at_utc=checked_at_utc))


def test_combo_a_operating_cycle_marks_green_inputs_eligible(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    checked = "2026-03-22T18:00:00+00:00"
    _write_green_sources(runs_dir, checked_at_utc=checked)

    result = combo_a_cycle.run_combo_a_operating_cycle(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 22, 18, 15, 0, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["effective_policy"] == "promoted_nightly"
    assert summary["promotion_state"] == "eligible"
    assert summary["blocking_reason_codes"] == []
    assert summary["recommended_actions"] == []
    assert summary["availability_status"] == "ready"


def test_combo_a_operating_cycle_missing_local_artifact_holds_with_specific_action(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    checked = "2026-03-22T18:00:00+00:00"
    _write_green_sources(runs_dir, checked_at_utc=checked)
    combo_a_cycle._canonical_paths(runs_dir)["gateway_combo_a"].unlink()

    result = combo_a_cycle.run_combo_a_operating_cycle(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 22, 18, 15, 0, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["promotion_state"] == "hold"
    assert "missing_live_artifact" in summary["blocking_reason_codes"]
    assert summary["recommended_actions"][0]["action_key"] == "gateway_local_combo_a"


def test_combo_a_operating_cycle_marks_stale_artifact_as_hold(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    stale_checked = "2026-03-20T00:00:00+00:00"
    _write_green_sources(runs_dir, checked_at_utc=stale_checked)

    result = combo_a_cycle.run_combo_a_operating_cycle(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 22, 18, 15, 0, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert summary["promotion_state"] == "hold"
    assert "stale_live_artifact" in summary["blocking_reason_codes"]
    assert any(action["action_key"] == "gateway_local_combo_a" for action in summary["recommended_actions"])


def test_combo_a_operating_cycle_detects_suite_breach(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    checked = "2026-03-22T18:00:00+00:00"
    _write_green_sources(runs_dir, checked_at_utc=checked)
    _write_json(
        combo_a_cycle._canonical_paths(runs_dir)["cross_service_suite_combo_a"],
        _suite_summary(
            checked_at_utc=checked,
            overall_sla_status="breach",
            degraded_services=["retrieval"],
        ),
    )

    result = combo_a_cycle.run_combo_a_operating_cycle(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 22, 18, 15, 0, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert summary["promotion_state"] == "hold"
    assert "cross_service_suite_combo_a_breach" in summary["blocking_reason_codes"]
    assert any(action["action_key"] == "cross_service_suite_combo_a_smoke" for action in summary["recommended_actions"])


def test_combo_a_operating_cycle_detects_unhealthy_service_in_operator_snapshot(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    checked = "2026-03-22T18:00:00+00:00"
    _write_green_sources(runs_dir, checked_at_utc=checked)
    _write_json(
        combo_a_cycle._canonical_paths(runs_dir)["operator_snapshot"],
        _operator_snapshot_payload(
            checked_at_utc=checked,
            availability_status="partial",
            available=False,
            service_statuses={"qdrant": "error"},
        ),
    )

    result = combo_a_cycle.run_combo_a_operating_cycle(
        runs_dir=runs_dir,
        policy="report_only",
        now=datetime(2026, 3, 22, 18, 15, 0, tzinfo=timezone.utc),
    )

    summary = result["summary_payload"]
    assert summary["promotion_state"] == "hold"
    assert "operator_profile_not_ready" in summary["blocking_reason_codes"]
    assert "qdrant_unhealthy" in summary["blocking_reason_codes"]
    assert summary["availability_status"] == "partial"


def test_combo_a_operating_cycle_fail_on_hold_returns_non_zero_only_when_blocked(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    checked = "2026-03-22T18:00:00+00:00"
    _write_green_sources(runs_dir, checked_at_utc=checked)

    green_result = combo_a_cycle.run_combo_a_operating_cycle(
        runs_dir=runs_dir,
        policy="fail_on_hold",
        now=datetime(2026, 3, 22, 18, 15, 0, tzinfo=timezone.utc),
    )
    assert green_result["exit_code"] == 0
    assert green_result["summary_payload"]["promotion_state"] == "promoted"

    combo_a_cycle._canonical_paths(runs_dir)["gateway_http_combo_a"].unlink()
    blocked_result = combo_a_cycle.run_combo_a_operating_cycle(
        runs_dir=runs_dir,
        policy="fail_on_hold",
        now=datetime(2026, 3, 22, 18, 16, 0, tzinfo=timezone.utc),
    )
    assert blocked_result["exit_code"] == 1
    assert blocked_result["summary_payload"]["promotion_state"] == "hold"
