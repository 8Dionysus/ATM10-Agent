from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.combo_a_profile import (
    DEFAULT_COMBO_A_NEO4J_DATABASE,
    DEFAULT_COMBO_A_NEO4J_URL,
    DEFAULT_COMBO_A_NEO4J_USER,
    DEFAULT_COMBO_A_QDRANT_URL,
    qdrant_host_port_from_url,
    seed_combo_a_fixture_data,
)
from scripts.gateway_v1_http_service import create_app, map_gateway_http_status


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_run_dir(runs_dir: Path, *, scenario: str, now: datetime) -> Path:
    base_name = now.strftime(f"%Y%m%d_%H%M%S-gateway-v1-http-smoke-{scenario}")
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


def _percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    if percentile <= 0:
        return sorted_values[0]
    if percentile >= 100:
        return sorted_values[-1]
    rank = math.ceil((percentile / 100.0) * len(sorted_values))
    index = min(max(rank - 1, 0), len(sorted_values) - 1)
    return sorted_values[index]


def _build_error_buckets(request_rows: list[Mapping[str, Any]]) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for row in request_rows:
        error_code = row.get("error_code")
        key = "none" if error_code in (None, "", "None") else str(error_code)
        buckets[key] = buckets.get(key, 0) + 1
    return buckets


def _build_scenario_requests(
    scenario: str,
    *,
    combo_a_seed: Mapping[str, Any] | None = None,
    combo_a_qdrant_url: str = DEFAULT_COMBO_A_QDRANT_URL,
    combo_a_neo4j_url: str = DEFAULT_COMBO_A_NEO4J_URL,
    combo_a_neo4j_database: str = DEFAULT_COMBO_A_NEO4J_DATABASE,
    combo_a_neo4j_user: str = DEFAULT_COMBO_A_NEO4J_USER,
    combo_a_neo4j_password: str | None = None,
) -> list[dict[str, Any]]:
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
    if scenario == "hybrid":
        return [
            {
                "schema_version": "gateway_request_v1",
                "operation": "hybrid_query",
                "payload": {
                    "query": "steel tools",
                    "docs_path": str(Path("tests") / "fixtures" / "retrieval_docs_sample.jsonl"),
                    "topk": 5,
                    "candidate_k": 10,
                    "reranker": "none",
                    "max_entities_per_doc": 128,
                },
            }
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
    if scenario == "combo_a":
        if combo_a_seed is None:
            raise ValueError("combo_a_seed is required for scenario='combo_a'.")
        qdrant = combo_a_seed.get("qdrant")
        neo4j = combo_a_seed.get("neo4j")
        qdrant = qdrant if isinstance(qdrant, Mapping) else {}
        neo4j = neo4j if isinstance(neo4j, Mapping) else {}
        qdrant_host, qdrant_port = qdrant_host_port_from_url(combo_a_qdrant_url)
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
                    "backend": "qdrant",
                    "query": "steel tools",
                    "collection": qdrant.get("collection"),
                    "host": qdrant_host,
                    "port": qdrant_port,
                    "vector_size": qdrant.get("vector_size", 64),
                    "topk": 3,
                    "candidate_k": 10,
                    "reranker": "none",
                },
            },
            {
                "schema_version": "gateway_request_v1",
                "operation": "kag_query",
                "payload": {
                    "backend": "neo4j",
                    "query": "steel tools",
                    "topk": 5,
                    "neo4j_url": combo_a_neo4j_url,
                    "neo4j_database": combo_a_neo4j_database,
                    "neo4j_user": combo_a_neo4j_user,
                    "neo4j_password": combo_a_neo4j_password,
                    "neo4j_dataset_tag": neo4j.get("dataset_tag"),
                },
            },
            {
                "schema_version": "gateway_request_v1",
                "operation": "hybrid_query",
                "payload": {
                    "profile": "combo_a",
                    "query": "steel tools",
                    "retrieval_backend": "qdrant",
                    "kag_backend": "neo4j",
                    "collection": qdrant.get("collection"),
                    "host": qdrant_host,
                    "port": qdrant_port,
                    "vector_size": qdrant.get("vector_size", 64),
                    "neo4j_url": combo_a_neo4j_url,
                    "neo4j_database": combo_a_neo4j_database,
                    "neo4j_user": combo_a_neo4j_user,
                    "neo4j_password": combo_a_neo4j_password,
                    "neo4j_dataset_tag": neo4j.get("dataset_tag"),
                    "topk": 5,
                    "candidate_k": 10,
                    "reranker": "none",
                    "max_entities_per_doc": 128,
                },
            },
        ]
    raise ValueError(f"Unsupported scenario: {scenario!r}")


def run_gateway_v1_http_smoke(
    *,
    scenario: str,
    runs_dir: Path = Path("runs"),
    summary_json: Path | None = None,
    combo_a_docs_path: Path = Path("tests") / "fixtures" / "kag_neo4j_docs_sample.jsonl",
    combo_a_qdrant_url: str = DEFAULT_COMBO_A_QDRANT_URL,
    combo_a_neo4j_url: str = DEFAULT_COMBO_A_NEO4J_URL,
    combo_a_neo4j_database: str = DEFAULT_COMBO_A_NEO4J_DATABASE,
    combo_a_neo4j_user: str = DEFAULT_COMBO_A_NEO4J_USER,
    combo_a_neo4j_password: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if scenario not in {"core", "hybrid", "automation", "combo_a"}:
        raise ValueError("scenario must be one of ['core', 'hybrid', 'automation', 'combo_a'].")
    if now is None:
        now = datetime.now(timezone.utc)

    try:
        from fastapi.testclient import TestClient
    except Exception as exc:  # pragma: no cover - dependency presence
        raise RuntimeError("FastAPI TestClient is required for gateway_v1_http_smoke.") from exc

    run_dir = _create_run_dir(runs_dir, scenario=scenario, now=now)
    run_json_path = run_dir / "run.json"
    summary_path = summary_json if summary_json is not None else (runs_dir / "gateway_http_smoke_summary.json")
    gateway_runs_dir = run_dir / "gateway_http_runs"
    combo_a_seed_result = None
    combo_a_seed_summary = None
    if scenario == "combo_a":
        qdrant_host, qdrant_port = qdrant_host_port_from_url(combo_a_qdrant_url)
        combo_a_seed_result = seed_combo_a_fixture_data(
            scope="gateway_http_smoke",
            docs_path=combo_a_docs_path,
            runs_dir=run_dir / "combo_a_seed",
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
            neo4j_url=combo_a_neo4j_url,
            neo4j_database=combo_a_neo4j_database,
            neo4j_user=combo_a_neo4j_user,
            neo4j_password=combo_a_neo4j_password,
            now=now,
        )
        if not combo_a_seed_result["ok"]:
            raise RuntimeError(str(combo_a_seed_result["run_payload"].get("error", "combo_a seed failed")))
        combo_a_seed_summary = {
            "qdrant": {
                "collection": combo_a_seed_result["summary_payload"]["qdrant"]["collection"],
                "vector_size": combo_a_seed_result["summary_payload"]["qdrant"]["vector_size"],
            },
            "neo4j": {
                "dataset_tag": combo_a_seed_result["summary_payload"]["neo4j"]["dataset_tag"],
            },
            "paths": combo_a_seed_result["summary_payload"]["paths"],
        }
    requests = _build_scenario_requests(
        scenario,
        combo_a_seed=combo_a_seed_summary,
        combo_a_qdrant_url=combo_a_qdrant_url,
        combo_a_neo4j_url=combo_a_neo4j_url,
        combo_a_neo4j_database=combo_a_neo4j_database,
        combo_a_neo4j_user=combo_a_neo4j_user,
        combo_a_neo4j_password=combo_a_neo4j_password,
    )
    started_at_utc = _utc_now()
    started_at_perf = time.perf_counter()

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "gateway_v1_http_smoke",
        "status": "started",
        "scenario": scenario,
        "started_at_utc": started_at_utc,
        "request_count": len(requests),
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_path),
            "gateway_runs_dir": str(gateway_runs_dir),
            "combo_a_seed_run_dir": (
                None if combo_a_seed_result is None else str(combo_a_seed_result["run_dir"])
            ),
        },
    }
    _write_json(run_json_path, run_payload)

    app = create_app(
        runs_dir=gateway_runs_dir,
        qdrant_url=combo_a_qdrant_url if scenario == "combo_a" else None,
        neo4j_url=combo_a_neo4j_url if scenario == "combo_a" else None,
        neo4j_database=combo_a_neo4j_database,
        neo4j_user=combo_a_neo4j_user,
    )
    request_summaries: list[dict[str, Any]] = []
    all_ok = True
    with TestClient(app) as client:
        for request in requests:
            request_started = time.perf_counter()
            http_response = client.post("/v1/gateway", json=request)
            latency_ms = round((time.perf_counter() - request_started) * 1000.0, 3)
            response_json = http_response.json()
            expected_http_status = map_gateway_http_status(response_json)
            row_ok = (
                http_response.status_code == expected_http_status
                and str(response_json.get("status")) == "ok"
            )
            row = {
                "operation": str(response_json.get("operation")),
                "status": str(response_json.get("status")),
                "http_status": int(http_response.status_code),
                "expected_http_status": int(expected_http_status),
                "error_code": response_json.get("error_code"),
                "ok": row_ok,
                "latency_ms": latency_ms,
                "run_dir": response_json.get("artifacts", {}).get("run_dir"),
                "run_json": response_json.get("artifacts", {}).get("run_json"),
            }
            request_summaries.append(row)
            if not row_ok:
                all_ok = False

    finished_at_utc = _utc_now()
    duration_ms = round((time.perf_counter() - started_at_perf) * 1000.0, 3)
    latency_values = [float(item["latency_ms"]) for item in request_summaries]
    failed_requests_count = sum(1 for item in request_summaries if not bool(item["ok"]))
    summary_payload = {
        "profile": "combo_a" if scenario == "combo_a" else "baseline_first",
        "surface": "http",
        "scenario": scenario,
        "ok": all_ok,
        "status": "ok" if all_ok else "error",
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "duration_ms": duration_ms,
        "request_count": len(request_summaries),
        "failed_requests_count": failed_requests_count,
        "latency_p50_ms": _percentile_nearest_rank(latency_values, 50.0),
        "latency_p95_ms": _percentile_nearest_rank(latency_values, 95.0),
        "latency_max_ms": max(latency_values) if latency_values else None,
        "error_buckets": _build_error_buckets(request_summaries),
        "requests": request_summaries,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_path),
            "gateway_runs_dir": str(gateway_runs_dir),
        },
        "combo_a_seed": combo_a_seed_summary,
    }
    _write_json(summary_path, summary_payload)

    run_payload["status"] = summary_payload["status"]
    run_payload["result"] = {
        "ok": summary_payload["ok"],
        "request_count": summary_payload["request_count"],
        "failed_requests_count": summary_payload["failed_requests_count"],
    }
    _write_json(run_json_path, run_payload)
    return {
        "ok": all_ok,
        "run_dir": run_dir,
        "run_payload": run_payload,
        "summary_payload": summary_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gateway v1 HTTP smoke scenarios (core|hybrid|automation|combo_a).")
    parser.add_argument(
        "--scenario",
        choices=("core", "hybrid", "automation", "combo_a"),
        required=True,
        help="Smoke scenario name.",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional output path for machine-readable smoke summary.",
    )
    parser.add_argument(
        "--combo-a-docs",
        type=Path,
        default=Path("tests") / "fixtures" / "kag_neo4j_docs_sample.jsonl",
        help="Docs fixture used to seed Combo A smoke backends.",
    )
    parser.add_argument("--qdrant-url", default=DEFAULT_COMBO_A_QDRANT_URL, help="Combo A Qdrant URL.")
    parser.add_argument("--neo4j-url", default=DEFAULT_COMBO_A_NEO4J_URL, help="Combo A Neo4j URL.")
    parser.add_argument(
        "--neo4j-database",
        default=DEFAULT_COMBO_A_NEO4J_DATABASE,
        help="Combo A Neo4j database name.",
    )
    parser.add_argument(
        "--neo4j-user",
        default=DEFAULT_COMBO_A_NEO4J_USER,
        help="Combo A Neo4j user.",
    )
    parser.add_argument(
        "--neo4j-password",
        default=None,
        help="Combo A Neo4j password (or use NEO4J_PASSWORD env var).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_v1_http_smoke(
        scenario=args.scenario,
        runs_dir=args.runs_dir,
        summary_json=args.summary_json,
        combo_a_docs_path=args.combo_a_docs,
        combo_a_qdrant_url=args.qdrant_url,
        combo_a_neo4j_url=args.neo4j_url,
        combo_a_neo4j_database=args.neo4j_database,
        combo_a_neo4j_user=args.neo4j_user,
        combo_a_neo4j_password=args.neo4j_password,
    )
    run_dir = result["run_dir"]
    summary_payload = result["summary_payload"]
    print(f"[gateway_v1_http_smoke] scenario: {args.scenario}")
    print(f"[gateway_v1_http_smoke] run_dir: {run_dir}")
    print(f"[gateway_v1_http_smoke] run_json: {run_dir / 'run.json'}")
    print(f"[gateway_v1_http_smoke] summary_json: {summary_payload['paths']['summary_json']}")
    print(f"[gateway_v1_http_smoke] status: {summary_payload['status']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
