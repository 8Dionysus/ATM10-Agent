from __future__ import annotations

import json
from pathlib import Path

import scripts.operator_return_recovery as operator_return_recovery


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_resolve_startup_return_surface_stops_at_latest_clean_run(tmp_path: Path) -> None:
    operator_runs_dir = tmp_path / "runs"
    latest_run = operator_runs_dir / "20260328_020000-start-operator-product"
    older_run = operator_runs_dir / "20260328_010000-start-operator-product"

    _write_json(
        latest_run / "run.json",
        {
            "last_return_event": None,
        },
    )
    _write_json(
        older_run / "run.json",
        {
            "last_return_event": {
                "schema_version": operator_return_recovery.GATEWAY_OPERATOR_RETURN_EVENT_SCHEMA,
                "event_id": "return-old",
                "timestamp_utc": "2026-03-28T01:00:00+00:00",
                "status": "open",
                "surface": "startup",
                "reason_code": "startup_checkpoint_failed",
                "severity": "degraded",
                "return_mode": "restart_surface",
                "operator_visible": True,
                "anchor_refs": [],
                "recommended_safe_actions": ["gateway_http_core"],
                "triage_hint": "Review the latest startup checkpoint.",
                "loop_count": 1,
                "safe_stop_after": 2,
                "details": {},
            },
        },
    )

    event_payload, paths_payload = operator_return_recovery._resolve_startup_return_surface(operator_runs_dir)

    assert event_payload is None
    assert paths_payload is None


def test_build_return_summary_prioritizes_safe_stop_guidance() -> None:
    summary = operator_return_recovery.build_return_summary(
        [
            {
                "source": "pilot_runtime",
                "event": {
                    "schema_version": operator_return_recovery.GATEWAY_OPERATOR_RETURN_EVENT_SCHEMA,
                    "event_id": "return-safe-stop",
                    "timestamp_utc": "2026-03-28T03:00:00+00:00",
                    "status": "safe_stop",
                    "surface": "pilot_runtime",
                    "reason_code": "pilot_runtime_exited",
                    "severity": "critical",
                    "return_mode": "safe_stop",
                    "operator_visible": True,
                    "anchor_refs": [],
                    "recommended_safe_actions": ["gateway_http_combo_a"],
                    "triage_hint": "The pilot runtime exited and needs a safe stop.",
                    "loop_count": 2,
                    "safe_stop_after": 2,
                    "details": {},
                },
                "paths": operator_return_recovery.return_paths(Path("runs") / "pilot-runtime"),
            }
        ]
    )

    assert summary is not None
    assert summary["status"] == "safe_stop"
    assert summary["next_step_code"] == "safe_stop"
    assert summary["recommended_safe_actions"] == ["gateway_http_combo_a"]
