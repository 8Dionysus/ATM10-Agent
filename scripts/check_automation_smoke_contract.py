from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _latest_run_dir(runs_dir: Path, suffix: str) -> Path:
    if not runs_dir.exists() or not runs_dir.is_dir():
        raise FileNotFoundError(f"Runs directory not found: {runs_dir}")
    candidates = sorted(
        [path for path in runs_dir.iterdir() if path.is_dir() and path.name.endswith(suffix)],
        key=lambda path: path.name,
    )
    if not candidates:
        raise FileNotFoundError(f"No run directory with suffix '{suffix}' under: {runs_dir}")
    return candidates[-1]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _check_dry_run_contract(
    *,
    run_dir: Path,
    min_action_count: int,
    min_step_count: int,
) -> tuple[bool, list[str], dict[str, Any]]:
    errors: list[str] = []
    run_payload = _read_json(run_dir / "run.json")
    normalized_payload = _read_json(run_dir / "actions_normalized.json")
    execution_plan = _read_json(run_dir / "execution_plan.json")

    if run_payload.get("status") != "ok":
        errors.append(f"run.json status must be 'ok' (got {run_payload.get('status')!r})")
    result = run_payload.get("result")
    if not isinstance(result, dict):
        errors.append("run.json.result must be object")
        return False, errors, {}
    if result.get("dry_run") is not True:
        errors.append("run.json.result.dry_run must be true")

    action_count = int(result.get("action_count", 0))
    step_count = int(result.get("step_count", 0))
    if action_count < min_action_count:
        errors.append(f"action_count={action_count} < min_action_count={min_action_count}")
    if step_count < min_step_count:
        errors.append(f"step_count={step_count} < min_step_count={min_step_count}")

    if normalized_payload.get("schema_version") != "automation_plan_v1":
        errors.append("actions_normalized.json.schema_version must be 'automation_plan_v1'")
    if execution_plan.get("dry_run") is not True:
        errors.append("execution_plan.json.dry_run must be true")
    if int(execution_plan.get("step_count", 0)) != step_count:
        errors.append("execution_plan.step_count must match run.json.result.step_count")

    observed = {
        "action_count": action_count,
        "step_count": step_count,
        "schema_version": normalized_payload.get("schema_version"),
    }
    return (not errors), errors, observed


def _check_chain_contract(
    *,
    run_dir: Path,
    min_action_count: int,
    min_step_count: int,
    expected_intent_type: str | None,
) -> tuple[bool, list[str], dict[str, Any]]:
    errors: list[str] = []
    run_payload = _read_json(run_dir / "run.json")
    chain_summary = _read_json(run_dir / "chain_summary.json")
    plan_payload = _read_json(run_dir / "automation_plan.json")

    if run_payload.get("status") != "ok":
        errors.append(f"run.json status must be 'ok' (got {run_payload.get('status')!r})")
    result = run_payload.get("result")
    if not isinstance(result, dict):
        errors.append("run.json.result must be object")
        return False, errors, {}
    if result.get("dry_run_only") is not True:
        errors.append("run.json.result.dry_run_only must be true")
    action_count = int(result.get("action_count", 0))
    step_count = int(result.get("step_count", 0))
    if action_count < min_action_count:
        errors.append(f"action_count={action_count} < min_action_count={min_action_count}")
    if step_count < min_step_count:
        errors.append(f"step_count={step_count} < min_step_count={min_step_count}")

    if chain_summary.get("ok") is not True:
        errors.append("chain_summary.json.ok must be true")
    if plan_payload.get("schema_version") != "automation_plan_v1":
        errors.append("automation_plan.json.schema_version must be 'automation_plan_v1'")

    plan_context = plan_payload.get("context")
    if not isinstance(plan_context, dict):
        errors.append("automation_plan.json.context must be object")
        intent_type = None
    else:
        intent_type = str(plan_context.get("intent_type", "")).strip() or None
        if intent_type is None:
            errors.append("automation_plan.json.context.intent_type must be non-empty")
        elif expected_intent_type and intent_type != expected_intent_type:
            errors.append(
                f"context.intent_type={intent_type!r} != expected_intent_type={expected_intent_type!r}"
            )

    observed = {
        "action_count": action_count,
        "step_count": step_count,
        "schema_version": plan_payload.get("schema_version"),
        "intent_type": intent_type,
    }
    return (not errors), errors, observed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate automation smoke run artifacts against pass/fail contract."
    )
    parser.add_argument(
        "--mode",
        choices=("dry_run", "intent_chain"),
        required=True,
        help="Contract mode.",
    )
    parser.add_argument("--runs-dir", type=Path, required=True, help="Base runs directory.")
    parser.add_argument("--run-dir", type=Path, default=None, help="Specific run directory (optional).")
    parser.add_argument("--min-action-count", type=int, default=1, help="Minimum expected action count.")
    parser.add_argument("--min-step-count", type=int, default=1, help="Minimum expected step count.")
    parser.add_argument(
        "--expected-intent-type",
        default=None,
        help="Optional expected intent_type for mode=intent_chain.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional output path for machine-readable check summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary_payload: dict[str, Any] = {
        "mode": args.mode,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "status": "error",
        "run_dir": None,
        "thresholds": {
            "min_action_count": args.min_action_count,
            "min_step_count": args.min_step_count,
            "expected_intent_type": args.expected_intent_type,
        },
        "observed": {},
        "violations": [],
        "error": None,
    }

    try:
        suffix = "-automation-dry-run" if args.mode == "dry_run" else "-automation-intent-chain-smoke"
        run_dir = args.run_dir if args.run_dir is not None else _latest_run_dir(args.runs_dir, suffix)
        summary_payload["run_dir"] = str(run_dir)

        if args.mode == "dry_run":
            ok, errors, observed = _check_dry_run_contract(
                run_dir=run_dir,
                min_action_count=args.min_action_count,
                min_step_count=args.min_step_count,
            )
        else:
            ok, errors, observed = _check_chain_contract(
                run_dir=run_dir,
                min_action_count=args.min_action_count,
                min_step_count=args.min_step_count,
                expected_intent_type=args.expected_intent_type,
            )

        summary_payload["ok"] = ok
        summary_payload["status"] = "ok" if ok else "error"
        summary_payload["observed"] = observed
        summary_payload["violations"] = errors

        print(f"[check_automation_smoke_contract] mode={args.mode} run_dir={run_dir}")
        if ok:
            print("[check_automation_smoke_contract] status=ok")
            exit_code = 0
        else:
            for error in errors:
                print(f"[check_automation_smoke_contract] violation: {error}")
            exit_code = 2
    except Exception as exc:
        summary_payload["error"] = str(exc)
        print(f"[check_automation_smoke_contract] error: {exc}")
        exit_code = 2

    if args.summary_json is not None:
        _write_json(args.summary_json, summary_payload)
        print(f"[check_automation_smoke_contract] summary_json={args.summary_json}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
