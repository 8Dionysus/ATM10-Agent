from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_INTENT_SCHEMA_VERSION = "automation_intent_v1"
_PLAN_SCHEMA_VERSION = "automation_plan_v1"
_ALLOWED_PRIORITIES = {"low", "normal", "high"}
_ADAPTER_NAME = "intent_to_automation_plan"
_ADAPTER_VERSION = "v1"

_INTENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "open_quest_book": {
        "goal": "open quest book and inspect active objective",
        "tags": ["quests", "ui"],
        "actions": [
            {"id": "open_quest_book", "type": "key_tap", "key": "l"},
            {"id": "wait_ui_stabilize", "type": "wait", "duration_ms": 250, "repeats": 2},
            {"id": "focus_first_quest_line", "type": "mouse_click", "button": "left", "x": 1200, "y": 640},
        ],
    },
    "check_inventory_tool": {
        "goal": "open inventory and verify tool durability",
        "tags": ["inventory", "status"],
        "actions": [
            {"id": "open_inventory", "type": "key_tap", "key": "e"},
            {"id": "wait_inventory_ui", "type": "wait", "duration_ms": 150},
            {"id": "hover_tool_slot", "type": "mouse_move", "x": 1130, "y": 510},
            {"id": "wait_tooltip_render", "type": "wait", "duration_ms": 120},
        ],
    },
    "open_world_map": {
        "goal": "open world map and focus current position",
        "tags": ["map", "navigation"],
        "actions": [
            {"id": "open_world_map", "type": "key_tap", "key": "m"},
            {"id": "wait_world_map_ui", "type": "wait", "duration_ms": 200, "repeats": 2},
            {"id": "focus_player_marker", "type": "key_tap", "key": "space"},
        ],
    },
}


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-intent-to-automation-plan")
    run_dir = runs_dir / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    suffix = 1
    while True:
        candidate = runs_dir / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Intent JSON path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Intent JSON path must be a file: {path}")
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise ValueError(f"Intent JSON file is empty: {path}")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"Intent JSON root must be object: {path}")
    return payload


def _normalize_priority(value: Any) -> str:
    priority = str(value if value is not None else "normal").strip().lower()
    if priority not in _ALLOWED_PRIORITIES:
        raise ValueError(f"intent priority must be one of {sorted(_ALLOWED_PRIORITIES)}.")
    return priority


def _normalize_list_of_strings(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be array when provided.")
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_optional_string(raw_payload: Mapping[str, Any], field: str) -> str | None:
    if field not in raw_payload:
        return None
    value = str(raw_payload.get(field, "")).strip()
    if not value:
        raise ValueError(f"{field} must be non-empty string when provided.")
    return value


def _normalize_intent_payload(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    schema_version = str(raw_payload.get("schema_version", _INTENT_SCHEMA_VERSION)).strip()
    if schema_version != _INTENT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported intent schema_version: {schema_version!r}. "
            f"Expected {_INTENT_SCHEMA_VERSION!r}."
        )

    intent_type = str(raw_payload.get("intent_type", "")).strip().lower()
    if intent_type not in _INTENT_TEMPLATES:
        raise ValueError(f"Unsupported intent_type: {intent_type!r}.")

    template = _INTENT_TEMPLATES[intent_type]
    goal = str(raw_payload.get("goal", template["goal"])).strip()
    if not goal:
        raise ValueError("intent goal must be non-empty string.")

    priority = _normalize_priority(raw_payload.get("priority", "normal"))
    tags = _normalize_list_of_strings(raw_payload.get("tags"), field="tags")
    if not tags:
        tags = list(template["tags"])
    if intent_type not in tags:
        tags.append(intent_type)

    constraints = _normalize_list_of_strings(raw_payload.get("constraints"), field="constraints")
    if "dry_run_only" not in constraints:
        constraints.insert(0, "dry_run_only")

    context = raw_payload.get("context", {})
    if context is None:
        context = {}
    if not isinstance(context, Mapping):
        raise ValueError("context must be JSON object when provided.")
    normalized_context = dict(context)
    source = str(raw_payload.get("source", "")).strip()
    if source:
        normalized_context["source"] = source
    note = str(raw_payload.get("note", "")).strip()
    if note:
        normalized_context["note"] = note
    normalized_context["intent_type"] = intent_type
    intent_id = _normalize_optional_string(raw_payload, "intent_id")
    trace_id = _normalize_optional_string(raw_payload, "trace_id")

    return {
        "schema_version": schema_version,
        "intent_type": intent_type,
        "goal": goal,
        "priority": priority,
        "tags": tags,
        "constraints": constraints,
        "context": normalized_context,
        "intent_id": intent_id,
        "trace_id": trace_id,
    }


def build_automation_plan_from_intent(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    intent = _normalize_intent_payload(raw_payload)
    actions = _INTENT_TEMPLATES[intent["intent_type"]]["actions"]
    planning: dict[str, Any] = {
        "intent_type": intent["intent_type"],
        "intent_schema_version": _INTENT_SCHEMA_VERSION,
        "adapter_name": _ADAPTER_NAME,
        "adapter_version": _ADAPTER_VERSION,
    }
    if intent["intent_id"] is not None:
        planning["intent_id"] = intent["intent_id"]
    if intent["trace_id"] is not None:
        planning["trace_id"] = intent["trace_id"]
    return {
        "schema_version": _PLAN_SCHEMA_VERSION,
        "intent": {
            "goal": intent["goal"],
            "priority": intent["priority"],
            "tags": intent["tags"],
            "constraints": intent["constraints"],
        },
        "context": intent["context"],
        "planning": planning,
        "actions": [dict(action) for action in actions],
    }


def run_intent_to_automation_plan(
    *,
    intent_json: Path,
    runs_dir: Path = Path("runs"),
    plan_out: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    automation_plan_path = plan_out if plan_out is not None else (run_dir / "automation_plan.json")

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "intent_to_automation_plan",
        "status": "started",
        "request": {"intent_json": str(intent_json)},
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "automation_plan_json": str(automation_plan_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        raw_payload = _load_json_object(intent_json)
        plan_payload = build_automation_plan_from_intent(raw_payload)
        _write_json(automation_plan_path, plan_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "dry_run_only": True,
            "intent_type": plan_payload["context"]["intent_type"],
            "action_count": len(plan_payload["actions"]),
        }
        trace_id = plan_payload.get("planning", {}).get("trace_id")
        if trace_id is not None:
            run_payload["result"]["trace_id"] = trace_id
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "plan_payload": plan_payload,
        }
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, FileNotFoundError):
            run_payload["error_code"] = "input_path_missing"
        elif isinstance(exc, (ValueError, json.JSONDecodeError)):
            run_payload["error_code"] = "invalid_intent_payload"
        else:
            run_payload["error_code"] = "intent_adapter_failed"
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "plan_payload": None,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build automation_plan_v1 from intent payload (dry-run only adapter)."
    )
    parser.add_argument("--intent-json", type=Path, required=True, help="Path to intent JSON payload.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    parser.add_argument(
        "--plan-out",
        type=Path,
        default=None,
        help="Optional output path for generated automation plan. Defaults to runs/<timestamp>/automation_plan.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_intent_to_automation_plan(
        intent_json=args.intent_json,
        runs_dir=args.runs_dir,
        plan_out=args.plan_out,
    )
    run_dir = result["run_dir"]
    print(f"[intent_to_automation_plan] run_dir: {run_dir}")
    print(f"[intent_to_automation_plan] run_json: {run_dir / 'run.json'}")
    print(f"[intent_to_automation_plan] automation_plan_json: {result['run_payload']['paths']['automation_plan_json']}")
    if not result["ok"]:
        print(f"[intent_to_automation_plan] error: {result['run_payload']['error']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
