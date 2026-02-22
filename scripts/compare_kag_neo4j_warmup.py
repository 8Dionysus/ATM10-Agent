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

from scripts.eval_kag_neo4j import run_eval_kag_neo4j


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-kag-neo4j-warmup-compare")
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


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _profile_summary(*, label: str, warmup_runs: int, runs: list[dict[str, Any]]) -> dict[str, Any]:
    p95_values = [float(item["latency_p95_ms"]) for item in runs]
    mrr_values = [float(item["mean_mrr_at_k"]) for item in runs]
    hit_rate_values = [float(item["hit_rate_at_k"]) for item in runs]
    return {
        "label": label,
        "warmup_runs": warmup_runs,
        "repeats": len(runs),
        "runs": runs,
        "metrics": {
            "latency_p95_ms_avg": _mean(p95_values),
            "latency_p95_ms_min": min(p95_values) if p95_values else 0.0,
            "latency_p95_ms_max": max(p95_values) if p95_values else 0.0,
            "mean_mrr_at_k_avg": _mean(mrr_values),
            "hit_rate_at_k_avg": _mean(hit_rate_values),
        },
    }


def _write_summary_md(path: Path, *, comparison: Mapping[str, Any]) -> None:
    baseline = comparison["baseline"]
    candidate = comparison["candidate"]
    delta = comparison["delta"]

    def _fmt(value: float) -> str:
        return f"{value:.2f}"

    lines = [
        "# KAG Neo4j Warmup Compare Summary",
        "",
        "## Profiles",
        "",
        "| profile | warmup_runs | repeats | p95 avg (ms) | p95 min (ms) | p95 max (ms) | mrr avg | hit-rate avg |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for profile in (baseline, candidate):
        metrics = profile["metrics"]
        lines.append(
            "| "
            f"{profile['label']} | {profile['warmup_runs']} | {profile['repeats']} | "
            f"{_fmt(float(metrics['latency_p95_ms_avg']))} | "
            f"{_fmt(float(metrics['latency_p95_ms_min']))} | "
            f"{_fmt(float(metrics['latency_p95_ms_max']))} | "
            f"{float(metrics['mean_mrr_at_k_avg']):.4f} | "
            f"{float(metrics['hit_rate_at_k_avg']):.4f} |"
        )

    lines.extend(
        [
            "",
            "## Delta",
            "",
            f"- `candidate_vs_baseline_p95_delta_ms`: {_fmt(float(delta['p95_delta_ms']))}",
            f"- `candidate_vs_baseline_p95_improvement_ms`: {_fmt(float(delta['p95_improvement_ms']))}",
            f"- `candidate_vs_baseline_p95_improvement_pct`: {float(delta['p95_improvement_pct']):.2f}%",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_compare_kag_neo4j_warmup(
    *,
    eval_path: Path = Path("tests") / "fixtures" / "kag_neo4j_eval_hard.jsonl",
    repeats: int = 3,
    baseline_warmup_runs: int = 0,
    candidate_warmup_runs: int = 1,
    topk: int = 5,
    neo4j_url: str = "http://127.0.0.1:7474",
    neo4j_database: str = "neo4j",
    neo4j_user: str = "neo4j",
    neo4j_password: str | None = None,
    timeout_sec: float = 10.0,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if repeats <= 0:
        raise ValueError("repeats must be > 0.")
    if baseline_warmup_runs < 0 or candidate_warmup_runs < 0:
        raise ValueError("warmup runs must be >= 0.")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    summary_json_path = run_dir / "summary.json"
    summary_md_path = run_dir / "summary.md"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "compare_kag_neo4j_warmup",
        "status": "started",
        "params": {
            "eval_path": str(eval_path),
            "repeats": repeats,
            "baseline_warmup_runs": baseline_warmup_runs,
            "candidate_warmup_runs": candidate_warmup_runs,
            "topk": topk,
            "neo4j_url": neo4j_url,
            "neo4j_database": neo4j_database,
            "neo4j_user": neo4j_user,
            "timeout_sec": timeout_sec,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_json_path),
            "summary_md": str(summary_md_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        profiles = [
            ("baseline", baseline_warmup_runs),
            ("candidate", candidate_warmup_runs),
        ]
        profile_outputs: list[dict[str, Any]] = []
        for label, warmup_runs in profiles:
            runs: list[dict[str, Any]] = []
            for attempt in range(1, repeats + 1):
                result = run_eval_kag_neo4j(
                    eval_path=eval_path,
                    topk=topk,
                    neo4j_url=neo4j_url,
                    neo4j_database=neo4j_database,
                    neo4j_user=neo4j_user,
                    neo4j_password=neo4j_password,
                    timeout_sec=timeout_sec,
                    warmup_runs=warmup_runs,
                    runs_dir=runs_dir,
                )
                if not result["ok"]:
                    message = str(result["eval_payload"].get("error", "unknown error"))
                    raise RuntimeError(
                        f"{label} run failed at attempt={attempt}: {message} "
                        f"(run_dir={result['run_dir']})"
                    )
                metrics = result["eval_payload"]["metrics"]
                runs.append(
                    {
                        "attempt": attempt,
                        "eval_run_dir": str(result["run_dir"]),
                        "latency_p95_ms": float(metrics["latency_p95_ms"]),
                        "mean_mrr_at_k": float(metrics["mean_mrr_at_k"]),
                        "hit_rate_at_k": float(metrics["hit_rate_at_k"]),
                    }
                )
            profile_outputs.append(_profile_summary(label=label, warmup_runs=warmup_runs, runs=runs))

        baseline_summary = profile_outputs[0]
        candidate_summary = profile_outputs[1]
        baseline_p95_avg = float(baseline_summary["metrics"]["latency_p95_ms_avg"])
        candidate_p95_avg = float(candidate_summary["metrics"]["latency_p95_ms_avg"])
        p95_delta_ms = candidate_p95_avg - baseline_p95_avg
        p95_improvement_ms = baseline_p95_avg - candidate_p95_avg
        p95_improvement_pct = 0.0
        if baseline_p95_avg > 0.0:
            p95_improvement_pct = (p95_improvement_ms / baseline_p95_avg) * 100.0

        summary_payload = {
            "baseline": baseline_summary,
            "candidate": candidate_summary,
            "delta": {
                "p95_delta_ms": p95_delta_ms,
                "p95_improvement_ms": p95_improvement_ms,
                "p95_improvement_pct": p95_improvement_pct,
            },
        }
        _write_json(summary_json_path, summary_payload)
        _write_summary_md(summary_md_path, comparison=summary_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = summary_payload["delta"]
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
        }
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": {"error": str(exc)},
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare KAG Neo4j eval latency with and without warmup.")
    parser.add_argument(
        "--eval",
        dest="eval_path",
        type=Path,
        default=Path("tests") / "fixtures" / "kag_neo4j_eval_hard.jsonl",
        help="JSONL file with eval cases: {id?, query, relevant_ids}.",
    )
    parser.add_argument("--repeats", type=int, default=3, help="Number of repeated runs per profile.")
    parser.add_argument("--baseline-warmup-runs", type=int, default=0, help="Warmup runs for baseline profile.")
    parser.add_argument("--candidate-warmup-runs", type=int, default=1, help="Warmup runs for candidate profile.")
    parser.add_argument("--topk", type=int, default=5, help="Cutoff k for metrics.")
    parser.add_argument("--neo4j-url", default="http://127.0.0.1:7474", help="Neo4j HTTP base URL.")
    parser.add_argument("--neo4j-database", default="neo4j", help="Neo4j database name.")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username.")
    parser.add_argument("--password", default=None, help="Neo4j password (or use NEO4J_PASSWORD env var).")
    parser.add_argument("--timeout-sec", type=float, default=10.0, help="HTTP timeout for Neo4j requests.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_compare_kag_neo4j_warmup(
        eval_path=args.eval_path,
        repeats=args.repeats,
        baseline_warmup_runs=args.baseline_warmup_runs,
        candidate_warmup_runs=args.candidate_warmup_runs,
        topk=args.topk,
        neo4j_url=args.neo4j_url,
        neo4j_database=args.neo4j_database,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.password,
        timeout_sec=args.timeout_sec,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[compare_kag_neo4j_warmup] run_dir: {run_dir}")
    print(f"[compare_kag_neo4j_warmup] run_json: {run_dir / 'run.json'}")
    print(f"[compare_kag_neo4j_warmup] summary_json: {run_dir / 'summary.json'}")
    print(f"[compare_kag_neo4j_warmup] summary_md: {run_dir / 'summary.md'}")

    if not result["ok"]:
        print(f"[compare_kag_neo4j_warmup] error: {result['summary_payload']['error']}")
        return 2

    delta = result["summary_payload"]["delta"]
    print(
        "[compare_kag_neo4j_warmup] "
        f"p95_delta_ms={delta['p95_delta_ms']:.2f} "
        f"p95_improvement_ms={delta['p95_improvement_ms']:.2f} "
        f"p95_improvement_pct={delta['p95_improvement_pct']:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
