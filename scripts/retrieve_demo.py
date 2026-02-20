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

from src.rag.retrieval import load_docs, retrieve_top_k, retrieve_top_k_qdrant


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrieve top-k docs from in-memory JSONL or Qdrant backend.")
    parser.add_argument(
        "--backend",
        choices=("in_memory", "qdrant"),
        default="in_memory",
        help="Retrieval backend: in_memory (default) or qdrant.",
    )
    parser.add_argument(
        "--in",
        dest="input_path",
        type=Path,
        default=Path("data") / "ftbquests_norm" / "quests.jsonl",
        help="Path to JSONL file or directory with *.jsonl files (used by in_memory backend).",
    )
    parser.add_argument("--query", required=True, help="User query for retrieval.")
    parser.add_argument("--topk", type=int, default=5, help="Number of retrieval results (default: 5).")
    parser.add_argument("--collection", default="atm10", help="Qdrant collection name (default: atm10).")
    parser.add_argument("--host", default="127.0.0.1", help="Qdrant host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=6333, help="Qdrant port (default: 6333).")
    parser.add_argument("--vector-size", type=int, default=64, help="Embedding vector size (default: 64).")
    parser.add_argument("--timeout-sec", type=float, default=10.0, help="HTTP timeout for Qdrant requests.")
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base directory for run artifacts (default: runs).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)
    run_dir = _create_run_dir(args.runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    results_path = run_dir / "retrieval_results.json"

    try:
        if args.backend == "in_memory":
            docs = load_docs(args.input_path)
            results = retrieve_top_k(args.query, docs, topk=args.topk)
        else:
            results = retrieve_top_k_qdrant(
                args.query,
                collection=args.collection,
                topk=args.topk,
                host=args.host,
                port=args.port,
                vector_size=args.vector_size,
                timeout_sec=args.timeout_sec,
            )
    except RuntimeError as exc:
        print(f"[retrieve_demo] backend_error: {exc}")
        return 2

    run_payload = {
        "timestamp_utc": now.isoformat(),
        "mode": "retrieve_demo",
        "backend": args.backend,
        "query": args.query,
        "topk": args.topk,
        "paths": {
            "input": str(args.input_path) if args.backend == "in_memory" else None,
            "run_dir": str(run_dir),
            "results_json": str(results_path),
        },
        "qdrant": {
            "collection": args.collection,
            "host": args.host,
            "port": args.port,
            "vector_size": args.vector_size,
        }
        if args.backend == "qdrant"
        else None,
    }
    _write_json(run_json_path, run_payload)
    _write_json(results_path, {"results": results, "count": len(results)})

    print(f"[retrieve_demo] run_dir: {run_dir}")
    print(f"[retrieve_demo] backend: {args.backend}")
    if args.backend == "in_memory":
        print(f"[retrieve_demo] input: {args.input_path}")
    else:
        print(f"[retrieve_demo] qdrant: {args.host}:{args.port}/{args.collection}")
    print(f"[retrieve_demo] results_json: {results_path}")
    print(f"[retrieve_demo] results_count: {len(results)}")
    for index, result in enumerate(results, start=1):
        citation = result["citation"]
        print(
            f"[retrieve_demo] #{index} score={result['score']} "
            f"id={citation['id']} source={citation['source']} path={citation['path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
