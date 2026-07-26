"""Compatibility CLI for the package-owned ATM10 intent planner."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from atm10_agent.action import build_plan_from_intent


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base = runs_dir / now.strftime("%Y%m%d_%H%M%S-intent-to-automation-plan")
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = runs_dir / f"{base.name}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


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


def run_intent_to_automation_plan(
    *,
    intent_json: Path,
    runs_dir: Path = Path("runs"),
    plan_out: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed_at = now or datetime.now(timezone.utc)
    run_dir = _create_run_dir(runs_dir, observed_at)
    run_json_path = run_dir / "run.json"
    plan_path = plan_out if plan_out is not None else run_dir / "automation_plan.json"
    run_payload: dict[str, Any] = {
        "timestamp_utc": observed_at.astimezone(timezone.utc).isoformat(),
        "mode": "intent_to_automation_plan",
        "status": "started",
        "request": {"intent_json": str(intent_json)},
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "automation_plan_json": str(plan_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        plan_payload = build_plan_from_intent(_load_json_object(intent_json))
        _write_json(plan_path, plan_payload)
        planning = plan_payload["planning"]
        run_payload["status"] = "ok"
        run_payload["result"] = {
            "dry_run_only": True,
            "intent_type": plan_payload["context"]["intent_type"],
            "action_count": len(plan_payload["actions"]),
        }
        for field in ("intent_id", "trace_id"):
            if field in planning:
                run_payload["result"][field] = planning[field]
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
        description="Build automation_plan_v1 through the package-owned dry-run planner."
    )
    parser.add_argument("--intent-json", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--plan-out", type=Path)
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
    print(
        "[intent_to_automation_plan] automation_plan_json: "
        f"{result['run_payload']['paths']['automation_plan_json']}"
    )
    if not result["ok"]:
        print(f"[intent_to_automation_plan] error: {result['run_payload']['error']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
