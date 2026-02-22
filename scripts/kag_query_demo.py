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

from src.kag import query_kag_graph


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-kag-query")
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


def _load_graph_payload(graph_path: Path) -> dict[str, Any]:
    if not graph_path.exists():
        raise FileNotFoundError(f"KAG graph path does not exist: {graph_path}")
    if not graph_path.is_file():
        raise ValueError(f"KAG graph path must be a file: {graph_path}")
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("KAG graph payload must be JSON object.")
    return payload


def run_kag_query_demo(
    *,
    graph_path: Path,
    query: str,
    topk: int = 5,
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
        "mode": "kag_query_demo",
        "status": "started",
        "request": {
            "graph_path": str(graph_path),
            "query": query,
            "topk": topk,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "results_json": str(results_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        graph_payload = _load_graph_payload(graph_path)
        results = query_kag_graph(graph_payload, query=query, topk=topk)
        output_payload = {"query": query, "topk": topk, "results": results, "count": len(results)}
        _write_json(results_json_path, output_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = {"count": len(results)}
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "results_payload": output_payload,
            "ok": True,
        }
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, FileNotFoundError):
            run_payload["error_code"] = "graph_path_missing"
        elif isinstance(exc, ValueError):
            run_payload["error_code"] = "invalid_input"
        else:
            run_payload["error_code"] = "kag_query_failed"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "results_payload": None,
            "ok": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query KAG baseline graph and return top-k doc citations.")
    parser.add_argument("--graph", type=Path, required=True, help="Path to kag_graph.json artifact.")
    parser.add_argument("--query", required=True, help="User query.")
    parser.add_argument("--topk", type=int, default=5, help="Top-k result count.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_kag_query_demo(
        graph_path=args.graph,
        query=args.query,
        topk=args.topk,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[kag_query_demo] run_dir: {run_dir}")
    print(f"[kag_query_demo] run_json: {run_dir / 'run.json'}")
    print(f"[kag_query_demo] results_json: {run_dir / 'kag_query_results.json'}")
    if not result["ok"]:
        print(f"[kag_query_demo] error: {result['run_payload']['error']}")
        return 2
    print(f"[kag_query_demo] results_count: {result['results_payload']['count']}")
    for index, item in enumerate(result["results_payload"]["results"], start=1):
        citation = item["citation"]
        print(
            f"[kag_query_demo] #{index} score={item['score']} "
            f"id={citation['id']} source={citation['source']} path={citation['path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
