from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from atm10_agent.app import CompanionApp, run_companion_turn
from atm10_agent.cli import main
from atm10_agent.contracts import TurnRequest


FIXED_NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)


def test_deterministic_turn_covers_the_full_companion_boundary(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    state_dir = tmp_path / "state"
    result = run_companion_turn(
        TurnRequest(
            prompt="Describe the current ATM10 context.",
            query="steel tools",
            action_intent="open_quest_book",
        ),
        runs_dir=runs_dir,
        state_dir=state_dir,
        now=FIXED_NOW,
    )

    assert result["schema_version"] == "atm10_companion_turn_v1"
    assert result["status"] == "ok"
    assert result["degraded"] is False
    assert list(result["stages"]) == ["perception", "interpretation", "world"]
    assert result["stages"]["perception"]["provider"] == "deterministic_stub_v1"
    assert result["stages"]["world"]["backend"] == "file"
    assert result["citations"]
    assert result["citations"][0]["source"] == "atm10_builtin_world"
    assert result["citations"][0]["path"] == (
        "package://atm10_agent/data/default_world.jsonl"
    )
    assert result["response"]["mode"] == "grounded_file_world"
    assert result["action"]["dry_run"] is True
    assert result["action"]["executed"] is False
    assert result["voice"]["status"] == "not_requested"

    trace = result["trace"]
    assert Path(trace["turn_json"]).is_file()
    assert Path(trace["append_only_trace"]).is_file()
    assert Path(trace["mutable_state"]).is_file()
    assert Path(trace["append_only_trace"]).parent == runs_dir
    assert Path(trace["mutable_state"]).parent == state_dir


def test_replay_preserves_response_and_citations_without_running_providers(
    tmp_path: Path,
) -> None:
    app = CompanionApp(runs_dir=tmp_path / "runs", state_dir=tmp_path / "state")
    original = app.run(
        TurnRequest(prompt="Observe ATM10.", query="better furnace"),
        now=FIXED_NOW,
    )
    replay = app.replay(
        Path(original["trace"]["turn_json"]),
        now=datetime(2026, 7, 25, 12, 1, 0, tzinfo=timezone.utc),
    )
    repeated_replay = app.replay(
        Path(original["trace"]["turn_json"]),
        now=datetime(2026, 7, 25, 12, 1, 0, tzinfo=timezone.utc),
    )

    assert replay["replay_of"] == original["turn_id"]
    assert replay["turn_id"] != original["turn_id"]
    assert repeated_replay["replay_of"] == original["turn_id"]
    assert repeated_replay["turn_id"] != replay["turn_id"]
    assert replay["response"] == original["response"]
    assert replay["citations"] == original["citations"]
    assert Path(replay["trace"]["turn_json"]).is_file()


def test_missing_optional_voice_provider_is_honest_degradation(tmp_path: Path) -> None:
    result = run_companion_turn(
        TurnRequest(prompt="Observe ATM10.", query="starter tools", voice=True),
        runs_dir=tmp_path / "runs",
        state_dir=tmp_path / "state",
        now=FIXED_NOW,
    )

    assert result["status"] == "degraded"
    assert result["degraded"] is True
    assert result["degradation_reasons"] == ["voice_provider_not_configured"]
    assert result["voice"]["audio_written"] is False


def test_unsupported_action_never_executes_input(tmp_path: Path) -> None:
    result = run_companion_turn(
        TurnRequest(
            prompt="Observe ATM10.",
            query="steel",
            action_intent="destroy_world",
        ),
        runs_dir=tmp_path / "runs",
        state_dir=tmp_path / "state",
        now=FIXED_NOW,
    )

    assert result["status"] == "degraded"
    assert result["action"] == {
        "schema_version": "atm10_action_plan_v1",
        "status": "degraded",
        "dry_run": True,
        "executed": False,
        "intent": "destroy_world",
        "actions": [],
        "degradation_reason": "unsupported_action_intent",
    }


def test_cli_doctor_and_run_are_dependency_light(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert main(["doctor"]) == 0
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["core_dependencies"] == []
    assert doctor["action_default"] == "dry_run_only"

    assert (
        main(
            [
                "run",
                "--prompt",
                "Observe ATM10.",
                "--query",
                "steel tools",
                "--runs-dir",
                str(tmp_path / "runs"),
                "--state-dir",
                str(tmp_path / "state"),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "atm10_companion_turn_v1"
    assert result["action"]["executed"] is False
