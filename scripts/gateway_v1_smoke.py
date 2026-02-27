from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.gateway_v1_local import run_gateway_request


def _create_run_dir(runs_dir: Path, *, scenario: str, now: datetime) -> Path:
    base_name = now.strftime(f"%Y%m%d_%H%M%S-gateway-v1-smoke-{scenario}")
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


def _build_scenario_requests(scenario: str) -> list[dict[str, Any]]:
    if scenario == "core":
        return [
            {
                "schema_version": "gateway_request_v1",
                "operation": "health",
                "payload": {},
            },
            {
                "schema_version": "gateway_request_v1",
                "operation": "retrieval_query",
                "payload": {
                    "query": "mekanism steel",
                    "docs_path": str(Path("tests") / "fixtures" / "retrieval_docs_sample.jsonl"),
                    "topk": 3,
                    "candidate_k": 10,
                    "reranker": "none",
                },
            },
            {
                "schema_version": "gateway_request_v1",
                "operation": "kag_query",
                "payload": {
                    "backend": "file",
                    "docs_in": str(Path("tests") / "fixtures" / "kag_neo4j_docs_sample.jsonl"),
                    "query": "steel tools",
                    "topk": 5,
                },
            },
        ]
    if scenario == "automation":
        return [
            {
                "schema_version": "gateway_request_v1",
                "operation": "automation_dry_run",
                "payload": {
                    "plan_json": str(Path("tests") / "fixtures" / "automation_plan_quest_book.json"),
                },
            }
        ]
    raise ValueError(f"Unsupported scenario: {scenario!r}")


def run_gateway_v1_smoke(
    *,
    scenario: str,
    runs_dir: Path = Path("runs"),
    summary_json: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if scenario not in {"core", "automation"}:
        raise ValueError("scenario must be one of ['core', 'automation'].")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, scenario=scenario, now=now)
    run_json_path = run_dir / "run.json"
    summary_path = summary_json if summary_json is not None else (runs_dir / "gateway_smoke_summary.json")
    gateway_runs_dir = run_dir / "gateway_runs"
    requests = _build_scenario_requests(scenario)

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "gateway_v1_smoke",
        "status": "started",
        "scenario": scenario,
        "request_count": len(requests),
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_path),
            "gateway_runs_dir": str(gateway_runs_dir),
        },
    }
    _write_json(run_json_path, run_payload)

    request_summaries: list[dict[str, Any]] = []
    all_ok = True
    for request in requests:
        gateway_result = run_gateway_request(
            request_payload=request,
            runs_dir=gateway_runs_dir,
            now=now,
        )
        response_payload = gateway_result["response_payload"]
        summary_row = {
            "operation": response_payload["operation"],
            "status": response_payload["status"],
            "error_code": response_payload["error_code"],
            "run_dir": str(gateway_result["run_dir"]),
            "run_json": gateway_result["run_payload"]["paths"]["run_json"],
            "response_json": gateway_result["run_payload"]["paths"]["response_json"],
        }
        request_summaries.append(summary_row)
        if response_payload["status"] != "ok":
            all_ok = False

    summary_payload = {
        "scenario": scenario,
        "ok": all_ok,
        "status": "ok" if all_ok else "error",
        "request_count": len(request_summaries),
        "requests": request_summaries,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_path),
            "gateway_runs_dir": str(gateway_runs_dir),
        },
    }
    _write_json(summary_path, summary_payload)

    run_payload["status"] = summary_payload["status"]
    run_payload["result"] = {
        "ok": summary_payload["ok"],
        "request_count": summary_payload["request_count"],
    }
    _write_json(run_json_path, run_payload)
    return {
        "ok": all_ok,
        "run_dir": run_dir,
        "run_payload": run_payload,
        "summary_payload": summary_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gateway v1 smoke scenarios (core|automation).")
    parser.add_argument("--scenario", choices=("core", "automation"), required=True, help="Smoke scenario name.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional output path for machine-readable smoke summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_v1_smoke(
        scenario=args.scenario,
        runs_dir=args.runs_dir,
        summary_json=args.summary_json,
    )
    run_dir = result["run_dir"]
    summary_payload = result["summary_payload"]
    print(f"[gateway_v1_smoke] scenario: {args.scenario}")
    print(f"[gateway_v1_smoke] run_dir: {run_dir}")
    print(f"[gateway_v1_smoke] run_json: {run_dir / 'run.json'}")
    print(f"[gateway_v1_smoke] summary_json: {summary_payload['paths']['summary_json']}")
    print(f"[gateway_v1_smoke] status: {summary_payload['status']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
