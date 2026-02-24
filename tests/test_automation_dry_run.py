from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.automation_dry_run as automation_dry_run


def _fixture_payload(name: str) -> dict[str, object]:
    fixture_path = Path(__file__).parent / "fixtures" / name
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_automation_dry_run_writes_plan_artifacts(tmp_path: Path) -> None:
    plan_path = tmp_path / "actions.json"
    payload = {
        "context": {"source": "manual_hotkey", "note": "open quest book and wait"},
        "actions": [
            {"type": "key_tap", "key": "l"},
            {"type": "wait", "duration_ms": 250, "repeats": 2},
            {"type": "mouse_click", "button": "left", "x": 1200, "y": 640},
        ],
    }
    plan_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = automation_dry_run.run_automation_dry_run(
        plan_json=plan_path,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 22, 30, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    normalized_payload = json.loads((run_dir / "actions_normalized.json").read_text(encoding="utf-8"))
    execution_plan = json.loads((run_dir / "execution_plan.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260222_223000-automation-dry-run"
    assert run_payload["status"] == "ok"
    assert run_payload["result"]["dry_run"] is True
    assert run_payload["result"]["action_count"] == 3
    assert run_payload["result"]["step_count"] == 4
    assert normalized_payload["dry_run"] is True
    assert normalized_payload["actions"][1]["repeats"] == 2
    assert execution_plan["step_count"] == 4
    assert execution_plan["steps"][1]["dry_run_message"].startswith("DRY-RUN: would execute wait")


def test_automation_dry_run_contract_v1_with_intent_fixture(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan_contract_v1.json"
    payload = _fixture_payload("automation_plan_quest_book.json")
    plan_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = automation_dry_run.run_automation_dry_run(
        plan_json=plan_path,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 23, 18, 0, 0, tzinfo=timezone.utc),
    )

    normalized_payload = json.loads(
        (result["run_dir"] / "actions_normalized.json").read_text(encoding="utf-8")
    )
    assert result["ok"] is True
    assert normalized_payload["schema_version"] == "automation_plan_v1"
    assert normalized_payload["intent"]["goal"] == "open quest book and inspect active objective"
    assert normalized_payload["intent"]["priority"] == "normal"
    assert normalized_payload["intent"]["constraints"][0] == "dry_run_only"


def test_automation_dry_run_preserves_planning_metadata(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan_with_planning.json"
    payload = {
        "schema_version": "automation_plan_v1",
        "planning": {
            "intent_type": "open_quest_book",
            "intent_id": "intent-001",
            "trace_id": "trace-abc",
            "intent_schema_version": "automation_intent_v1",
            "adapter_name": "intent_to_automation_plan",
            "adapter_version": "v1",
        },
        "actions": [{"type": "key_tap", "key": "l"}],
    }
    plan_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = automation_dry_run.run_automation_dry_run(
        plan_json=plan_path,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 24, 10, 30, 0, tzinfo=timezone.utc),
    )

    normalized_payload = json.loads(
        (result["run_dir"] / "actions_normalized.json").read_text(encoding="utf-8")
    )
    assert result["ok"] is True
    assert normalized_payload["planning"]["intent_id"] == "intent-001"
    assert normalized_payload["planning"]["trace_id"] == "trace-abc"
    assert normalized_payload["planning"]["adapter_name"] == "intent_to_automation_plan"


def test_automation_dry_run_rejects_empty_actions(tmp_path: Path) -> None:
    plan_path = tmp_path / "bad_actions.json"
    plan_path.write_text(json.dumps({"actions": []}, ensure_ascii=False), encoding="utf-8")

    result = automation_dry_run.run_automation_dry_run(
        plan_json=plan_path,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 22, 31, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["run_payload"]["status"] == "error"
    assert result["run_payload"]["error_code"] == "invalid_action_plan"


def test_automation_dry_run_rejects_unknown_schema_version(tmp_path: Path) -> None:
    plan_path = tmp_path / "bad_schema.json"
    payload = {
        "schema_version": "automation_plan_v2",
        "actions": [{"type": "key_tap", "key": "l"}],
    }
    plan_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = automation_dry_run.run_automation_dry_run(
        plan_json=plan_path,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 23, 18, 1, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["run_payload"]["status"] == "error"
    assert result["run_payload"]["error_code"] == "invalid_action_plan"
    assert "Unsupported schema_version" in str(result["run_payload"]["error"])


def test_automation_dry_run_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["automation_dry_run.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        automation_dry_run.parse_args()
    assert exc.value.code == 0
