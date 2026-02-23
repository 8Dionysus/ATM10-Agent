from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.intent_to_automation_plan as intent_adapter


def _fixture_payload(name: str) -> dict[str, object]:
    fixture_path = Path(__file__).parent / "fixtures" / name
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_intent_to_automation_plan_builds_expected_payload(tmp_path: Path) -> None:
    intent_json = tmp_path / "intent.json"
    intent_json.write_text(
        json.dumps(_fixture_payload("intent_open_quest_book.json"), ensure_ascii=False),
        encoding="utf-8",
    )

    result = intent_adapter.run_intent_to_automation_plan(
        intent_json=intent_json,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 23, 19, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    plan_payload = json.loads((run_dir / "automation_plan.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260223_190000-intent-to-automation-plan"
    assert run_payload["status"] == "ok"
    assert run_payload["result"]["dry_run_only"] is True
    assert run_payload["result"]["intent_type"] == "open_quest_book"
    assert plan_payload["schema_version"] == "automation_plan_v1"
    assert plan_payload["intent"]["goal"] == "open quest book and inspect active objective"
    assert plan_payload["context"]["source"] == "voice_intent"
    assert plan_payload["context"]["intent_type"] == "open_quest_book"
    assert len(plan_payload["actions"]) == 3


def test_intent_to_automation_plan_rejects_unknown_intent_type(tmp_path: Path) -> None:
    intent_json = tmp_path / "bad_intent.json"
    intent_json.write_text(
        json.dumps({"schema_version": "automation_intent_v1", "intent_type": "unknown"}),
        encoding="utf-8",
    )

    result = intent_adapter.run_intent_to_automation_plan(
        intent_json=intent_json,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 23, 19, 1, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["run_payload"]["status"] == "error"
    assert result["run_payload"]["error_code"] == "invalid_intent_payload"
    assert "Unsupported intent_type" in str(result["run_payload"]["error"])


def test_intent_to_automation_plan_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["intent_to_automation_plan.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        intent_adapter.parse_args()
    assert exc.value.code == 0
