"""Append-only trace and separate mutable-state stores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from atm10_agent.contracts import STATE_SCHEMA_VERSION, TRACE_SCHEMA_VERSION


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_trace(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def record_turn(
    *,
    runs_dir: Path,
    run_dir: Path,
    state_dir: Path,
    turn: Mapping[str, Any],
) -> dict[str, str]:
    turn_path = run_dir / "turn.json"
    trace_path = runs_dir / "turn-trace.jsonl"
    state_path = state_dir / "companion-state.json"
    write_json(turn_path, turn)
    append_trace(
        trace_path,
        {
            "schema_version": TRACE_SCHEMA_VERSION,
            "turn_id": turn["turn_id"],
            "timestamp_utc": turn["timestamp_utc"],
            "status": turn["status"],
            "degraded": turn["degraded"],
            "citations": turn["citations"],
            "memory": (
                turn.get("stages", {}).get("memory")
                if isinstance(turn.get("stages"), Mapping)
                else None
            ),
            "run_artifact": str(turn_path),
            "replay_of": turn.get("replay_of"),
        },
    )

    turn_count = 1
    if state_path.is_file():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
            turn_count = int(previous.get("turn_count", 0)) + 1
        except (ValueError, TypeError, json.JSONDecodeError):
            turn_count = 1
    write_json(
        state_path,
        {
            "schema_version": STATE_SCHEMA_VERSION,
            "turn_count": turn_count,
            "last_turn_id": turn["turn_id"],
            "last_status": turn["status"],
        },
    )
    return {
        "run_dir": str(run_dir),
        "turn_json": str(turn_path),
        "append_only_trace": str(trace_path),
        "mutable_state": str(state_path),
    }
