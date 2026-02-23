from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts.automation_dry_run import run_automation_dry_run
    from scripts.intent_to_automation_plan import run_intent_to_automation_plan
except ModuleNotFoundError:  # Supports direct execution: `python scripts/automation_intent_chain_smoke.py ...`
    from automation_dry_run import run_automation_dry_run
    from intent_to_automation_plan import run_intent_to_automation_plan


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-automation-intent-chain-smoke")
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


def run_automation_intent_chain_smoke(
    *,
    intent_json: Path,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    generated_plan_path = run_dir / "automation_plan.json"
    chain_summary_path = run_dir / "chain_summary.json"
    child_runs_dir = run_dir / "child_runs"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "automation_intent_chain_smoke",
        "status": "started",
        "request": {"intent_json": str(intent_json)},
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "generated_plan_json": str(generated_plan_path),
            "chain_summary_json": str(chain_summary_path),
            "child_runs_dir": str(child_runs_dir),
        },
    }
    _write_json(run_json_path, run_payload)

    adapter_result = run_intent_to_automation_plan(
        intent_json=intent_json,
        runs_dir=child_runs_dir,
        plan_out=generated_plan_path,
        now=now,
    )

    if not adapter_result["ok"]:
        run_payload["status"] = "error"
        run_payload["error_code"] = "intent_adapter_failed"
        run_payload["error"] = adapter_result["run_payload"]["error"]
        run_payload["child_runs"] = {"intent_adapter": str(adapter_result["run_dir"])}
        _write_json(run_json_path, run_payload)
        _write_json(
            chain_summary_path,
            {
                "ok": False,
                "intent_adapter": {
                    "ok": False,
                    "run_dir": str(adapter_result["run_dir"]),
                    "error_code": adapter_result["run_payload"].get("error_code"),
                },
                "automation_dry_run": None,
            },
        )
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "chain_summary": None,
        }

    dry_run_result = run_automation_dry_run(
        plan_json=generated_plan_path,
        runs_dir=child_runs_dir,
        now=now,
    )

    if not dry_run_result["ok"]:
        run_payload["status"] = "error"
        run_payload["error_code"] = "automation_dry_run_failed"
        run_payload["error"] = dry_run_result["run_payload"]["error"]
        run_payload["child_runs"] = {
            "intent_adapter": str(adapter_result["run_dir"]),
            "automation_dry_run": str(dry_run_result["run_dir"]),
        }
        _write_json(run_json_path, run_payload)
        _write_json(
            chain_summary_path,
            {
                "ok": False,
                "intent_adapter": {"ok": True, "run_dir": str(adapter_result["run_dir"])},
                "automation_dry_run": {
                    "ok": False,
                    "run_dir": str(dry_run_result["run_dir"]),
                    "error_code": dry_run_result["run_payload"].get("error_code"),
                },
            },
        )
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "chain_summary": None,
        }

    chain_summary: dict[str, Any] = {
        "ok": True,
        "intent_adapter": {
            "ok": True,
            "run_dir": str(adapter_result["run_dir"]),
            "intent_type": adapter_result["plan_payload"]["context"]["intent_type"],
            "action_count": len(adapter_result["plan_payload"]["actions"]),
        },
        "automation_dry_run": {
            "ok": True,
            "run_dir": str(dry_run_result["run_dir"]),
            "step_count": dry_run_result["run_payload"]["result"]["step_count"],
            "estimated_total_duration_ms": dry_run_result["run_payload"]["result"][
                "estimated_total_duration_ms"
            ],
        },
        "paths": {
            "generated_plan_json": str(generated_plan_path),
        },
    }
    _write_json(chain_summary_path, chain_summary)

    run_payload["status"] = "ok"
    run_payload["result"] = {
        "dry_run_only": True,
        "intent_type": chain_summary["intent_adapter"]["intent_type"],
        "action_count": chain_summary["intent_adapter"]["action_count"],
        "step_count": chain_summary["automation_dry_run"]["step_count"],
    }
    run_payload["child_runs"] = {
        "intent_adapter": str(adapter_result["run_dir"]),
        "automation_dry_run": str(dry_run_result["run_dir"]),
    }
    _write_json(run_json_path, run_payload)
    return {
        "ok": True,
        "run_dir": run_dir,
        "run_payload": run_payload,
        "chain_summary": chain_summary,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run dry-run chain: intent payload -> automation_plan_v1 -> automation_dry_run."
    )
    parser.add_argument("--intent-json", type=Path, required=True, help="Path to intent JSON payload.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_automation_intent_chain_smoke(
        intent_json=args.intent_json,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[automation_intent_chain_smoke] run_dir: {run_dir}")
    print(f"[automation_intent_chain_smoke] run_json: {run_dir / 'run.json'}")
    print(f"[automation_intent_chain_smoke] chain_summary_json: {run_dir / 'chain_summary.json'}")
    print(f"[automation_intent_chain_smoke] generated_plan_json: {run_dir / 'automation_plan.json'}")
    if not result["ok"]:
        print(f"[automation_intent_chain_smoke] error: {result['run_payload']['error']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
