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

from scripts.eval_kag_neo4j import (  # noqa: E402
    EVAL_RESULTS_SCHEMA_VERSION,
    _case_metrics,
    _load_eval_cases,
    _write_summary_md,
)
from src.agent_core.service_sla import build_common_metrics, build_service_sla_summary
from src.kag import build_kag_graph, query_kag_graph
from src.rag.retrieval import load_docs


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-kag-file-eval")
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


def run_eval_kag_file(
    *,
    docs_path: Path = Path("tests") / "fixtures" / "kag_neo4j_docs_sample.jsonl",
    eval_path: Path = Path("tests") / "fixtures" / "kag_neo4j_eval_sample.jsonl",
    topk: int = 5,
    max_entities_per_doc: int = 128,
    runs_dir: Path = Path("runs"),
    profile: str = "baseline_first",
    policy: str = "signal_only",
    now: datetime | None = None,
) -> dict[str, Any]:
    if topk <= 0:
        raise ValueError("topk must be > 0.")
    if max_entities_per_doc <= 0:
        raise ValueError("max_entities_per_doc must be > 0.")
    if policy not in {"signal_only", "fail_on_breach"}:
        raise ValueError("policy must be signal_only or fail_on_breach.")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    graph_json_path = run_dir / "kag_graph.json"
    eval_json_path = run_dir / "eval_results.json"
    summary_md_path = run_dir / "summary.md"
    service_sla_summary_path = run_dir / "service_sla_summary.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "eval_kag_file",
        "status": "started",
        "profile": profile,
        "policy": policy,
        "params": {
            "topk": topk,
            "max_entities_per_doc": max_entities_per_doc,
        },
        "paths": {
            "docs": str(docs_path),
            "eval_cases": str(eval_path),
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "graph_json": str(graph_json_path),
            "eval_results_json": str(eval_json_path),
            "summary_md": str(summary_md_path),
            "service_sla_summary_json": str(service_sla_summary_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        docs = load_docs(docs_path)
        graph_payload = build_kag_graph(docs, max_entities_per_doc=max_entities_per_doc)
        _write_json(graph_json_path, graph_payload)
        cases = _load_eval_cases(eval_path)

        per_case: list[dict[str, Any]] = []
        latencies_ms: list[float] = []
        for case in cases:
            started = perf_counter()
            results = query_kag_graph(
                graph_payload,
                query=case["query"],
                topk=topk,
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
            "backend": "file",
            "profile": profile,
            "policy": policy,
            "metrics": {
                "query_count": query_count,
                "topk": topk,
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
        _write_summary_md(
            path=summary_md_path,
            metrics=eval_payload["metrics"],
            cases=per_case,
        )

        service_sla_summary = build_service_sla_summary(
            service_name="kag_file",
            surface="eval",
            backend="file",
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
                "graph_json": graph_json_path,
                "eval_results_json": eval_json_path,
                "summary_md": summary_md_path,
                "service_sla_summary_json": service_sla_summary_path,
            },
        )
        _write_json(service_sla_summary_path, service_sla_summary)

        run_payload["status"] = "ok"
        run_payload["result"] = eval_payload["metrics"]
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
            "backend": "file",
            "profile": profile,
            "policy": policy,
            "error": str(exc),
            "metrics": None,
            "cases": [],
        }
        _write_json(eval_json_path, eval_payload)
        service_sla_summary = build_service_sla_summary(
            service_name="kag_file",
            surface="eval",
            backend="file",
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
                "graph_json": graph_json_path,
                "eval_results_json": eval_json_path,
                "summary_md": summary_md_path,
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
    parser = argparse.ArgumentParser(description="Evaluate file-backed KAG query quality and latency.")
    parser.add_argument(
        "--docs",
        type=Path,
        default=Path("tests") / "fixtures" / "kag_neo4j_docs_sample.jsonl",
        help="Path to JSONL file or directory with KAG docs.",
    )
    parser.add_argument(
        "--eval",
        dest="eval_path",
        type=Path,
        default=Path("tests") / "fixtures" / "kag_neo4j_eval_sample.jsonl",
        help="JSONL file with eval cases: {id?, query, relevant_ids}.",
    )
    parser.add_argument("--topk", type=int, default=5, help="Cutoff k for metrics (default: 5).")
    parser.add_argument(
        "--max-entities-per-doc",
        type=int,
        default=128,
        help="Max extracted entities per document for graph build (default: 128).",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    parser.add_argument(
        "--profile",
        type=str,
        default="baseline_first",
        help="Profile label for normalized SLA summary (default: baseline_first).",
    )
    parser.add_argument(
        "--policy",
        choices=("signal_only", "fail_on_breach"),
        default="signal_only",
        help="Normalized SLA policy label (default: signal_only).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_eval_kag_file(
        docs_path=args.docs,
        eval_path=args.eval_path,
        topk=args.topk,
        max_entities_per_doc=args.max_entities_per_doc,
        runs_dir=args.runs_dir,
        profile=args.profile,
        policy=args.policy,
    )
    run_dir = result["run_dir"]
    print(f"[eval_kag_file] run_dir: {run_dir}")
    print(f"[eval_kag_file] run_json: {run_dir / 'run.json'}")
    print(f"[eval_kag_file] graph_json: {run_dir / 'kag_graph.json'}")
    print(f"[eval_kag_file] eval_results_json: {run_dir / 'eval_results.json'}")
    print(f"[eval_kag_file] service_sla_summary_json: {run_dir / 'service_sla_summary.json'}")
    if not result["ok"]:
        print(f"[eval_kag_file] error: {result['eval_payload']['error']}")
        return 2

    metrics = result["eval_payload"]["metrics"]
    print(
        "[eval_kag_file] "
        f"query_count={metrics['query_count']} "
        f"recall_at_k={metrics['mean_recall_at_k']:.4f} "
        f"mrr_at_k={metrics['mean_mrr_at_k']:.4f} "
        f"hit_rate_at_k={metrics['hit_rate_at_k']:.4f} "
        f"latency_mean_ms={metrics['latency_mean_ms']:.2f} "
        f"latency_p95_ms={metrics['latency_p95_ms']:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
