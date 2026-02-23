from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

_DEFAULT_PROFILES: dict[str, dict[str, float]] = {
    "sample": {
        "min_recall_at_k": 1.0,
        "min_mrr_at_k": 0.80,
        "min_hit_rate_at_k": 1.0,
        "max_latency_p95_ms": 120.0,
    },
    "hard": {
        "min_recall_at_k": 1.0,
        "min_mrr_at_k": 0.90,
        "min_hit_rate_at_k": 1.0,
        "max_latency_p95_ms": 130.0,
    },
}


def _load_metrics(path: Path) -> dict[str, float]:
    if not path.is_file():
        raise FileNotFoundError(f"Eval results file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Eval results root must be object: {path}")
    metrics = payload.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ValueError(f"Missing 'metrics' object in eval results: {path}")
    required = {
        "mean_recall_at_k",
        "mean_mrr_at_k",
        "hit_rate_at_k",
        "latency_p95_ms",
    }
    missing = sorted(key for key in required if key not in metrics)
    if missing:
        raise ValueError(f"Missing required metrics keys: {missing}")
    return {key: float(metrics[key]) for key in required}


def check_guardrail(
    *,
    metrics: Mapping[str, float],
    min_recall_at_k: float,
    min_mrr_at_k: float,
    min_hit_rate_at_k: float,
    max_latency_p95_ms: float,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if float(metrics["mean_recall_at_k"]) < min_recall_at_k:
        errors.append(
            f"mean_recall_at_k={metrics['mean_recall_at_k']:.4f} < required {min_recall_at_k:.4f}"
        )
    if float(metrics["mean_mrr_at_k"]) < min_mrr_at_k:
        errors.append(f"mean_mrr_at_k={metrics['mean_mrr_at_k']:.4f} < required {min_mrr_at_k:.4f}")
    if float(metrics["hit_rate_at_k"]) < min_hit_rate_at_k:
        errors.append(
            f"hit_rate_at_k={metrics['hit_rate_at_k']:.4f} < required {min_hit_rate_at_k:.4f}"
        )
    if float(metrics["latency_p95_ms"]) > max_latency_p95_ms:
        errors.append(
            f"latency_p95_ms={metrics['latency_p95_ms']:.2f} > allowed {max_latency_p95_ms:.2f}"
        )
    return (not errors), errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate KAG Neo4j eval_results.json against canonical quality/latency guardrail."
    )
    parser.add_argument(
        "--eval-results-json",
        type=Path,
        required=True,
        help="Path to eval_results.json produced by scripts/eval_kag_neo4j.py.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(_DEFAULT_PROFILES.keys()),
        default="sample",
        help="Canonical guardrail profile (default: sample).",
    )
    parser.add_argument("--min-recall-at-k", type=float, default=None)
    parser.add_argument("--min-mrr-at-k", type=float, default=None)
    parser.add_argument("--min-hit-rate-at-k", type=float, default=None)
    parser.add_argument("--max-latency-p95-ms", type=float, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    defaults = _DEFAULT_PROFILES[args.profile]
    min_recall_at_k = float(args.min_recall_at_k or defaults["min_recall_at_k"])
    min_mrr_at_k = float(args.min_mrr_at_k or defaults["min_mrr_at_k"])
    min_hit_rate_at_k = float(args.min_hit_rate_at_k or defaults["min_hit_rate_at_k"])
    max_latency_p95_ms = float(args.max_latency_p95_ms or defaults["max_latency_p95_ms"])

    metrics = _load_metrics(args.eval_results_json)
    ok, errors = check_guardrail(
        metrics=metrics,
        min_recall_at_k=min_recall_at_k,
        min_mrr_at_k=min_mrr_at_k,
        min_hit_rate_at_k=min_hit_rate_at_k,
        max_latency_p95_ms=max_latency_p95_ms,
    )
    print(
        "[check_kag_neo4j_guardrail] "
        f"profile={args.profile} "
        f"recall={metrics['mean_recall_at_k']:.4f} "
        f"mrr={metrics['mean_mrr_at_k']:.4f} "
        f"hit_rate={metrics['hit_rate_at_k']:.4f} "
        f"latency_p95_ms={metrics['latency_p95_ms']:.2f}"
    )
    if ok:
        print("[check_kag_neo4j_guardrail] status=ok")
        return 0
    for error in errors:
        print(f"[check_kag_neo4j_guardrail] violation: {error}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
