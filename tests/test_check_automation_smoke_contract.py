from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import scripts.check_automation_smoke_contract as checker


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_check_automation_smoke_contract_dry_run_ok(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "20260223_210000-automation-dry-run"
    _write_json(
        run_dir / "run.json",
        {
            "status": "ok",
            "result": {"dry_run": True, "action_count": 3, "step_count": 4},
        },
    )
    _write_json(run_dir / "actions_normalized.json", {"schema_version": "automation_plan_v1"})
    _write_json(run_dir / "execution_plan.json", {"dry_run": True, "step_count": 4})
    ok, errors, observed = checker._check_dry_run_contract(
        run_dir=run_dir,
        min_action_count=3,
        min_step_count=4,
    )
    assert ok is True
    assert errors == []
    assert observed["action_count"] == 3
    assert observed["step_count"] == 4
    assert observed["schema_version"] == "automation_plan_v1"


def test_check_automation_smoke_contract_chain_ok(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "20260223_210001-automation-intent-chain-smoke"
    _write_json(
        run_dir / "run.json",
        {
            "status": "ok",
            "result": {
                "dry_run_only": True,
                "intent_type": "open_quest_book",
                "action_count": 3,
                "step_count": 4,
            },
        },
    )
    _write_json(run_dir / "chain_summary.json", {"ok": True})
    _write_json(run_dir / "automation_plan.json", {"schema_version": "automation_plan_v1", "context": {"intent_type": "open_quest_book"}})
    ok, errors, observed = checker._check_chain_contract(
        run_dir=run_dir,
        min_action_count=3,
        min_step_count=4,
        expected_intent_type="open_quest_book",
    )
    assert ok is True
    assert errors == []
    assert observed["action_count"] == 3
    assert observed["step_count"] == 4
    assert observed["intent_type"] == "open_quest_book"


def test_check_automation_smoke_contract_chain_fails_on_intent_type(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "20260223_210002-automation-intent-chain-smoke"
    _write_json(
        run_dir / "run.json",
        {
            "status": "ok",
            "result": {
                "dry_run_only": True,
                "intent_type": "open_quest_book",
                "action_count": 3,
                "step_count": 4,
            },
        },
    )
    _write_json(run_dir / "chain_summary.json", {"ok": True})
    _write_json(run_dir / "automation_plan.json", {"schema_version": "automation_plan_v1", "context": {"intent_type": "check_inventory_tool"}})
    ok, errors, _observed = checker._check_chain_contract(
        run_dir=run_dir,
        min_action_count=1,
        min_step_count=1,
        expected_intent_type="open_quest_book",
    )
    assert ok is False
    assert any("expected_intent_type" in item for item in errors)


def test_check_automation_smoke_contract_main_writes_summary_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "runs" / "20260223_210003-automation-dry-run"
    _write_json(
        run_dir / "run.json",
        {
            "status": "ok",
            "result": {"dry_run": True, "action_count": 3, "step_count": 4},
        },
    )
    _write_json(run_dir / "actions_normalized.json", {"schema_version": "automation_plan_v1"})
    _write_json(run_dir / "execution_plan.json", {"dry_run": True, "step_count": 4})
    summary_path = tmp_path / "summary.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_automation_smoke_contract.py",
            "--mode",
            "dry_run",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--summary-json",
            str(summary_path),
            "--min-action-count",
            "3",
            "--min-step-count",
            "4",
        ],
    )
    exit_code = checker.main()
    assert exit_code == 0
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert summary["status"] == "ok"
    assert summary["mode"] == "dry_run"
    assert summary["observed"]["action_count"] == 3
    assert summary["violations"] == []


def test_check_automation_smoke_contract_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_automation_smoke_contract.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        checker.parse_args()
    assert exc.value.code == 0
