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

from src.agent_core.combo_a_profile import (
    COMBO_A_PROFILE,
    DEFAULT_COMBO_A_NEO4J_DATABASE,
    DEFAULT_COMBO_A_NEO4J_URL,
    DEFAULT_COMBO_A_NEO4J_USER,
    DEFAULT_COMBO_A_QDRANT_COLLECTION,
    DEFAULT_COMBO_A_QDRANT_HOST,
    DEFAULT_COMBO_A_QDRANT_PORT,
    DEFAULT_COMBO_A_QDRANT_VECTOR_SIZE,
    DEFAULT_PROFILE,
    docs_path_required,
    profile_backends,
    resolve_neo4j_password,
)
from src.hybrid import execute_hybrid_query


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
    docs_path: Path | None = None,
    profile: str = DEFAULT_PROFILE,
    retrieval_backend: str | None = None,
    kag_backend: str | None = None,
    topk: int = 5,
    candidate_k: int = 10,
    reranker: str = "none",
    reranker_model: str = "Qwen/Qwen3-Reranker-0.6B",
    reranker_runtime: str = "torch",
    reranker_device: str = "AUTO",
    reranker_max_length: int = 1024,
    max_entities_per_doc: int = 128,
    qdrant_collection: str = DEFAULT_COMBO_A_QDRANT_COLLECTION,
    qdrant_host: str = DEFAULT_COMBO_A_QDRANT_HOST,
    qdrant_port: int = DEFAULT_COMBO_A_QDRANT_PORT,
    qdrant_vector_size: int = DEFAULT_COMBO_A_QDRANT_VECTOR_SIZE,
    qdrant_timeout_sec: float = 10.0,
    neo4j_url: str = DEFAULT_COMBO_A_NEO4J_URL,
    neo4j_database: str = DEFAULT_COMBO_A_NEO4J_DATABASE,
    neo4j_user: str = DEFAULT_COMBO_A_NEO4J_USER,
    neo4j_password: str | None = None,
    neo4j_timeout_sec: float = 10.0,
    neo4j_dataset_tag: str | None = None,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    effective_retrieval_backend = (
        str(retrieval_backend).strip().lower() if retrieval_backend is not None else profile_backends(profile)[0]
    )
    effective_kag_backend = (
        str(kag_backend).strip().lower() if kag_backend is not None else profile_backends(profile)[1]
    )
    docs_path_value = None if docs_path is None else Path(docs_path)
    if docs_path_required(
        retrieval_backend=effective_retrieval_backend,
        kag_backend=effective_kag_backend,
    ) and docs_path_value is None:
        raise ValueError("docs_path is required for the selected hybrid backend combination")

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    results_json_path = run_dir / "hybrid_query_results.json"
    graph_json_path = run_dir / "kag_graph.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "hybrid_query_demo",
        "status": "started",
        "profile": profile,
        "request": {
            "query": query,
            "docs_path": None if docs_path_value is None else str(docs_path_value),
            "retrieval_backend": effective_retrieval_backend,
            "kag_backend": effective_kag_backend,
            "topk": topk,
            "candidate_k": candidate_k,
            "reranker": reranker,
            "reranker_model": reranker_model if reranker == "qwen3" else None,
            "reranker_runtime": reranker_runtime if reranker == "qwen3" else None,
            "reranker_device": reranker_device if reranker == "qwen3" else None,
            "reranker_max_length": reranker_max_length if reranker == "qwen3" else None,
            "max_entities_per_doc": max_entities_per_doc,
            "qdrant_collection": qdrant_collection if effective_retrieval_backend == "qdrant" else None,
            "qdrant_host": qdrant_host if effective_retrieval_backend == "qdrant" else None,
            "qdrant_port": qdrant_port if effective_retrieval_backend == "qdrant" else None,
            "qdrant_vector_size": qdrant_vector_size if effective_retrieval_backend == "qdrant" else None,
            "neo4j_url": neo4j_url if effective_kag_backend == "neo4j" else None,
            "neo4j_database": neo4j_database if effective_kag_backend == "neo4j" else None,
            "neo4j_user": neo4j_user if effective_kag_backend == "neo4j" else None,
            "neo4j_dataset_tag": neo4j_dataset_tag if effective_kag_backend == "neo4j" else None,
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
        resolved_neo4j_password = None
        if effective_kag_backend == "neo4j":
            resolved_neo4j_password = resolve_neo4j_password(neo4j_password)

        results_payload = execute_hybrid_query(
            query=query,
            docs_path=docs_path_value,
            topk=topk,
            candidate_k=candidate_k,
            reranker=reranker,
            reranker_model=reranker_model,
            reranker_runtime=reranker_runtime,
            reranker_device=reranker_device,
            reranker_max_length=reranker_max_length,
            max_entities_per_doc=max_entities_per_doc,
            retrieval_backend=effective_retrieval_backend,
            kag_backend=effective_kag_backend,
            qdrant_collection=qdrant_collection,
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
            qdrant_vector_size=qdrant_vector_size,
            qdrant_timeout_sec=qdrant_timeout_sec,
            neo4j_url=neo4j_url,
            neo4j_database=neo4j_database,
            neo4j_user=neo4j_user,
            neo4j_password=resolved_neo4j_password,
            neo4j_timeout_sec=neo4j_timeout_sec,
            neo4j_dataset_tag=neo4j_dataset_tag,
        )
        graph_payload = results_payload.pop("graph_payload", None)
        if isinstance(graph_payload, dict):
            _write_json(graph_json_path, graph_payload)
        results_out_payload = {
            **results_payload,
            "query": query,
            "profile": profile,
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
            "backend": "hybrid_combo_a" if profile == COMBO_A_PROFILE else "hybrid_baseline",
            "profile": profile,
            "retrieval_backend": effective_retrieval_backend,
            "kag_backend": effective_kag_backend,
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
    parser.add_argument("--docs", dest="docs_path", type=Path, default=None, help="Optional path to JSONL docs input.")
    parser.add_argument("--query", required=True, help="User query.")
    parser.add_argument(
        "--profile",
        choices=(DEFAULT_PROFILE, COMBO_A_PROFILE),
        default=DEFAULT_PROFILE,
        help="Hybrid profile: baseline_first (default) or combo_a.",
    )
    parser.add_argument(
        "--retrieval-backend",
        choices=("in_memory", "qdrant"),
        default=None,
        help="Optional retrieval backend override.",
    )
    parser.add_argument(
        "--kag-backend",
        choices=("file", "neo4j"),
        default=None,
        help="Optional KAG backend override.",
    )
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
    parser.add_argument("--qdrant-collection", default=DEFAULT_COMBO_A_QDRANT_COLLECTION, help="Qdrant collection.")
    parser.add_argument("--qdrant-host", default=DEFAULT_COMBO_A_QDRANT_HOST, help="Qdrant host.")
    parser.add_argument("--qdrant-port", type=int, default=DEFAULT_COMBO_A_QDRANT_PORT, help="Qdrant port.")
    parser.add_argument(
        "--qdrant-vector-size",
        type=int,
        default=DEFAULT_COMBO_A_QDRANT_VECTOR_SIZE,
        help="Qdrant vector size.",
    )
    parser.add_argument("--qdrant-timeout-sec", type=float, default=10.0, help="Qdrant timeout in seconds.")
    parser.add_argument("--neo4j-url", default=DEFAULT_COMBO_A_NEO4J_URL, help="Neo4j HTTP base URL.")
    parser.add_argument("--neo4j-database", default=DEFAULT_COMBO_A_NEO4J_DATABASE, help="Neo4j database name.")
    parser.add_argument("--neo4j-user", default=DEFAULT_COMBO_A_NEO4J_USER, help="Neo4j username.")
    parser.add_argument("--neo4j-password", default=None, help="Neo4j password (or use NEO4J_PASSWORD env var).")
    parser.add_argument(
        "--neo4j-timeout-sec",
        type=float,
        default=10.0,
        help="Neo4j query timeout in seconds.",
    )
    parser.add_argument("--neo4j-dataset-tag", default=None, help="Optional Neo4j dataset tag.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_hybrid_query(
        query=args.query,
        docs_path=args.docs_path,
        profile=args.profile,
        retrieval_backend=args.retrieval_backend,
        kag_backend=args.kag_backend,
        topk=args.topk,
        candidate_k=args.candidate_k,
        reranker=args.reranker,
        reranker_model=args.reranker_model,
        reranker_runtime=args.reranker_runtime,
        reranker_device=args.reranker_device,
        reranker_max_length=args.reranker_max_length,
        max_entities_per_doc=args.max_entities_per_doc,
        qdrant_collection=args.qdrant_collection,
        qdrant_host=args.qdrant_host,
        qdrant_port=args.qdrant_port,
        qdrant_vector_size=args.qdrant_vector_size,
        qdrant_timeout_sec=args.qdrant_timeout_sec,
        neo4j_url=args.neo4j_url,
        neo4j_database=args.neo4j_database,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        neo4j_timeout_sec=args.neo4j_timeout_sec,
        neo4j_dataset_tag=args.neo4j_dataset_tag,
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
