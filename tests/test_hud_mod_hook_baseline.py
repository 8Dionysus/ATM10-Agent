from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.hud_mod_hook_baseline as hook_demo


def test_hud_mod_hook_baseline_writes_normalized_artifacts(tmp_path: Path) -> None:
    hook_path = tmp_path / "hook.json"
    hook_payload = {
        "event_ts": "2026-02-22T20:00:00+00:00",
        "source": "atm10_mod_hook",
        "hud_lines": ["Quest Updated", "Collect 16 wood"],
        "quest_updates": [
            {"id": "quest:start", "text": "Collect logs", "status": "active"},
            "Open quest book",
        ],
        "player_state": {"dimension": "minecraft:overworld", "x": 12, "y": 70, "z": -5, "health": 18.0},
        "context_tags": ["hud", "quest", "overlay"],
    }
    hook_path.write_text(json.dumps(hook_payload, ensure_ascii=False), encoding="utf-8")

    result = hook_demo.run_hud_mod_hook_baseline(
        hook_json=hook_path,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 20, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    normalized_payload = json.loads((run_dir / "hook_normalized.json").read_text(encoding="utf-8"))
    hud_text = (run_dir / "hud_text.txt").read_text(encoding="utf-8")

    assert result["ok"] is True
    assert run_dir.name == "20260222_200000-hud-hook"
    assert run_payload["status"] == "ok"
    assert run_payload["result"]["hud_line_count"] == 2
    assert run_payload["result"]["quest_update_count"] == 2
    assert normalized_payload["source"] == "atm10_mod_hook"
    assert normalized_payload["quest_updates"][1]["text"] == "Open quest book"
    assert "Quest Updated" in hud_text


def test_hud_mod_hook_baseline_rejects_empty_payload_content(tmp_path: Path) -> None:
    hook_path = tmp_path / "empty_hook.json"
    hook_path.write_text(json.dumps({"source": "atm10_mod_hook"}, ensure_ascii=False), encoding="utf-8")

    result = hook_demo.run_hud_mod_hook_baseline(
        hook_json=hook_path,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 20, 1, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["run_payload"]["error_code"] == "invalid_hook_payload"


def test_hud_mod_hook_baseline_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["hud_mod_hook_baseline.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        hook_demo.parse_args()
    assert exc.value.code == 0
