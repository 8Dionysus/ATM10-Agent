from __future__ import annotations

import json
from pathlib import Path

import scripts.operator_product_safe_actions as safe_actions


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_recommended_safe_actions_filters_to_allowed_catalog() -> None:
    actions = safe_actions.recommended_safe_actions("pilot_grounding_degraded")

    assert actions == [
        "gateway_http_combo_a",
        "cross_service_suite_combo_a_smoke",
    ]


def test_build_safe_actions_overview_exposes_return_recommendation(tmp_path: Path) -> None:
    operator_runs_dir = tmp_path / "operator-runs"
    startup_run_dir = operator_runs_dir / "20260322_120000-start-operator-product"
    _write_json(
        startup_run_dir / "run.json",
        {
            "schema_version": "operator_product_startup_v1",
            "mode": "start_operator_product",
            "last_return_event": {
                "schema_version": "gateway_operator_return_event_v1",
                "event_id": "return-abc123",
                "timestamp_utc": "2026-03-22T12:00:30+00:00",
                "status": "open",
                "surface": "gateway",
                "reason_code": "gateway_snapshot_not_ready",
                "severity": "attention",
                "return_mode": "reprobe",
                "operator_visible": True,
                "anchor_refs": [],
                "recommended_safe_actions": ["gateway_http_core"],
                "triage_hint": "Re-probe the gateway operator snapshot.",
                "loop_count": 1,
                "safe_stop_after": 2,
                "details": {},
            },
        },
    )

    overview = safe_actions.build_safe_actions_overview(
        runs_dir=tmp_path / "runs",
        operator_runs_dir=operator_runs_dir,
    )

    assert overview["schema_version"] == "gateway_operator_safe_actions_v1"
    assert overview["recommended_action_key"] == "gateway_http_core"
    assert overview["recommended_action_keys"] == ["gateway_http_core"]


def test_return_contract_examples_exist() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    assert (repo_root / "schemas" / "gateway_operator_return_event.schema.json").is_file()
    assert (repo_root / "schemas" / "gateway_operator_return_summary.schema.json").is_file()
    assert (repo_root / "schemas" / "operator_return_reason_catalog.schema.json").is_file()
    assert (repo_root / "examples" / "gateway_operator_return_event.example.json").is_file()
    assert (repo_root / "examples" / "gateway_operator_return_summary.example.json").is_file()
    assert (repo_root / "examples" / "operator_return_reason_catalog.example.json").is_file()
