from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kag import query_kag_neo4j


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-kag-query-neo4j")
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


def _resolve_password(password: str | None) -> str:
    if password:
        return password
    from_env = os.environ.get("NEO4J_PASSWORD", "").strip()
    if from_env:
        return from_env
    raise ValueError("Neo4j password is required: pass --password or set NEO4J_PASSWORD.")


def run_kag_query_neo4j(
    *,
    query: str,
    topk: int,
    neo4j_url: str,
    neo4j_database: str,
    neo4j_user: str,
    neo4j_password: str | None,
    timeout_sec: float = 10.0,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    results_json_path = run_dir / "kag_query_results.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "kag_query_neo4j",
        "status": "started",
        "request": {
            "query": query,
            "topk": topk,
            "neo4j_url": neo4j_url,
            "neo4j_database": neo4j_database,
            "neo4j_user": neo4j_user,
            "timeout_sec": timeout_sec,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "results_json": str(results_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        password = _resolve_password(neo4j_password)
        results = query_kag_neo4j(
            url=neo4j_url,
            database=neo4j_database,
            user=neo4j_user,
            password=password,
            query=query,
            topk=topk,
            timeout_sec=timeout_sec,
        )
        results_payload = {
            "query": query,
            "topk": topk,
            "count": len(results),
            "results": results,
        }
        _write_json(results_json_path, results_payload)
        run_payload["status"] = "ok"
        run_payload["result"] = {"count": len(results)}
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "results_payload": results_payload,
        }
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, ValueError):
            run_payload["error_code"] = "invalid_input"
        else:
            run_payload["error_code"] = "kag_query_neo4j_failed"
        _write_json(run_json_path, run_payload)
        return {"ok": False, "run_dir": run_dir, "run_payload": run_payload, "results_payload": None}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query KAG documents directly from Neo4j graph.")
    parser.add_argument("--query", required=True, help="User query text.")
    parser.add_argument("--topk", type=int, default=5, help="Top-k result count.")
    parser.add_argument("--neo4j-url", default="http://127.0.0.1:7474", help="Neo4j HTTP base URL.")
    parser.add_argument("--neo4j-database", default="neo4j", help="Neo4j database name.")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username.")
    parser.add_argument("--password", default=None, help="Neo4j password (or use NEO4J_PASSWORD env var).")
    parser.add_argument("--timeout-sec", type=float, default=10.0, help="HTTP timeout for Neo4j requests.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_kag_query_neo4j(
        query=args.query,
        topk=args.topk,
        neo4j_url=args.neo4j_url,
        neo4j_database=args.neo4j_database,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.password,
        timeout_sec=args.timeout_sec,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[kag_query_neo4j] run_dir: {run_dir}")
    print(f"[kag_query_neo4j] run_json: {run_dir / 'run.json'}")
    print(f"[kag_query_neo4j] results_json: {run_dir / 'kag_query_results.json'}")
    if not result["ok"]:
        print(f"[kag_query_neo4j] error: {result['run_payload']['error']}")
        return 2
    print(f"[kag_query_neo4j] results_count: {result['results_payload']['count']}")
    for index, item in enumerate(result["results_payload"]["results"], start=1):
        citation = item["citation"]
        print(
            f"[kag_query_neo4j] #{index} score={item['score']} "
            f"id={citation['id']} source={citation['source']} path={citation['path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
