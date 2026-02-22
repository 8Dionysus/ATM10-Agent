from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_ALLOWED_ACTION_TYPES = {
    "key_tap",
    "key_hold",
    "mouse_move",
    "mouse_click",
    "mouse_scroll",
    "wait",
}
_ALLOWED_MOUSE_BUTTONS = {"left", "right", "middle"}


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-automation-dry-run")
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


def _load_plan_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Plan JSON path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Plan JSON path must be a file: {path}")
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise ValueError(f"Plan JSON file is empty: {path}")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"Plan JSON root must be object: {path}")
    return parsed


def _coerce_int(name: str, value: Any, *, min_value: int | None = None) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{name} must be integer.")
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value}.")
    return value


def _normalize_action(action: Mapping[str, Any], *, default_id: str) -> dict[str, Any]:
    action_type = str(action.get("type", "")).strip().lower()
    if action_type not in _ALLOWED_ACTION_TYPES:
        raise ValueError(f"Unsupported action type: {action_type!r}")

    action_id = str(action.get("id", default_id)).strip() or default_id
    repeats = _coerce_int("repeats", int(action.get("repeats", 1)), min_value=1)
    params: dict[str, Any] = {}
    base_duration_ms = 0

    if action_type == "key_tap":
        key = str(action.get("key", "")).strip()
        if not key:
            raise ValueError("key_tap action requires non-empty key.")
        params["key"] = key
        base_duration_ms = 50
    elif action_type == "key_hold":
        key = str(action.get("key", "")).strip()
        if not key:
            raise ValueError("key_hold action requires non-empty key.")
        hold_ms = _coerce_int("hold_ms", action.get("hold_ms"), min_value=1)
        params["key"] = key
        params["hold_ms"] = hold_ms
        base_duration_ms = hold_ms
    elif action_type == "mouse_move":
        x = _coerce_int("x", action.get("x"))
        y = _coerce_int("y", action.get("y"))
        params["x"] = x
        params["y"] = y
        base_duration_ms = 30
    elif action_type == "mouse_click":
        button = str(action.get("button", "left")).strip().lower()
        if button not in _ALLOWED_MOUSE_BUTTONS:
            raise ValueError(f"mouse_click button must be one of {_ALLOWED_MOUSE_BUTTONS}.")
        params["button"] = button
        if "x" in action:
            params["x"] = _coerce_int("x", action.get("x"))
        if "y" in action:
            params["y"] = _coerce_int("y", action.get("y"))
        base_duration_ms = 40
    elif action_type == "mouse_scroll":
        delta = _coerce_int("delta", action.get("delta"))
        if delta == 0:
            raise ValueError("mouse_scroll delta must not be 0.")
        params["delta"] = delta
        base_duration_ms = 30
    else:
        duration_ms = _coerce_int("duration_ms", action.get("duration_ms"), min_value=1)
        params["duration_ms"] = duration_ms
        base_duration_ms = duration_ms

    estimated_duration_ms = base_duration_ms * repeats
    return {
        "id": action_id,
        "type": action_type,
        "params": params,
        "repeats": repeats,
        "estimated_duration_ms": estimated_duration_ms,
    }


def _normalize_plan_payload(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_actions = raw_payload.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise ValueError("Plan payload must contain non-empty actions list.")

    normalized_actions: list[dict[str, Any]] = []
    for index, action in enumerate(raw_actions, start=1):
        if not isinstance(action, Mapping):
            raise ValueError(f"Action #{index} must be JSON object.")
        normalized_actions.append(_normalize_action(action, default_id=f"a{index:03d}"))

    context = raw_payload.get("context", {})
    if context is None:
        context = {}
    if not isinstance(context, Mapping):
        raise ValueError("context must be JSON object when provided.")

    return {
        "schema_version": "automation_plan_v1",
        "dry_run": True,
        "context": dict(context),
        "actions": normalized_actions,
    }


def _build_execution_plan(normalized_payload: Mapping[str, Any]) -> dict[str, Any]:
    actions = normalized_payload["actions"]
    steps: list[dict[str, Any]] = []
    step_index = 0
    for action in actions:
        repeats = int(action["repeats"])
        for iteration in range(1, repeats + 1):
            step_index += 1
            steps.append(
                {
                    "step_index": step_index,
                    "action_id": str(action["id"]),
                    "action_type": str(action["type"]),
                    "iteration": iteration,
                    "params": dict(action["params"]),
                    "dry_run_message": f"DRY-RUN: would execute {action['type']} ({iteration}/{repeats})",
                }
            )
    return {
        "dry_run": True,
        "step_count": len(steps),
        "estimated_total_duration_ms": sum(int(action["estimated_duration_ms"]) for action in actions),
        "steps": steps,
    }


def run_automation_dry_run(
    *,
    plan_json: Path,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    actions_normalized_path = run_dir / "actions_normalized.json"
    execution_plan_path = run_dir / "execution_plan.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "automation_dry_run",
        "status": "started",
        "request": {"plan_json": str(plan_json)},
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "actions_normalized_json": str(actions_normalized_path),
            "execution_plan_json": str(execution_plan_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        raw_payload = _load_plan_payload(plan_json)
        normalized_payload = _normalize_plan_payload(raw_payload)
        execution_plan = _build_execution_plan(normalized_payload)

        _write_json(actions_normalized_path, normalized_payload)
        _write_json(execution_plan_path, execution_plan)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "dry_run": True,
            "action_count": len(normalized_payload["actions"]),
            "step_count": int(execution_plan["step_count"]),
            "estimated_total_duration_ms": int(execution_plan["estimated_total_duration_ms"]),
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "normalized_payload": normalized_payload,
            "execution_plan": execution_plan,
        }
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, FileNotFoundError):
            run_payload["error_code"] = "input_path_missing"
        elif isinstance(exc, (ValueError, json.JSONDecodeError)):
            run_payload["error_code"] = "invalid_action_plan"
        else:
            run_payload["error_code"] = "automation_dry_run_failed"
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "normalized_payload": None,
            "execution_plan": None,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automation dry-run: validate/normalize action plan and write execution plan artifacts."
    )
    parser.add_argument("--plan-json", type=Path, required=True, help="Path to action plan JSON.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_automation_dry_run(plan_json=args.plan_json, runs_dir=args.runs_dir)
    run_dir = result["run_dir"]
    print(f"[automation_dry_run] run_dir: {run_dir}")
    print(f"[automation_dry_run] run_json: {run_dir / 'run.json'}")
    print(f"[automation_dry_run] actions_normalized_json: {run_dir / 'actions_normalized.json'}")
    print(f"[automation_dry_run] execution_plan_json: {run_dir / 'execution_plan.json'}")
    if not result["ok"]:
        print(f"[automation_dry_run] error: {result['run_payload']['error']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
