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

from src.kag import sync_kag_graph_neo4j


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-kag-sync-neo4j")
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


def _load_graph_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"KAG graph path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"KAG graph path must be a file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("KAG graph payload must be JSON object.")
    return payload


def _sync_kag_graph_neo4j_compat(
    graph_payload: dict[str, Any],
    *,
    url: str,
    database: str,
    user: str,
    password: str,
    timeout_sec: float,
    batch_size: int,
    reset_graph: bool,
    dataset_tag: str | None,
) -> dict[str, Any]:
    try:
        return sync_kag_graph_neo4j(
            graph_payload,
            url=url,
            database=database,
            user=user,
            password=password,
            timeout_sec=timeout_sec,
            batch_size=batch_size,
            reset_graph=reset_graph,
            dataset_tag=dataset_tag,
        )
    except TypeError as exc:
        if "dataset_tag" not in str(exc):
            raise
        return sync_kag_graph_neo4j(
            graph_payload,
            url=url,
            database=database,
            user=user,
            password=password,
            timeout_sec=timeout_sec,
            batch_size=batch_size,
            reset_graph=reset_graph,
        )


def run_kag_sync_neo4j(
    *,
    graph_path: Path,
    neo4j_url: str,
    neo4j_database: str,
    neo4j_user: str,
    neo4j_password: str | None,
    dataset_tag: str | None = None,
    reset_graph: bool = False,
    timeout_sec: float = 30.0,
    batch_size: int = 500,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    summary_json_path = run_dir / "neo4j_sync_summary.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "kag_sync_neo4j",
        "status": "started",
        "request": {
            "graph_path": str(graph_path),
            "neo4j_url": neo4j_url,
            "neo4j_database": neo4j_database,
            "neo4j_user": neo4j_user,
            "dataset_tag": dataset_tag,
            "reset_graph": reset_graph,
            "timeout_sec": timeout_sec,
            "batch_size": batch_size,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        password = _resolve_password(neo4j_password)
        graph_payload = _load_graph_payload(graph_path)
        summary = _sync_kag_graph_neo4j_compat(
            graph_payload,
            url=neo4j_url,
            database=neo4j_database,
            user=neo4j_user,
            password=password,
            timeout_sec=timeout_sec,
            batch_size=batch_size,
            reset_graph=reset_graph,
            dataset_tag=dataset_tag,
        )
        _write_json(summary_json_path, summary)
        run_payload["status"] = "ok"
        run_payload["result"] = summary
        _write_json(run_json_path, run_payload)
        return {"ok": True, "run_dir": run_dir, "run_payload": run_payload, "summary": summary}
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, FileNotFoundError):
            run_payload["error_code"] = "graph_path_missing"
        elif isinstance(exc, ValueError):
            run_payload["error_code"] = "invalid_input"
        else:
            run_payload["error_code"] = "kag_sync_neo4j_failed"
        _write_json(run_json_path, run_payload)
        return {"ok": False, "run_dir": run_dir, "run_payload": run_payload, "summary": None}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync file-based KAG graph payload into Neo4j.")
    parser.add_argument("--graph", type=Path, required=True, help="Path to kag_graph.json artifact.")
    parser.add_argument("--neo4j-url", default="http://127.0.0.1:7474", help="Neo4j HTTP base URL.")
    parser.add_argument("--neo4j-database", default="neo4j", help="Neo4j database name.")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username.")
    parser.add_argument("--password", default=None, help="Neo4j password (or use NEO4J_PASSWORD env var).")
    parser.add_argument(
        "--dataset-tag",
        default=None,
        help="Optional dataset tag for isolated fixture syncs and targeted resets.",
    )
    parser.add_argument("--reset-graph", action="store_true", help="Delete existing Doc/Entity nodes before sync.")
    parser.add_argument("--timeout-sec", type=float, default=30.0, help="HTTP timeout for Neo4j requests.")
    parser.add_argument("--batch-size", type=int, default=500, help="Cypher UNWIND batch size.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_kag_sync_neo4j(
        graph_path=args.graph,
        neo4j_url=args.neo4j_url,
        neo4j_database=args.neo4j_database,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.password,
        dataset_tag=args.dataset_tag,
        reset_graph=args.reset_graph,
        timeout_sec=args.timeout_sec,
        batch_size=args.batch_size,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[kag_sync_neo4j] run_dir: {run_dir}")
    print(f"[kag_sync_neo4j] run_json: {run_dir / 'run.json'}")
    print(f"[kag_sync_neo4j] summary_json: {run_dir / 'neo4j_sync_summary.json'}")
    if not result["ok"]:
        print(f"[kag_sync_neo4j] error: {result['run_payload']['error']}")
        return 2
    summary = result["summary"]
    print(
        "[kag_sync_neo4j] "
        f"doc_nodes={summary['doc_nodes']} "
        f"entity_nodes={summary['entity_nodes']} "
        f"mention_edges={summary['mention_edges']} "
        f"cooccurs_edges={summary['cooccurs_edges']} "
        f"query_calls={summary['query_calls']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
