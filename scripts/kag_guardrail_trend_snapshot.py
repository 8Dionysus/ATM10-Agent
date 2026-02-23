from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_METRIC_KEYS: tuple[str, ...] = (
    "mean_recall_at_k",
    "mean_mrr_at_k",
    "hit_rate_at_k",
    "latency_p95_ms",
)
_EPSILON = 1e-9


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-kag-guardrail-trend")
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


def _read_eval_metrics(path: Path) -> dict[str, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Eval payload root must be object: {path}")
    metrics = payload.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ValueError(f"Missing metrics in {path}")
    return {
        "mean_recall_at_k": float(metrics["mean_recall_at_k"]),
        "mean_mrr_at_k": float(metrics["mean_mrr_at_k"]),
        "hit_rate_at_k": float(metrics["hit_rate_at_k"]),
        "latency_p95_ms": float(metrics["latency_p95_ms"]),
    }


def _collect_profile_history(profile_runs_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    eval_paths = sorted(profile_runs_dir.glob("**/eval_results.json"), key=lambda item: item.parent.name)
    rows: list[dict[str, Any]] = []
    for eval_path in eval_paths:
        metrics = _read_eval_metrics(eval_path)
        rows.append(
            {
                "run_dir": str(eval_path.parent),
                "run_name": eval_path.parent.name,
                "eval_results_json": str(eval_path),
                "metrics": metrics,
            }
        )
    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]
    return rows


def _compute_rolling_baseline(history: list[dict[str, Any]], *, window: int) -> dict[str, Any]:
    baseline_rows = history[:-1]
    if window > 0 and len(baseline_rows) > window:
        baseline_rows = baseline_rows[-window:]

    latest = history[-1]
    count = len(baseline_rows)
    if count == 0:
        return {
            "window": window,
            "count": 0,
            "run_names": [],
            "metrics_mean": None,
            "delta_latest_minus_baseline": None,
            "regression_flags": {
                "comparison_evaluated": False,
                "mrr_status": "insufficient_history",
                "latency_p95_status": "insufficient_history",
                "has_mrr_regression": False,
                "has_latency_p95_regression": False,
                "has_any_regression": False,
            },
        }

    metrics_mean: dict[str, float] = {}
    for key in _METRIC_KEYS:
        metrics_mean[key] = sum(float(row["metrics"][key]) for row in baseline_rows) / count

    delta_latest_minus_baseline = {
        f"delta_{key}": float(latest["metrics"][key]) - float(metrics_mean[key]) for key in _METRIC_KEYS
    }
    delta_mrr = float(delta_latest_minus_baseline["delta_mean_mrr_at_k"])
    delta_latency = float(delta_latest_minus_baseline["delta_latency_p95_ms"])

    if delta_mrr < -_EPSILON:
        mrr_status = "regressed"
    elif delta_mrr > _EPSILON:
        mrr_status = "improved"
    else:
        mrr_status = "stable"

    if delta_latency > _EPSILON:
        latency_status = "regressed"
    elif delta_latency < -_EPSILON:
        latency_status = "improved"
    else:
        latency_status = "stable"

    has_mrr_regression = mrr_status == "regressed"
    has_latency_regression = latency_status == "regressed"
    return {
        "window": window,
        "count": count,
        "run_names": [str(row["run_name"]) for row in baseline_rows],
        "metrics_mean": metrics_mean,
        "delta_latest_minus_baseline": delta_latest_minus_baseline,
        "regression_flags": {
            "comparison_evaluated": True,
            "mrr_status": mrr_status,
            "latency_p95_status": latency_status,
            "has_mrr_regression": has_mrr_regression,
            "has_latency_p95_regression": has_latency_regression,
            "has_any_regression": has_mrr_regression or has_latency_regression,
        },
    }


def _write_summary_md(path: Path, *, snapshot: Mapping[str, Any]) -> None:
    sample_profile = snapshot["profiles"]["sample"]
    hard_profile = snapshot["profiles"]["hard"]
    comparison = snapshot["comparison"]

    def _fmt_metric(row: Mapping[str, Any], key: str) -> str:
        value = float(row["metrics"][key])
        if key == "latency_p95_ms":
            return f"{value:.2f}"
        return f"{value:.4f}"

    def _fmt_opt(value: Any, *, decimals: int = 4) -> str:
        if value is None:
            return "n/a"
        return f"{float(value):.{decimals}f}"

    lines = [
        "# KAG Guardrail Trend Snapshot",
        "",
        "## Latest Metrics",
        "",
        "| profile | run | recall@k | mrr@k | hit-rate@k | latency_p95_ms |",
        "|---|---|---:|---:|---:|---:|",
    ]

    for label, profile in (("sample", sample_profile), ("hard", hard_profile)):
        latest = profile["latest"]
        lines.append(
            "| "
            f"{label} | {latest['run_name']} | "
            f"{_fmt_metric(latest, 'mean_recall_at_k')} | "
            f"{_fmt_metric(latest, 'mean_mrr_at_k')} | "
            f"{_fmt_metric(latest, 'hit_rate_at_k')} | "
            f"{_fmt_metric(latest, 'latency_p95_ms')} |"
        )

    lines.extend(
        [
            "",
            "## Latest Delta (hard - sample)",
            "",
            f"- `delta_mrr`: {float(comparison['latest_hard_minus_sample']['delta_mrr']):.4f}",
            (
                "- `delta_latency_p95_ms`: "
                f"{float(comparison['latest_hard_minus_sample']['delta_latency_p95_ms']):.2f}"
            ),
            "",
            "## History Window",
            "",
            f"- `sample_count`: {sample_profile['count']}",
            f"- `hard_count`: {hard_profile['count']}",
            f"- `history_limit`: {snapshot['history_limit']}",
            f"- `baseline_window`: {snapshot['baseline_window']}",
        ]
    )

    lines.extend(
        [
            "",
            "## Rolling Baseline (latest - mean previous runs)",
            "",
            (
                "| profile | baseline_count | baseline_mrr | baseline_latency_p95_ms | delta_mrr | "
                "delta_latency_p95_ms | mrr_status | latency_p95_status | any_regression |"
            ),
            "|---|---:|---:|---:|---:|---:|---|---|---|",
        ]
    )

    for label, profile in (("sample", sample_profile), ("hard", hard_profile)):
        rolling = profile["rolling_baseline"]
        means = rolling["metrics_mean"] or {}
        deltas = rolling["delta_latest_minus_baseline"] or {}
        flags = rolling["regression_flags"]
        lines.append(
            "| "
            f"{label} | {rolling['count']} | "
            f"{_fmt_opt(means.get('mean_mrr_at_k'), decimals=4)} | "
            f"{_fmt_opt(means.get('latency_p95_ms'), decimals=2)} | "
            f"{_fmt_opt(deltas.get('delta_mean_mrr_at_k'), decimals=4)} | "
            f"{_fmt_opt(deltas.get('delta_latency_p95_ms'), decimals=2)} | "
            f"{flags['mrr_status']} | "
            f"{flags['latency_p95_status']} | "
            f"{str(flags['has_any_regression']).lower()} |"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_kag_guardrail_trend_snapshot(
    *,
    sample_runs_dir: Path = Path("runs") / "nightly-kag-eval-sample",
    hard_runs_dir: Path = Path("runs") / "nightly-kag-eval-hard",
    history_limit: int = 5,
    baseline_window: int = 3,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if history_limit <= 0:
        raise ValueError("history_limit must be > 0.")
    if baseline_window <= 0:
        raise ValueError("baseline_window must be > 0.")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    snapshot_json_path = run_dir / "trend_snapshot.json"
    summary_md_path = run_dir / "summary.md"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "kag_guardrail_trend_snapshot",
        "status": "started",
        "params": {
            "sample_runs_dir": str(sample_runs_dir),
            "hard_runs_dir": str(hard_runs_dir),
            "history_limit": history_limit,
            "baseline_window": baseline_window,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "snapshot_json": str(snapshot_json_path),
            "summary_md": str(summary_md_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        sample_history = _collect_profile_history(sample_runs_dir, limit=history_limit)
        hard_history = _collect_profile_history(hard_runs_dir, limit=history_limit)
        if not sample_history:
            raise ValueError(f"No eval_results.json found under sample_runs_dir: {sample_runs_dir}")
        if not hard_history:
            raise ValueError(f"No eval_results.json found under hard_runs_dir: {hard_runs_dir}")

        latest_sample = sample_history[-1]
        latest_hard = hard_history[-1]
        sample_rolling_baseline = _compute_rolling_baseline(sample_history, window=baseline_window)
        hard_rolling_baseline = _compute_rolling_baseline(hard_history, window=baseline_window)
        snapshot_payload = {
            "history_limit": history_limit,
            "baseline_window": baseline_window,
            "profiles": {
                "sample": {
                    "count": len(sample_history),
                    "latest": latest_sample,
                    "history": sample_history,
                    "rolling_baseline": sample_rolling_baseline,
                },
                "hard": {
                    "count": len(hard_history),
                    "latest": latest_hard,
                    "history": hard_history,
                    "rolling_baseline": hard_rolling_baseline,
                },
            },
            "comparison": {
                "latest_hard_minus_sample": {
                    "delta_mrr": float(latest_hard["metrics"]["mean_mrr_at_k"])
                    - float(latest_sample["metrics"]["mean_mrr_at_k"]),
                    "delta_latency_p95_ms": float(latest_hard["metrics"]["latency_p95_ms"])
                    - float(latest_sample["metrics"]["latency_p95_ms"]),
                }
            },
        }
        _write_json(snapshot_json_path, snapshot_payload)
        _write_summary_md(summary_md_path, snapshot=snapshot_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "sample_latest_run": latest_sample["run_name"],
            "hard_latest_run": latest_hard["run_name"],
            "sample_count": len(sample_history),
            "hard_count": len(hard_history),
            "sample_baseline_count": sample_rolling_baseline["count"],
            "hard_baseline_count": hard_rolling_baseline["count"],
            "sample_has_regression": sample_rolling_baseline["regression_flags"]["has_any_regression"],
            "hard_has_regression": hard_rolling_baseline["regression_flags"]["has_any_regression"],
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "snapshot_payload": snapshot_payload,
        }
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        run_payload["error_code"] = "guardrail_trend_failed"
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "snapshot_payload": None,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create trend snapshot for nightly KAG guardrail metrics.")
    parser.add_argument(
        "--sample-runs-dir",
        type=Path,
        default=Path("runs") / "nightly-kag-eval-sample",
        help="Directory with sample eval runs.",
    )
    parser.add_argument(
        "--hard-runs-dir",
        type=Path,
        default=Path("runs") / "nightly-kag-eval-hard",
        help="Directory with hard eval runs.",
    )
    parser.add_argument("--history-limit", type=int, default=5, help="Number of latest runs per profile.")
    parser.add_argument(
        "--baseline-window",
        type=int,
        default=3,
        help="Number of previous runs used for rolling baseline comparison per profile.",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_kag_guardrail_trend_snapshot(
        sample_runs_dir=args.sample_runs_dir,
        hard_runs_dir=args.hard_runs_dir,
        history_limit=args.history_limit,
        baseline_window=args.baseline_window,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[kag_guardrail_trend_snapshot] run_dir: {run_dir}")
    print(f"[kag_guardrail_trend_snapshot] run_json: {run_dir / 'run.json'}")
    print(f"[kag_guardrail_trend_snapshot] trend_snapshot_json: {run_dir / 'trend_snapshot.json'}")
    print(f"[kag_guardrail_trend_snapshot] summary_md: {run_dir / 'summary.md'}")
    if not result["ok"]:
        print(f"[kag_guardrail_trend_snapshot] error: {result['run_payload']['error']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
