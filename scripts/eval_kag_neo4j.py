from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kag import query_kag_neo4j


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-kag-neo4j-eval")
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


def _write_summary_md(
    *,
    path: Path,
    metrics: Mapping[str, Any],
    cases: list[Mapping[str, Any]],
) -> None:
    def _fmt(value: float) -> str:
        return f"{value:.4f}"

    lines = [
        "# KAG Neo4j Eval Summary",
        "",
        "## Metrics",
        "",
        f"- `query_count`: {metrics['query_count']}",
        f"- `topk`: {metrics['topk']}",
        f"- `mean_recall_at_k`: {_fmt(float(metrics['mean_recall_at_k']))}",
        f"- `mean_mrr_at_k`: {_fmt(float(metrics['mean_mrr_at_k']))}",
        f"- `hit_rate_at_k`: {_fmt(float(metrics['hit_rate_at_k']))}",
        f"- `latency_mean_ms`: {_fmt(float(metrics['latency_mean_ms']))}",
        f"- `latency_p95_ms`: {_fmt(float(metrics['latency_p95_ms']))}",
        f"- `latency_max_ms`: {_fmt(float(metrics['latency_max_ms']))}",
        "",
        "## Per-case",
        "",
        "| id | query | first_hit_rank | recall | mrr | latency_ms |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for item in cases:
        query = str(item["query"]).replace("|", "\\|")
        case_metrics = item["metrics"]
        first_hit_rank = case_metrics["first_hit_rank"]
        if first_hit_rank is None:
            first_hit = "-"
        else:
            first_hit = str(int(first_hit_rank))
        lines.append(
            "| "
            f"{item['id']} | {query} | {first_hit} | "
            f"{_fmt(float(case_metrics['recall']))} | "
            f"{_fmt(float(case_metrics['mrr']))} | "
            f"{_fmt(float(item['latency_ms']))} |"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_password(password: str | None) -> str:
    if password:
        return password
    from_env = os.environ.get("NEO4J_PASSWORD", "").strip()
    if from_env:
        return from_env
    raise ValueError("Neo4j password is required: pass --password or set NEO4J_PASSWORD.")


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


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if percentile <= 0:
        return min(values)
    if percentile >= 100:
        return max(values)
    sorted_values = sorted(values)
    rank = (len(sorted_values) - 1) * (percentile / 100.0)
    low_index = int(rank)
    high_index = min(low_index + 1, len(sorted_values) - 1)
    low_value = sorted_values[low_index]
    high_value = sorted_values[high_index]
    fraction = rank - low_index
    return low_value + ((high_value - low_value) * fraction)


def run_eval_kag_neo4j(
    *,
    eval_path: Path = Path("tests") / "fixtures" / "kag_neo4j_eval_sample.jsonl",
    topk: int = 5,
    neo4j_url: str = "http://127.0.0.1:7474",
    neo4j_database: str = "neo4j",
    neo4j_user: str = "neo4j",
    neo4j_password: str | None = None,
    timeout_sec: float = 10.0,
    warmup_runs: int = 0,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if warmup_runs < 0:
        raise ValueError("warmup_runs must be >= 0.")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    eval_json_path = run_dir / "eval_results.json"
    summary_md_path = run_dir / "summary.md"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "eval_kag_neo4j",
        "status": "started",
        "params": {
            "topk": topk,
            "neo4j_url": neo4j_url,
            "neo4j_database": neo4j_database,
            "neo4j_user": neo4j_user,
            "timeout_sec": timeout_sec,
            "warmup_runs": warmup_runs,
        },
        "paths": {
            "eval_cases": str(eval_path),
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "eval_results_json": str(eval_json_path),
            "summary_md": str(summary_md_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        password = _resolve_password(neo4j_password)
        cases = _load_eval_cases(eval_path)
        warmup_calls = 0

        if warmup_runs > 0:
            for _ in range(warmup_runs):
                for case in cases:
                    query_kag_neo4j(
                        url=neo4j_url,
                        database=neo4j_database,
                        user=neo4j_user,
                        password=password,
                        query=case["query"],
                        topk=topk,
                        timeout_sec=timeout_sec,
                    )
                    warmup_calls += 1

        per_case: list[dict[str, Any]] = []
        latencies_ms: list[float] = []
        for case in cases:
            started = perf_counter()
            results = query_kag_neo4j(
                url=neo4j_url,
                database=neo4j_database,
                user=neo4j_user,
                password=password,
                query=case["query"],
                topk=topk,
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
        latency_mean_ms = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
        latency_p95_ms = _percentile(latencies_ms, 95.0)
        latency_max_ms = max(latencies_ms) if latencies_ms else 0.0

        eval_payload = {
            "metrics": {
                "query_count": query_count,
                "topk": topk,
                "mean_recall_at_k": mean_recall,
                "mean_mrr_at_k": mean_mrr,
                "hit_rate_at_k": hit_rate,
                "latency_mean_ms": latency_mean_ms,
                "latency_p95_ms": latency_p95_ms,
                "latency_max_ms": latency_max_ms,
            },
            "cases": per_case,
        }
        _write_json(eval_json_path, eval_payload)
        _write_summary_md(
            path=summary_md_path,
            metrics=eval_payload["metrics"],
            cases=per_case,
        )
        run_payload["status"] = "ok"
        run_payload["warmup"] = {
            "requested_runs": warmup_runs,
            "executed_calls": warmup_calls,
        }
        run_payload["result"] = eval_payload["metrics"]
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "eval_payload": eval_payload,
        }
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        eval_payload = {"error": str(exc), "metrics": None, "cases": []}
        _write_json(eval_json_path, eval_payload)
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "eval_payload": eval_payload,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate KAG Neo4j query quality and latency.")
    parser.add_argument(
        "--eval",
        dest="eval_path",
        type=Path,
        default=Path("tests") / "fixtures" / "kag_neo4j_eval_sample.jsonl",
        help="JSONL file with eval cases: {id?, query, relevant_ids}.",
    )
    parser.add_argument("--topk", type=int, default=5, help="Cutoff k for metrics (default: 5).")
    parser.add_argument("--neo4j-url", default="http://127.0.0.1:7474", help="Neo4j HTTP base URL.")
    parser.add_argument("--neo4j-database", default="neo4j", help="Neo4j database name.")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username.")
    parser.add_argument("--password", default=None, help="Neo4j password (or use NEO4J_PASSWORD env var).")
    parser.add_argument("--timeout-sec", type=float, default=10.0, help="HTTP timeout for Neo4j requests.")
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=0,
        help="Number of full warmup passes over eval queries before measured run (default: 0).",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_eval_kag_neo4j(
        eval_path=args.eval_path,
        topk=args.topk,
        neo4j_url=args.neo4j_url,
        neo4j_database=args.neo4j_database,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.password,
        timeout_sec=args.timeout_sec,
        warmup_runs=args.warmup_runs,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[eval_kag_neo4j] run_dir: {run_dir}")
    print(f"[eval_kag_neo4j] run_json: {run_dir / 'run.json'}")
    print(f"[eval_kag_neo4j] eval_results_json: {run_dir / 'eval_results.json'}")

    if not result["ok"]:
        print(f"[eval_kag_neo4j] error: {result['eval_payload']['error']}")
        return 2

    metrics = result["eval_payload"]["metrics"]
    print(
        "[eval_kag_neo4j] "
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
