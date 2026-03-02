from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_THRESHOLD_PROFILES: dict[str, dict[str, float]] = {
    "conservative": {
        "latency_p95_ms_max": 1500.0,
        "error_rate_max": 0.05,
        "timeout_rate_max": 0.01,
    },
    "moderate": {
        "latency_p95_ms_max": 1000.0,
        "error_rate_max": 0.03,
        "timeout_rate_max": 0.005,
    },
    "aggressive": {
        "latency_p95_ms_max": 700.0,
        "error_rate_max": 0.01,
        "timeout_rate_max": 0.002,
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-check")
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


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"HTTP smoke summary not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("HTTP smoke summary root must be JSON object.")
    return payload


def _percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    if percentile <= 0:
        return sorted_values[0]
    if percentile >= 100:
        return sorted_values[-1]
    rank = math.ceil((percentile / 100.0) * len(sorted_values))
    index = min(max(rank - 1, 0), len(sorted_values) - 1)
    return sorted_values[index]


def _extract_http_metrics(http_summary: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    required_fields = {"request_count", "failed_requests_count", "latency_p95_ms", "requests"}
    missing_fields = sorted(field for field in required_fields if field not in http_summary)
    if missing_fields:
        raise ValueError(f"Missing required HTTP smoke fields: {missing_fields}")

    request_count = int(http_summary["request_count"])
    failed_requests_count = int(http_summary["failed_requests_count"])
    if request_count <= 0:
        raise ValueError("request_count must be > 0.")
    if failed_requests_count < 0 or failed_requests_count > request_count:
        raise ValueError(
            "failed_requests_count must be within [0, request_count]."
        )

    request_rows = http_summary.get("requests")
    if not isinstance(request_rows, list):
        raise ValueError("requests must be a JSON array.")
    if len(request_rows) != request_count:
        raise ValueError("requests length must match request_count.")

    latencies_ms: list[float] = []
    timeout_count = 0
    error_buckets: dict[str, int] = {}
    for index, row in enumerate(request_rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"requests[{index}] must be a JSON object.")
        if "latency_ms" not in row:
            raise ValueError(f"requests[{index}].latency_ms is required.")
        latency_value = float(row["latency_ms"])
        if latency_value < 0:
            raise ValueError(f"requests[{index}].latency_ms must be >= 0.")
        latencies_ms.append(latency_value)

        error_code = row.get("error_code")
        error_bucket_key = "none" if error_code in (None, "", "None") else str(error_code)
        error_buckets[error_bucket_key] = error_buckets.get(error_bucket_key, 0) + 1
        if error_bucket_key == "operation_timeout":
            timeout_count += 1

    # Ensure upstream summary already exposes this field (contract check).
    _ = float(http_summary["latency_p95_ms"]) if http_summary["latency_p95_ms"] is not None else None

    error_rate = failed_requests_count / request_count
    timeout_rate = timeout_count / request_count
    metrics = {
        "request_count": request_count,
        "failed_requests_count": failed_requests_count,
        "error_rate": error_rate,
        "timeout_count": timeout_count,
        "timeout_rate": timeout_rate,
        "latency_p50_ms": _percentile_nearest_rank(latencies_ms, 50.0),
        "latency_p95_ms": _percentile_nearest_rank(latencies_ms, 95.0),
        "latency_max_ms": max(latencies_ms) if latencies_ms else None,
    }
    return metrics, error_buckets


def _evaluate_sla_breaches(
    *,
    metrics: Mapping[str, Any],
    thresholds: Mapping[str, float],
) -> list[str]:
    breaches: list[str] = []
    latency_p95_ms = metrics.get("latency_p95_ms")
    if latency_p95_ms is not None and float(latency_p95_ms) > float(thresholds["latency_p95_ms_max"]):
        breaches.append(
            f"latency_p95_ms={float(latency_p95_ms):.3f} > {float(thresholds['latency_p95_ms_max']):.3f}"
        )
    if float(metrics["error_rate"]) > float(thresholds["error_rate_max"]):
        breaches.append(
            f"error_rate={float(metrics['error_rate']):.6f} > {float(thresholds['error_rate_max']):.6f}"
        )
    if float(metrics["timeout_rate"]) > float(thresholds["timeout_rate_max"]):
        breaches.append(
            f"timeout_rate={float(metrics['timeout_rate']):.6f} > {float(thresholds['timeout_rate_max']):.6f}"
        )
    return breaches


def run_gateway_sla_check(
    *,
    http_summary_json: Path,
    summary_json: Path,
    profile: str = "conservative",
    policy: str = "signal_only",
    runs_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if profile not in _THRESHOLD_PROFILES:
        raise ValueError(f"Unsupported profile: {profile!r}")
    if policy not in {"signal_only", "fail_on_breach"}:
        raise ValueError(f"Unsupported policy: {policy!r}")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir: Path | None = None
    run_json_path: Path | None = None
    history_summary_json: Path | None = None
    run_payload: dict[str, Any] | None = None
    if runs_dir is not None:
        run_dir = _create_run_dir(runs_dir, now=now)
        run_json_path = run_dir / "run.json"
        history_summary_json = run_dir / "gateway_sla_summary.json"
        run_payload = {
            "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
            "mode": "gateway_sla_check",
            "status": "started",
            "params": {
                "http_summary_json": str(http_summary_json),
                "summary_json": str(summary_json),
                "profile": profile,
                "policy": policy,
            },
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_json),
                "history_summary_json": str(history_summary_json),
            },
        }
        _write_json(run_json_path, run_payload)

    thresholds = dict(_THRESHOLD_PROFILES[profile])
    summary_payload: dict[str, Any] = {
        "schema_version": "gateway_sla_summary_v1",
        "status": "error",
        "sla_status": "breach",
        "profile": profile,
        "policy": policy,
        "checked_at_utc": _utc_now(),
        "metrics": {
            "request_count": 0,
            "failed_requests_count": 0,
            "error_rate": 0.0,
            "timeout_count": 0,
            "timeout_rate": 0.0,
            "latency_p50_ms": None,
            "latency_p95_ms": None,
            "latency_max_ms": None,
        },
        "thresholds": thresholds,
        "error_buckets": {},
        "breaches": [],
        "paths": {
            "summary_json": str(summary_json),
        },
        "exit_code": 2,
        "error": None,
    }
    exit_code = 2
    if run_dir is not None and run_json_path is not None and history_summary_json is not None:
        summary_payload["paths"]["run_dir"] = str(run_dir)
        summary_payload["paths"]["run_json"] = str(run_json_path)
        summary_payload["paths"]["history_summary_json"] = str(history_summary_json)

    try:
        http_summary = _read_json_object(http_summary_json)
        metrics, error_buckets = _extract_http_metrics(http_summary)
        breaches = _evaluate_sla_breaches(metrics=metrics, thresholds=thresholds)
        sla_status = "pass" if not breaches else "breach"

        summary_payload["status"] = "ok"
        summary_payload["sla_status"] = sla_status
        summary_payload["metrics"] = metrics
        summary_payload["error_buckets"] = error_buckets
        summary_payload["breaches"] = breaches
        summary_payload["error"] = None

        if sla_status == "breach" and policy == "fail_on_breach":
            exit_code = 2
        else:
            exit_code = 0
    except Exception as exc:
        summary_payload["status"] = "error"
        summary_payload["sla_status"] = "breach"
        summary_payload["error"] = str(exc)
        summary_payload["breaches"] = [f"checker_error: {exc}"]
        exit_code = 2

    summary_payload["exit_code"] = exit_code
    _write_json(summary_json, summary_payload)
    if history_summary_json is not None:
        _write_json(history_summary_json, summary_payload)

    if run_payload is not None and run_json_path is not None:
        run_payload["status"] = summary_payload["status"]
        run_payload["result"] = {
            "sla_status": summary_payload["sla_status"],
            "exit_code": exit_code,
        }
        _write_json(run_json_path, run_payload)

    return {
        "ok": summary_payload["status"] == "ok",
        "exit_code": exit_code,
        "summary_payload": summary_payload,
        "run_dir": run_dir,
        "run_payload": run_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check gateway HTTP smoke summary against SLA profile thresholds."
    )
    parser.add_argument(
        "--http-summary-json",
        type=Path,
        required=True,
        help="Path to gateway_http_smoke_summary.json.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        required=True,
        help="Output path for gateway_sla_summary_v1.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(_THRESHOLD_PROFILES.keys()),
        default="conservative",
        help="SLA threshold profile (default: conservative).",
    )
    parser.add_argument(
        "--policy",
        choices=("signal_only", "fail_on_breach"),
        default="signal_only",
        help="Exit policy for SLA breach (default: signal_only).",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=None,
        help="Optional run artifact base directory for timestamped history copy/run.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_check(
        http_summary_json=args.http_summary_json,
        summary_json=args.summary_json,
        profile=args.profile,
        policy=args.policy,
        runs_dir=args.runs_dir,
    )
    summary_payload = result["summary_payload"]
    print(f"[check_gateway_sla] summary_json: {summary_payload['paths']['summary_json']}")
    print(f"[check_gateway_sla] status: {summary_payload['status']}")
    print(f"[check_gateway_sla] sla_status: {summary_payload['sla_status']}")
    print(f"[check_gateway_sla] exit_code: {summary_payload['exit_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
