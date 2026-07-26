"""Compatibility CLI for package-owned ATM10 dry-run action contracts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from atm10_agent.action import build_dry_run_execution, normalize_plan


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base = runs_dir / now.strftime("%Y%m%d_%H%M%S-automation-dry-run")
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


def _load_plan(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Plan JSON path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Plan JSON path must be a file: {path}")
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise ValueError(f"Plan JSON file is empty: {path}")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"Plan JSON root must be object: {path}")
    return payload


def run_automation_dry_run(
    *,
    plan_json: Path,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    observed_at = now or datetime.now(timezone.utc)
    run_dir = _create_run_dir(runs_dir, observed_at)
    run_json_path = run_dir / "run.json"
    normalized_path = run_dir / "actions_normalized.json"
    execution_path = run_dir / "execution_plan.json"
    run_payload: dict[str, Any] = {
        "timestamp_utc": observed_at.astimezone(timezone.utc).isoformat(),
        "mode": "automation_dry_run",
        "status": "started",
        "request": {"plan_json": str(plan_json)},
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "actions_normalized_json": str(normalized_path),
            "execution_plan_json": str(execution_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        normalized = normalize_plan(_load_plan(plan_json))
        execution = build_dry_run_execution(normalized)
        _write_json(normalized_path, normalized)
        _write_json(execution_path, execution)
        run_payload["status"] = "ok"
        run_payload["result"] = {
            "dry_run": True,
            "action_count": len(normalized["actions"]),
            "step_count": execution["step_count"],
            "estimated_total_duration_ms": execution["estimated_total_duration_ms"],
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "normalized_payload": normalized,
            "execution_plan": execution,
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
        description="Validate an action plan through the package-owned dry-run fence."
    )
    parser.add_argument("--plan-json", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
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
