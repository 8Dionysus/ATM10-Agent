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

from src.hybrid import execute_hybrid_baseline_query


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-hybrid-query")
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


def run_hybrid_query(
    *,
    query: str,
    docs_path: Path,
    topk: int = 5,
    candidate_k: int = 10,
    reranker: str = "none",
    reranker_model: str = "Qwen/Qwen3-Reranker-0.6B",
    reranker_runtime: str = "torch",
    reranker_device: str = "AUTO",
    reranker_max_length: int = 1024,
    max_entities_per_doc: int = 128,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    results_json_path = run_dir / "hybrid_query_results.json"
    graph_json_path = run_dir / "kag_graph.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "hybrid_query_demo",
        "status": "started",
        "request": {
            "query": query,
            "docs_path": str(docs_path),
            "topk": topk,
            "candidate_k": candidate_k,
            "reranker": reranker,
            "reranker_model": reranker_model if reranker == "qwen3" else None,
            "reranker_runtime": reranker_runtime if reranker == "qwen3" else None,
            "reranker_device": reranker_device if reranker == "qwen3" else None,
            "reranker_max_length": reranker_max_length if reranker == "qwen3" else None,
            "max_entities_per_doc": max_entities_per_doc,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "results_json": str(results_json_path),
            "kag_graph_json": str(graph_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        results_payload = execute_hybrid_baseline_query(
            query=query,
            docs_path=docs_path,
            topk=topk,
            candidate_k=candidate_k,
            reranker=reranker,
            reranker_model=reranker_model,
            reranker_runtime=reranker_runtime,
            reranker_device=reranker_device,
            reranker_max_length=reranker_max_length,
            max_entities_per_doc=max_entities_per_doc,
        )
        graph_payload = results_payload.pop("graph_payload", None)
        if isinstance(graph_payload, dict):
            _write_json(graph_json_path, graph_payload)
        results_out_payload = {
            **results_payload,
            "query": query,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "results_json": str(results_json_path),
                "kag_graph_json": str(graph_json_path) if isinstance(graph_payload, dict) else None,
            },
        }
        _write_json(results_json_path, results_out_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "planner_mode": results_out_payload["planner_mode"],
            "planner_status": results_out_payload["planner_status"],
            "degraded": bool(results_out_payload["degraded"]),
            "retrieval_results_count": int(results_out_payload["retrieval_results_count"]),
            "kag_results_count": int(results_out_payload["kag_results_count"]),
            "results_count": int(results_out_payload["results_count"]),
        }
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "results_payload": results_out_payload,
            "ok": True,
        }
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, FileNotFoundError):
            run_payload["error_code"] = "input_path_missing"
        elif isinstance(exc, ValueError):
            run_payload["error_code"] = "invalid_input"
        else:
            run_payload["error_code"] = "hybrid_query_failed"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "results_payload": None,
            "ok": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run hybrid retrieval-first KAG expansion query and write machine-readable artifacts."
    )
    parser.add_argument("--docs", dest="docs_path", type=Path, required=True, help="Path to JSONL docs input.")
    parser.add_argument("--query", required=True, help="User query.")
    parser.add_argument("--topk", type=int, default=5, help="Final merged top-k result count.")
    parser.add_argument(
        "--candidate-k",
        type=int,
        default=10,
        help="First-stage retrieval candidate pool size before reranking.",
    )
    parser.add_argument(
        "--reranker",
        choices=("none", "qwen3"),
        default="none",
        help="Second-stage reranker for retrieval seeds.",
    )
    parser.add_argument(
        "--reranker-model",
        default="Qwen/Qwen3-Reranker-0.6B",
        help="Reranker model id for --reranker qwen3.",
    )
    parser.add_argument(
        "--reranker-runtime",
        choices=("torch", "openvino"),
        default="torch",
        help="Runtime for qwen3 reranker.",
    )
    parser.add_argument(
        "--reranker-device",
        default="AUTO",
        help="Device for qwen3 reranker when using openvino runtime.",
    )
    parser.add_argument(
        "--reranker-max-length",
        type=int,
        default=1024,
        help="Max tokenized length for reranker input.",
    )
    parser.add_argument("--max-entities-per-doc", type=int, default=128, help="Entity cap per document.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_hybrid_query(
        query=args.query,
        docs_path=args.docs_path,
        topk=args.topk,
        candidate_k=args.candidate_k,
        reranker=args.reranker,
        reranker_model=args.reranker_model,
        reranker_runtime=args.reranker_runtime,
        reranker_device=args.reranker_device,
        reranker_max_length=args.reranker_max_length,
        max_entities_per_doc=args.max_entities_per_doc,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[hybrid_query_demo] run_dir: {run_dir}")
    print(f"[hybrid_query_demo] run_json: {run_dir / 'run.json'}")
    print(f"[hybrid_query_demo] results_json: {run_dir / 'hybrid_query_results.json'}")
    if not result["ok"]:
        print(f"[hybrid_query_demo] error: {result['run_payload']['error']}")
        return 2

    results_payload = result["results_payload"]
    print(f"[hybrid_query_demo] planner_status: {results_payload['planner_status']}")
    print(f"[hybrid_query_demo] degraded: {results_payload['degraded']}")
    print(f"[hybrid_query_demo] results_count: {results_payload['results_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
