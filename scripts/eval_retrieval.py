from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.rag.retrieval import load_docs, retrieve_top_k, retrieve_top_k_qdrant
from src.rag.retrieval_profiles import list_profile_names, resolve_profile
from src.agent_core.service_sla import build_common_metrics, build_service_sla_summary


EVAL_RESULTS_SCHEMA_VERSION = "retrieval_eval_results_v1"


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


def _load_eval_cases(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation file not found: {path}")

    cases: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at {path}:{line_no}") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_no}")

        query = str(payload.get("query", "")).strip()
        raw_relevant = payload.get("relevant_ids")
        if not query:
            raise ValueError(f"Missing non-empty 'query' at {path}:{line_no}")
        if not isinstance(raw_relevant, list) or not raw_relevant:
            raise ValueError(f"Missing non-empty 'relevant_ids' list at {path}:{line_no}")
        relevant_ids = [str(value).strip() for value in raw_relevant if str(value).strip()]
        if not relevant_ids:
            raise ValueError(f"Empty 'relevant_ids' entries at {path}:{line_no}")

        case_id = str(payload.get("id") or f"case_{len(cases) + 1:03d}")
        cases.append({"id": case_id, "query": query, "relevant_ids": relevant_ids})

    if not cases:
        raise ValueError(f"No eval cases found in: {path}")
    return cases


def _case_metrics(*, relevant_ids: list[str], retrieved_ids: list[str]) -> dict[str, Any]:
    relevant_set = set(relevant_ids)
    hits = [doc_id for doc_id in retrieved_ids if doc_id in relevant_set]
    unique_hits = set(hits)
    recall = len(unique_hits) / len(relevant_set)

    rr = 0.0
    first_hit_rank: int | None = None
    for index, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_set:
            rr = 1.0 / index
            first_hit_rank = index
            break

    return {
        "recall": recall,
        "mrr": rr,
        "first_hit_rank": first_hit_rank,
        "hits": sorted(unique_hits),
    }


def run_eval_retrieval(
    *,
    backend: str = "in_memory",
    docs_path: Path = Path("data") / "ftbquests_norm" / "quests.jsonl",
    eval_path: Path = Path("tests") / "fixtures" / "retrieval_eval_sample.jsonl",
    topk: int = 5,
    candidate_k: int = 50,
    reranker: str = "none",
    reranker_model: str = "Qwen/Qwen3-Reranker-0.6B",
    reranker_runtime: str = "torch",
    reranker_device: str = "AUTO",
    reranker_max_length: int = 1024,
    collection: str = "atm10",
    host: str = "127.0.0.1",
    port: int = 6333,
    vector_size: int = 64,
    timeout_sec: float = 10.0,
    runs_dir: Path = Path("runs"),
    profile: str = "baseline",
    policy: str = "signal_only",
    now: datetime | None = None,
) -> dict[str, Any]:
    if policy not in {"signal_only", "fail_on_breach"}:
        raise ValueError("policy must be signal_only or fail_on_breach.")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    eval_json_path = run_dir / "eval_results.json"
    service_sla_summary_path = run_dir / "service_sla_summary.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.isoformat(),
        "mode": "eval_retrieval",
        "profile": profile,
        "policy": policy,
        "status": "started",
        "backend": backend,
        "params": {
            "topk": topk,
            "candidate_k": candidate_k,
            "reranker": reranker,
            "reranker_model": reranker_model if reranker == "qwen3" else None,
            "reranker_runtime": reranker_runtime if reranker == "qwen3" else None,
            "reranker_device": reranker_device if reranker == "qwen3" else None,
            "reranker_max_length": reranker_max_length if reranker == "qwen3" else None,
            "collection": collection if backend == "qdrant" else None,
            "host": host if backend == "qdrant" else None,
            "port": port if backend == "qdrant" else None,
            "vector_size": vector_size if backend == "qdrant" else None,
            "timeout_sec": timeout_sec if backend == "qdrant" else None,
        },
        "paths": {
            "docs": str(docs_path) if backend == "in_memory" else None,
            "eval_cases": str(eval_path),
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "eval_results_json": str(eval_json_path),
            "service_sla_summary_json": str(service_sla_summary_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        cases = _load_eval_cases(eval_path)
        docs = load_docs(docs_path) if backend == "in_memory" else []

        per_case: list[dict[str, Any]] = []
        latencies_ms: list[float] = []
        for case in cases:
            started = perf_counter()
            if backend == "in_memory":
                results = retrieve_top_k(
                    case["query"],
                    docs,
                    topk=topk,
                    candidate_k=candidate_k,
                    reranker=reranker,
                    reranker_model=reranker_model,
                    reranker_max_length=reranker_max_length,
                    reranker_runtime=reranker_runtime,
                    reranker_device=reranker_device,
                )
            else:
                results = retrieve_top_k_qdrant(
                    case["query"],
                    collection=collection,
                    topk=topk,
                    candidate_k=candidate_k,
                    reranker=reranker,
                    reranker_model=reranker_model,
                    reranker_max_length=reranker_max_length,
                    reranker_runtime=reranker_runtime,
                    reranker_device=reranker_device,
                    host=host,
                    port=port,
                    vector_size=vector_size,
                    timeout_sec=timeout_sec,
                )
            latency_ms = (perf_counter() - started) * 1000.0
            latencies_ms.append(latency_ms)

            retrieved_ids = [str(item["id"]) for item in results]
            metrics = _case_metrics(relevant_ids=case["relevant_ids"], retrieved_ids=retrieved_ids)
            per_case.append(
                {
                    "id": case["id"],
                    "query": case["query"],
                    "relevant_ids": case["relevant_ids"],
                    "retrieved_ids": retrieved_ids,
                    "retrieved_count": len(retrieved_ids),
                    "latency_ms": latency_ms,
                    "metrics": metrics,
                }
            )

        query_count = len(per_case)
        mean_recall = sum(item["metrics"]["recall"] for item in per_case) / query_count
        mean_mrr = sum(item["metrics"]["mrr"] for item in per_case) / query_count
        hit_rate = sum(1 for item in per_case if item["metrics"]["first_hit_rank"] is not None) / query_count
        common_metrics = build_common_metrics(
            sample_count=query_count,
            success_count=query_count,
            latency_values_ms=latencies_ms,
        )

        eval_payload = {
            "schema_version": EVAL_RESULTS_SCHEMA_VERSION,
            "backend": backend,
            "profile": profile,
            "policy": policy,
            "metrics": {
                "query_count": query_count,
                "topk": topk,
                "candidate_k": candidate_k,
                "mean_recall_at_k": mean_recall,
                "mean_mrr_at_k": mean_mrr,
                "hit_rate_at_k": hit_rate,
                "latency_mean_ms": common_metrics["latency_mean_ms"],
                "latency_p50_ms": common_metrics["latency_p50_ms"],
                "latency_p95_ms": common_metrics["latency_p95_ms"],
                "latency_max_ms": common_metrics["latency_max_ms"],
            },
            "cases": per_case,
        }
        _write_json(eval_json_path, eval_payload)
        service_sla_summary = build_service_sla_summary(
            service_name="retrieval",
            surface="eval",
            backend=backend,
            profile=profile,
            policy=policy,
            status="ok",
            metrics=common_metrics,
            quality={
                "mean_recall_at_k": mean_recall,
                "mean_mrr_at_k": mean_mrr,
                "hit_rate_at_k": hit_rate,
            },
            thresholds={},
            warnings=[],
            breaches=[],
            paths={
                "run_dir": run_dir,
                "run_json": run_json_path,
                "eval_results_json": eval_json_path,
                "service_sla_summary_json": service_sla_summary_path,
            },
        )
        _write_json(service_sla_summary_path, service_sla_summary)
        run_payload["status"] = "ok"
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "eval_payload": eval_payload,
            "service_sla_summary": service_sla_summary,
        }
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        eval_payload = {
            "schema_version": EVAL_RESULTS_SCHEMA_VERSION,
            "backend": backend,
            "profile": profile,
            "policy": policy,
            "error": str(exc),
            "metrics": None,
            "cases": [],
        }
        _write_json(eval_json_path, eval_payload)
        service_sla_summary = build_service_sla_summary(
            service_name="retrieval",
            surface="eval",
            backend=backend,
            profile=profile,
            policy=policy,
            status="error",
            metrics=build_common_metrics(sample_count=0, success_count=0, error_count=1, latency_values_ms=[]),
            quality={},
            thresholds={},
            warnings=[],
            breaches=[f"eval_error: {exc}"],
            paths={
                "run_dir": run_dir,
                "run_json": run_json_path,
                "eval_results_json": eval_json_path,
                "service_sla_summary_json": service_sla_summary_path,
            },
        )
        _write_json(service_sla_summary_path, service_sla_summary)
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "eval_payload": eval_payload,
            "service_sla_summary": service_sla_summary,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality with Recall@k and MRR@k.")
    parser.add_argument(
        "--backend",
        choices=("in_memory", "qdrant"),
        default="in_memory",
        help="Retrieval backend: in_memory (default) or qdrant.",
    )
    parser.add_argument(
        "--profile",
        choices=list_profile_names(),
        default="baseline",
        help="Retrieval profile: baseline (default) or ov_production.",
    )
    parser.add_argument(
        "--docs",
        type=Path,
        default=Path("data") / "ftbquests_norm" / "quests.jsonl",
        help="Path to JSONL file or directory with *.jsonl files (used by in_memory backend).",
    )
    parser.add_argument(
        "--eval",
        dest="eval_path",
        type=Path,
        default=Path("tests") / "fixtures" / "retrieval_eval_sample.jsonl",
        help="JSONL file with eval cases: {id?, query, relevant_ids}.",
    )
    parser.add_argument("--topk", type=int, default=None, help="Cutoff k for metrics (overrides --profile).")
    parser.add_argument(
        "--candidate-k",
        type=int,
        default=None,
        help="First-stage candidate pool size (overrides --profile).",
    )
    parser.add_argument(
        "--reranker",
        choices=("none", "qwen3"),
        default=None,
        help="Second-stage reranker: none or qwen3 (overrides --profile).",
    )
    parser.add_argument(
        "--reranker-model",
        default=None,
        help="Reranker model id for --reranker qwen3 (overrides --profile).",
    )
    parser.add_argument(
        "--reranker-runtime",
        choices=("torch", "openvino"),
        default=None,
        help="Runtime for qwen3 reranker: torch or openvino (overrides --profile).",
    )
    parser.add_argument(
        "--reranker-device",
        default=None,
        help="Device for openvino runtime: AUTO, CPU, GPU, or NPU (overrides --profile).",
    )
    parser.add_argument(
        "--reranker-max-length",
        type=int,
        default=1024,
        help="Max tokenized length for reranker input (default: 1024).",
    )
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
    parser.add_argument(
        "--policy",
        choices=("signal_only", "fail_on_breach"),
        default="signal_only",
        help="Normalized SLA policy label for service_sla_summary.json (default: signal_only).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = resolve_profile(args.profile)
    effective_topk = args.topk if args.topk is not None else profile.topk
    effective_candidate_k = args.candidate_k if args.candidate_k is not None else profile.candidate_k
    effective_reranker = args.reranker if args.reranker is not None else profile.reranker
    effective_reranker_model = (
        args.reranker_model
        if args.reranker_model is not None
        else (profile.reranker_model or "Qwen/Qwen3-Reranker-0.6B")
    )
    effective_reranker_runtime = (
        args.reranker_runtime
        if args.reranker_runtime is not None
        else (profile.reranker_runtime or "torch")
    )
    effective_reranker_device = (
        args.reranker_device
        if args.reranker_device is not None
        else (profile.reranker_device or "AUTO")
    )
    result = run_eval_retrieval(
        backend=args.backend,
        docs_path=args.docs,
        eval_path=args.eval_path,
        topk=effective_topk,
        candidate_k=effective_candidate_k,
        reranker=effective_reranker,
        reranker_model=effective_reranker_model,
        reranker_runtime=effective_reranker_runtime,
        reranker_device=effective_reranker_device,
        reranker_max_length=args.reranker_max_length,
        collection=args.collection,
        host=args.host,
        port=args.port,
        vector_size=args.vector_size,
        timeout_sec=args.timeout_sec,
        runs_dir=args.runs_dir,
        profile=profile.name,
        policy=args.policy,
    )

    run_dir = result["run_dir"]
    print(f"[eval_retrieval] run_dir: {run_dir}")
    print(f"[eval_retrieval] run_json: {run_dir / 'run.json'}")
    print(f"[eval_retrieval] eval_results_json: {run_dir / 'eval_results.json'}")

    if not result["ok"]:
        print(f"[eval_retrieval] error: {result['eval_payload']['error']}")
        return 2

    metrics = result["eval_payload"]["metrics"]
    print(
        "[eval_retrieval] "
        f"query_count={metrics['query_count']} "
        f"recall_at_k={metrics['mean_recall_at_k']:.4f} "
        f"mrr_at_k={metrics['mean_mrr_at_k']:.4f} "
        f"hit_rate_at_k={metrics['hit_rate_at_k']:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
