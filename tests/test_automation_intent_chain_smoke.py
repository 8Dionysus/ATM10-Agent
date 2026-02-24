from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.automation_intent_chain_smoke as chain_smoke


def _fixture_payload(name: str) -> dict[str, object]:
    fixture_path = Path(__file__).parent / "fixtures" / name
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_automation_intent_chain_smoke_runs_end_to_end(tmp_path: Path) -> None:
    intent_json = tmp_path / "intent.json"
    intent_json.write_text(
        json.dumps(_fixture_payload("intent_open_quest_book.json"), ensure_ascii=False),
        encoding="utf-8",
    )

    result = chain_smoke.run_automation_intent_chain_smoke(
        intent_json=intent_json,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 23, 20, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    summary_payload = json.loads((run_dir / "chain_summary.json").read_text(encoding="utf-8"))
    plan_payload = json.loads((run_dir / "automation_plan.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260223_200000-automation-intent-chain-smoke"
    assert run_payload["status"] == "ok"
    assert run_payload["mode"] == "automation_intent_chain_smoke"
    assert run_payload["result"]["dry_run_only"] is True
    assert run_payload["result"]["intent_type"] == "open_quest_book"
    assert run_payload["result"]["action_count"] == 3
    assert run_payload["result"]["step_count"] == 4
    assert summary_payload["ok"] is True
    assert summary_payload["intent_adapter"]["ok"] is True
    assert summary_payload["automation_dry_run"]["ok"] is True
    assert plan_payload["schema_version"] == "automation_plan_v1"
    assert plan_payload["context"]["intent_type"] == "open_quest_book"
    assert plan_payload["planning"]["intent_type"] == "open_quest_book"


def test_automation_intent_chain_smoke_propagates_trace_id(tmp_path: Path) -> None:
    intent_json = tmp_path / "intent_with_trace.json"
    intent_json.write_text(
        json.dumps(
            {
                "schema_version": "automation_intent_v1",
                "intent_type": "open_quest_book",
                "trace_id": "trace-chain-42",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = chain_smoke.run_automation_intent_chain_smoke(
        intent_json=intent_json,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 24, 10, 32, 0, tzinfo=timezone.utc),
    )

    run_payload = json.loads((result["run_dir"] / "run.json").read_text(encoding="utf-8"))
    summary_payload = json.loads((result["run_dir"] / "chain_summary.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_payload["result"]["trace_id"] == "trace-chain-42"
    assert summary_payload["intent_adapter"]["trace_id"] == "trace-chain-42"


def test_automation_intent_chain_smoke_runs_inventory_fixture(tmp_path: Path) -> None:
    intent_json = tmp_path / "intent_inventory.json"
    intent_json.write_text(
        json.dumps(_fixture_payload("intent_check_inventory_tool.json"), ensure_ascii=False),
        encoding="utf-8",
    )

    result = chain_smoke.run_automation_intent_chain_smoke(
        intent_json=intent_json,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 24, 11, 0, 0, tzinfo=timezone.utc),
    )

    run_payload = json.loads((result["run_dir"] / "run.json").read_text(encoding="utf-8"))
    summary_payload = json.loads((result["run_dir"] / "chain_summary.json").read_text(encoding="utf-8"))
    plan_payload = json.loads((result["run_dir"] / "automation_plan.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_payload["result"]["intent_type"] == "check_inventory_tool"
    assert run_payload["result"]["action_count"] == 4
    assert run_payload["result"]["step_count"] == 4
    assert summary_payload["intent_adapter"]["intent_type"] == "check_inventory_tool"
    assert plan_payload["context"]["intent_type"] == "check_inventory_tool"


def test_automation_intent_chain_smoke_rejects_invalid_intent(tmp_path: Path) -> None:
    intent_json = tmp_path / "bad_intent.json"
    intent_json.write_text(
        json.dumps({"schema_version": "automation_intent_v1", "intent_type": "unsupported"}),
        encoding="utf-8",
    )

    result = chain_smoke.run_automation_intent_chain_smoke(
        intent_json=intent_json,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 23, 20, 1, 0, tzinfo=timezone.utc),
    )

    run_payload = result["run_payload"]
    assert result["ok"] is False
    assert run_payload["status"] == "error"
    assert run_payload["error_code"] == "intent_adapter_failed"
    assert "Unsupported intent_type" in str(run_payload["error"])


def test_automation_intent_chain_smoke_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["automation_intent_chain_smoke.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        chain_smoke.parse_args()
    assert exc.value.code == 0
