from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _latest_run_dir(runs_dir: Path) -> Path:
    if not runs_dir.exists() or not runs_dir.is_dir():
        raise FileNotFoundError(f"Runs directory not found: {runs_dir}")
    candidates = sorted([path for path in runs_dir.iterdir() if path.is_dir()], key=lambda path: path.name)
    if not candidates:
        raise FileNotFoundError(f"No run directories found under: {runs_dir}")
    return candidates[-1]


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def _build_summary(run_dir: Path, run_payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    mode = str(run_payload.get("mode", "")).strip() or "unknown"
    status = str(run_payload.get("status", "")).strip() or "ok"

    observed: dict[str, Any] = {
        "mode": mode,
        "status": status,
    }

    if mode == "phase_a_smoke":
        response_payload = _read_optional_json(run_dir / "response.json")
        if response_payload is None:
            errors.append("response.json is missing or invalid")
        vlm_payload = run_payload.get("vlm")
        if isinstance(vlm_payload, dict):
            observed["vlm_resolved"] = vlm_payload.get("resolved")
            observed["vlm_fallback_used"] = bool(vlm_payload.get("fallback_used", False))
    elif mode == "retrieve_demo":
        results_payload = _read_optional_json(run_dir / "retrieval_results.json")
        if status == "ok" and results_payload is None:
            errors.append("retrieval_results.json is missing or invalid")
        if isinstance(results_payload, dict):
            results = results_payload.get("results")
            if isinstance(results, list):
                observed["results_count"] = len(results)
            observed["retrieved_count"] = results_payload.get("count")
    elif mode == "eval_retrieval":
        eval_payload = _read_optional_json(run_dir / "eval_results.json")
        if status == "ok" and eval_payload is None:
            errors.append("eval_results.json is missing or invalid")
        if isinstance(eval_payload, dict):
            metrics = eval_payload.get("metrics")
            if isinstance(metrics, dict):
                observed["query_count"] = metrics.get("query_count")
                observed["mean_recall_at_k"] = metrics.get("mean_recall_at_k")
                observed["mean_mrr_at_k"] = metrics.get("mean_mrr_at_k")
                observed["hit_rate_at_k"] = metrics.get("hit_rate_at_k")
    else:
        errors.append(f"unsupported mode in run.json: {mode}")

    summary_payload = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "ok": not errors,
        "status": "ok" if not errors else "error",
        "observed": observed,
        "violations": errors,
    }
    return summary_payload, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build machine-readable summary for latest smoke run.")
    parser.add_argument("--runs-dir", type=Path, required=True, help="Base directory with smoke run folders.")
    parser.add_argument(
        "--expected-mode",
        choices=("phase_a_smoke", "retrieve_demo", "eval_retrieval"),
        required=True,
        help="Expected run.json mode for validation.",
    )
    parser.add_argument("--summary-json", type=Path, required=True, help="Output JSON summary path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_dir = _latest_run_dir(args.runs_dir)
        run_payload = _read_json(run_dir / "run.json")
        summary_payload, errors = _build_summary(run_dir, run_payload)
        observed_mode = str(summary_payload["observed"].get("mode", "")).strip()
        if observed_mode != args.expected_mode:
            errors.append(f"observed mode {observed_mode!r} != expected_mode {args.expected_mode!r}")
            summary_payload["ok"] = False
            summary_payload["status"] = "error"
            summary_payload["violations"] = errors
        _write_json(args.summary_json, summary_payload)
        print(f"[collect_smoke_run_summary] run_dir={run_dir}")
        print(f"[collect_smoke_run_summary] expected_mode={args.expected_mode}")
        print(f"[collect_smoke_run_summary] summary_json={args.summary_json}")
        if errors:
            for error in errors:
                print(f"[collect_smoke_run_summary] violation: {error}")
            return 2
        return 0
    except Exception as exc:
        summary_payload = {
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_dir": None,
            "ok": False,
            "status": "error",
            "observed": {"mode": args.expected_mode, "status": "error"},
            "violations": [],
            "error": str(exc),
        }
        _write_json(args.summary_json, summary_payload)
        print(f"[collect_smoke_run_summary] error: {exc}")
        print(f"[collect_smoke_run_summary] summary_json={args.summary_json}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
