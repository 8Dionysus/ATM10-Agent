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

from src.rag.retrieval import ingest_docs_qdrant, load_docs


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
    parser = argparse.ArgumentParser(description="Ingest normalized JSONL docs into Qdrant collection.")
    parser.add_argument(
        "--in",
        dest="input_path",
        type=Path,
        default=Path("data") / "ftbquests_norm",
        help="Path to JSONL file or directory with *.jsonl files.",
    )
    parser.add_argument("--collection", default="atm10", help="Qdrant collection name (default: atm10).")
    parser.add_argument("--host", default="127.0.0.1", help="Qdrant host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=6333, help="Qdrant port (default: 6333).")
    parser.add_argument("--vector-size", type=int, default=64, help="Embedding vector size (default: 64).")
    parser.add_argument("--timeout-sec", type=float, default=10.0, help="HTTP timeout for Qdrant requests.")
    parser.add_argument("--batch-size", type=int, default=128, help="Upsert batch size (default: 128).")
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
    summary_path = run_dir / "ingest_summary.json"

    try:
        docs = load_docs(args.input_path)
        summary = ingest_docs_qdrant(
            docs,
            collection=args.collection,
            host=args.host,
            port=args.port,
            vector_size=args.vector_size,
            timeout_sec=args.timeout_sec,
            batch_size=args.batch_size,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        _write_json(
            run_json_path,
            {
                "timestamp_utc": now.isoformat(),
                "mode": "ingest_qdrant",
                "status": "error",
                "error": str(exc),
                "paths": {
                    "input": str(args.input_path),
                    "run_dir": str(run_dir),
                },
            },
        )
        print(f"[ingest_qdrant] error: {exc}")
        print(f"[ingest_qdrant] run_dir: {run_dir}")
        return 2

    run_payload = {
        "timestamp_utc": now.isoformat(),
        "mode": "ingest_qdrant",
        "status": "ok",
        "paths": {
            "input": str(args.input_path),
            "run_dir": str(run_dir),
            "summary_json": str(summary_path),
        },
        "qdrant": {
            "collection": args.collection,
            "host": args.host,
            "port": args.port,
            "vector_size": args.vector_size,
            "timeout_sec": args.timeout_sec,
            "batch_size": args.batch_size,
        },
    }
    _write_json(run_json_path, run_payload)
    _write_json(summary_path, summary)

    print(f"[ingest_qdrant] run_dir: {run_dir}")
    print(f"[ingest_qdrant] input: {args.input_path}")
    print(f"[ingest_qdrant] summary_json: {summary_path}")
    print(
        "[ingest_qdrant] "
        f"collection={args.collection} docs_ingested={summary['docs_ingested']} "
        f"upsert_calls={summary['upsert_calls']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
