from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_EPSILON = 1e-9
_SEVERITY_RANK = {"none": 0, "warn": 1, "critical": 2}
_CRITICAL_POLICIES: tuple[str, ...] = ("signal_only", "fail_nightly")
_SUMMARY_FILE_NAME = "gateway_sla_summary.json"

_DEFAULT_ERROR_RATE_WARN_DELTA = 0.01
_DEFAULT_ERROR_RATE_CRITICAL_DELTA = 0.03
_DEFAULT_TIMEOUT_RATE_WARN_DELTA = 0.005
_DEFAULT_TIMEOUT_RATE_CRITICAL_DELTA = 0.01
_DEFAULT_LATENCY_P95_WARN_DELTA_MS = 100.0
_DEFAULT_LATENCY_P95_CRITICAL_DELTA_MS = 300.0
_DEFAULT_BREACH_RATE_WARN_DELTA = 0.5
_DEFAULT_BREACH_RATE_CRITICAL_DELTA = 0.9


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-trend")
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


def _max_severity(*values: str) -> str:
    return max(values, key=lambda item: _SEVERITY_RANK.get(item, 0))


def _regression_status_higher_worse(delta: float) -> str:
    if delta > _EPSILON:
        return "regressed"
    if delta < -_EPSILON:
        return "improved"
    return "stable"


def _regression_severity(*, status: str, magnitude: float, warn_delta: float, critical_delta: float) -> str:
    if status != "regressed":
        return "none"
    if magnitude + _EPSILON >= critical_delta:
        return "critical"
    if magnitude + _EPSILON >= warn_delta:
        return "warn"
    return "none"


def _parse_iso_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("checked_at_utc must be a non-empty string.")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _validate_thresholds(
    *,
    error_rate_warn_delta: float,
    error_rate_critical_delta: float,
    timeout_rate_warn_delta: float,
    timeout_rate_critical_delta: float,
    latency_p95_warn_delta_ms: float,
    latency_p95_critical_delta_ms: float,
    breach_rate_warn_delta: float,
    breach_rate_critical_delta: float,
) -> None:
    checks = (
        ("error_rate_warn_delta", error_rate_warn_delta),
        ("error_rate_critical_delta", error_rate_critical_delta),
        ("timeout_rate_warn_delta", timeout_rate_warn_delta),
        ("timeout_rate_critical_delta", timeout_rate_critical_delta),
        ("latency_p95_warn_delta_ms", latency_p95_warn_delta_ms),
        ("latency_p95_critical_delta_ms", latency_p95_critical_delta_ms),
        ("breach_rate_warn_delta", breach_rate_warn_delta),
        ("breach_rate_critical_delta", breach_rate_critical_delta),
    )
    for name, value in checks:
        if float(value) < 0:
            raise ValueError(f"{name} must be >= 0.")
    if error_rate_critical_delta + _EPSILON < error_rate_warn_delta:
        raise ValueError("error_rate_critical_delta must be >= error_rate_warn_delta.")
    if timeout_rate_critical_delta + _EPSILON < timeout_rate_warn_delta:
        raise ValueError("timeout_rate_critical_delta must be >= timeout_rate_warn_delta.")
    if latency_p95_critical_delta_ms + _EPSILON < latency_p95_warn_delta_ms:
        raise ValueError("latency_p95_critical_delta_ms must be >= latency_p95_warn_delta_ms.")
    if breach_rate_critical_delta + _EPSILON < breach_rate_warn_delta:
        raise ValueError("breach_rate_critical_delta must be >= breach_rate_warn_delta.")


def _read_valid_sla_rows(sla_runs_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    seen_fingerprints: set[tuple[Any, ...]] = set()
    for summary_path in sorted(sla_runs_dir.glob(f"**/{_SUMMARY_FILE_NAME}")):
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("summary root must be an object")
            if payload.get("schema_version") != "gateway_sla_summary_v1":
                raise ValueError("schema_version must be gateway_sla_summary_v1")
            if payload.get("status") != "ok":
                raise ValueError("status must be ok")
            checked_at = _parse_iso_datetime(payload.get("checked_at_utc"))
            sla_status = str(payload.get("sla_status", "")).strip()
            if sla_status not in {"pass", "breach"}:
                raise ValueError("sla_status must be pass|breach")
            metrics = payload.get("metrics")
            if not isinstance(metrics, Mapping):
                raise ValueError("metrics must be an object")
            metrics_row = {
                "error_rate": float(metrics["error_rate"]),
                "timeout_rate": float(metrics["timeout_rate"]),
                "latency_p95_ms": float(metrics["latency_p95_ms"]),
            }
            row = {
                "checked_at_utc": checked_at.astimezone(timezone.utc).isoformat(),
                "checked_at_epoch": checked_at.timestamp(),
                "run_name": summary_path.parent.name,
                "summary_json": str(summary_path),
                "profile": str(payload.get("profile", "")),
                "policy": str(payload.get("policy", "")),
                "sla_status": sla_status,
                "metrics": metrics_row,
            }
            fingerprint = (
                row["checked_at_utc"],
                row["profile"],
                row["policy"],
                row["sla_status"],
                round(metrics_row["error_rate"], 12),
                round(metrics_row["timeout_rate"], 12),
                round(metrics_row["latency_p95_ms"], 12),
            )
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            rows.append(row)
        except Exception as exc:
            warnings.append(f"{summary_path}: skipped ({exc})")
    rows.sort(key=lambda item: (float(item["checked_at_epoch"]), str(item["run_name"])))
    return rows, warnings


def _write_summary_md(path: Path, *, snapshot: Mapping[str, Any]) -> None:
    latest = snapshot.get("latest") or {}
    rolling = snapshot.get("rolling_baseline") or {}
    rolling_flags = rolling.get("regression_flags") or {}
    breach_drift = snapshot.get("breach_drift") or {}
    critical_policy = snapshot.get("critical_policy") or {}
    lines = [
        "# Gateway SLA Trend Snapshot",
        "",
        f"- `status`: {snapshot.get('status', 'n/a')}",
        f"- `latest_run`: {latest.get('run_name', 'n/a')}",
        f"- `latest_checked_at_utc`: {latest.get('checked_at_utc', 'n/a')}",
        f"- `latest_sla_status`: {latest.get('sla_status', 'n/a')}",
        f"- `baseline_count`: {rolling.get('count', 0)}",
        f"- `error_rate_status`: {rolling_flags.get('error_rate_status', 'n/a')}",
        f"- `timeout_rate_status`: {rolling_flags.get('timeout_rate_status', 'n/a')}",
        f"- `latency_p95_status`: {rolling_flags.get('latency_p95_status', 'n/a')}",
        f"- `max_regression_severity`: {rolling_flags.get('max_regression_severity', 'n/a')}",
        f"- `breach_rate_status`: {breach_drift.get('breach_rate_status', 'n/a')}",
        f"- `breach_rate_severity`: {breach_drift.get('breach_rate_severity', 'n/a')}",
        f"- `critical_policy_mode`: {critical_policy.get('mode', 'n/a')}",
        f"- `critical_policy_has_critical_regression`: {critical_policy.get('has_critical_regression', 'n/a')}",
        f"- `critical_policy_should_fail_nightly`: {critical_policy.get('should_fail_nightly', 'n/a')}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_gateway_sla_trend_snapshot(
    *,
    sla_runs_dir: Path = Path("runs") / "ci-smoke-gateway-sla",
    history_limit: int = 10,
    baseline_window: int = 5,
    error_rate_warn_delta: float = _DEFAULT_ERROR_RATE_WARN_DELTA,
    error_rate_critical_delta: float = _DEFAULT_ERROR_RATE_CRITICAL_DELTA,
    timeout_rate_warn_delta: float = _DEFAULT_TIMEOUT_RATE_WARN_DELTA,
    timeout_rate_critical_delta: float = _DEFAULT_TIMEOUT_RATE_CRITICAL_DELTA,
    latency_p95_warn_delta_ms: float = _DEFAULT_LATENCY_P95_WARN_DELTA_MS,
    latency_p95_critical_delta_ms: float = _DEFAULT_LATENCY_P95_CRITICAL_DELTA_MS,
    breach_rate_warn_delta: float = _DEFAULT_BREACH_RATE_WARN_DELTA,
    breach_rate_critical_delta: float = _DEFAULT_BREACH_RATE_CRITICAL_DELTA,
    critical_policy: str = "signal_only",
    runs_dir: Path = Path("runs") / "ci-smoke-gateway-sla-trend",
    now: datetime | None = None,
) -> dict[str, Any]:
    if history_limit <= 0:
        raise ValueError("history_limit must be > 0.")
    if baseline_window <= 0:
        raise ValueError("baseline_window must be > 0.")
    if critical_policy not in _CRITICAL_POLICIES:
        raise ValueError(f"critical_policy must be one of: {', '.join(_CRITICAL_POLICIES)}")
    _validate_thresholds(
        error_rate_warn_delta=error_rate_warn_delta,
        error_rate_critical_delta=error_rate_critical_delta,
        timeout_rate_warn_delta=timeout_rate_warn_delta,
        timeout_rate_critical_delta=timeout_rate_critical_delta,
        latency_p95_warn_delta_ms=latency_p95_warn_delta_ms,
        latency_p95_critical_delta_ms=latency_p95_critical_delta_ms,
        breach_rate_warn_delta=breach_rate_warn_delta,
        breach_rate_critical_delta=breach_rate_critical_delta,
    )
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    snapshot_json_path = run_dir / "gateway_sla_trend_snapshot.json"
    summary_md_path = run_dir / "summary.md"
    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "gateway_sla_trend_snapshot",
        "status": "started",
        "params": {
            "sla_runs_dir": str(sla_runs_dir),
            "history_limit": history_limit,
            "baseline_window": baseline_window,
            "error_rate_warn_delta": error_rate_warn_delta,
            "error_rate_critical_delta": error_rate_critical_delta,
            "timeout_rate_warn_delta": timeout_rate_warn_delta,
            "timeout_rate_critical_delta": timeout_rate_critical_delta,
            "latency_p95_warn_delta_ms": latency_p95_warn_delta_ms,
            "latency_p95_critical_delta_ms": latency_p95_critical_delta_ms,
            "breach_rate_warn_delta": breach_rate_warn_delta,
            "breach_rate_critical_delta": breach_rate_critical_delta,
            "critical_policy": critical_policy,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "trend_snapshot_json": str(snapshot_json_path),
            "summary_md": str(summary_md_path),
        },
    }
    _write_json(run_json_path, run_payload)

    warnings: list[str] = []
    try:
        history_rows, warnings = _read_valid_sla_rows(sla_runs_dir)
        if not history_rows:
            raise ValueError(f"No valid {_SUMMARY_FILE_NAME} with status=ok found under {sla_runs_dir}")
        if len(history_rows) > history_limit:
            history_rows = history_rows[-history_limit:]

        latest = history_rows[-1]
        baseline_rows = history_rows[:-1]
        if len(baseline_rows) > baseline_window:
            baseline_rows = baseline_rows[-baseline_window:]

        baseline_count = len(baseline_rows)
        if baseline_count == 0:
            rolling_baseline = {
                "window": baseline_window,
                "count": 0,
                "run_names": [],
                "metrics_mean": None,
                "delta_latest_minus_baseline": None,
                "regression_flags": {
                    "comparison_evaluated": False,
                    "error_rate_status": "insufficient_history",
                    "timeout_rate_status": "insufficient_history",
                    "latency_p95_status": "insufficient_history",
                    "error_rate_regression_severity": "none",
                    "timeout_rate_regression_severity": "none",
                    "latency_p95_regression_severity": "none",
                    "max_regression_severity": "none",
                    "has_warn_or_higher_regression": False,
                    "has_any_regression": False,
                },
            }
            breach_drift = {
                "latest_is_breach": latest["sla_status"] == "breach",
                "baseline_breach_rate": None,
                "delta_breach_rate": None,
                "breach_rate_status": "insufficient_history",
                "breach_rate_severity": "none",
            }
        else:
            means = {
                "error_rate": sum(float(item["metrics"]["error_rate"]) for item in baseline_rows) / baseline_count,
                "timeout_rate": sum(float(item["metrics"]["timeout_rate"]) for item in baseline_rows) / baseline_count,
                "latency_p95_ms": sum(float(item["metrics"]["latency_p95_ms"]) for item in baseline_rows)
                / baseline_count,
            }
            deltas = {
                "delta_error_rate": float(latest["metrics"]["error_rate"]) - float(means["error_rate"]),
                "delta_timeout_rate": float(latest["metrics"]["timeout_rate"]) - float(means["timeout_rate"]),
                "delta_latency_p95_ms": float(latest["metrics"]["latency_p95_ms"]) - float(means["latency_p95_ms"]),
            }
            error_rate_status = _regression_status_higher_worse(float(deltas["delta_error_rate"]))
            timeout_rate_status = _regression_status_higher_worse(float(deltas["delta_timeout_rate"]))
            latency_status = _regression_status_higher_worse(float(deltas["delta_latency_p95_ms"]))
            error_rate_severity = _regression_severity(
                status=error_rate_status,
                magnitude=abs(float(deltas["delta_error_rate"])),
                warn_delta=error_rate_warn_delta,
                critical_delta=error_rate_critical_delta,
            )
            timeout_rate_severity = _regression_severity(
                status=timeout_rate_status,
                magnitude=abs(float(deltas["delta_timeout_rate"])),
                warn_delta=timeout_rate_warn_delta,
                critical_delta=timeout_rate_critical_delta,
            )
            latency_severity = _regression_severity(
                status=latency_status,
                magnitude=abs(float(deltas["delta_latency_p95_ms"])),
                warn_delta=latency_p95_warn_delta_ms,
                critical_delta=latency_p95_critical_delta_ms,
            )
            max_regression_severity = _max_severity(error_rate_severity, timeout_rate_severity, latency_severity)
            rolling_baseline = {
                "window": baseline_window,
                "count": baseline_count,
                "run_names": [str(item["run_name"]) for item in baseline_rows],
                "metrics_mean": means,
                "delta_latest_minus_baseline": deltas,
                "regression_flags": {
                    "comparison_evaluated": True,
                    "error_rate_status": error_rate_status,
                    "timeout_rate_status": timeout_rate_status,
                    "latency_p95_status": latency_status,
                    "error_rate_regression_severity": error_rate_severity,
                    "timeout_rate_regression_severity": timeout_rate_severity,
                    "latency_p95_regression_severity": latency_severity,
                    "max_regression_severity": max_regression_severity,
                    "has_warn_or_higher_regression": max_regression_severity != "none",
                    "has_any_regression": (
                        error_rate_status == "regressed"
                        or timeout_rate_status == "regressed"
                        or latency_status == "regressed"
                    ),
                },
            }
            baseline_breach_rate = sum(1.0 for item in baseline_rows if item["sla_status"] == "breach") / baseline_count
            latest_breach_value = 1.0 if latest["sla_status"] == "breach" else 0.0
            delta_breach_rate = latest_breach_value - baseline_breach_rate
            breach_rate_status = _regression_status_higher_worse(delta_breach_rate)
            breach_rate_severity = _regression_severity(
                status=breach_rate_status,
                magnitude=abs(delta_breach_rate),
                warn_delta=breach_rate_warn_delta,
                critical_delta=breach_rate_critical_delta,
            )
            breach_drift = {
                "latest_is_breach": bool(latest_breach_value),
                "baseline_breach_rate": baseline_breach_rate,
                "delta_breach_rate": delta_breach_rate,
                "breach_rate_status": breach_rate_status,
                "breach_rate_severity": breach_rate_severity,
            }

        metric_max_severity = str(rolling_baseline["regression_flags"]["max_regression_severity"])
        breach_rate_severity = str(breach_drift["breach_rate_severity"])
        has_critical_regression = _max_severity(metric_max_severity, breach_rate_severity) == "critical"
        should_fail_nightly = critical_policy == "fail_nightly" and has_critical_regression

        snapshot_payload: dict[str, Any] = {
            "schema_version": "gateway_sla_trend_snapshot_v1",
            "status": "ok",
            "checked_at_utc": _utc_now(),
            "history_limit": history_limit,
            "baseline_window": baseline_window,
            "severity_thresholds": {
                "error_rate": {
                    "warn_delta_latest_minus_baseline": error_rate_warn_delta,
                    "critical_delta_latest_minus_baseline": error_rate_critical_delta,
                },
                "timeout_rate": {
                    "warn_delta_latest_minus_baseline": timeout_rate_warn_delta,
                    "critical_delta_latest_minus_baseline": timeout_rate_critical_delta,
                },
                "latency_p95_ms": {
                    "warn_delta_latest_minus_baseline": latency_p95_warn_delta_ms,
                    "critical_delta_latest_minus_baseline": latency_p95_critical_delta_ms,
                },
                "breach_rate": {
                    "warn_delta_latest_minus_baseline": breach_rate_warn_delta,
                    "critical_delta_latest_minus_baseline": breach_rate_critical_delta,
                },
            },
            "latest": latest,
            "history": history_rows,
            "rolling_baseline": rolling_baseline,
            "breach_drift": breach_drift,
            "warnings": warnings,
            "critical_policy": {
                "mode": critical_policy,
                "has_critical_regression": has_critical_regression,
                "critical_signals": {
                    "metrics_max_severity": metric_max_severity,
                    "breach_rate_severity": breach_rate_severity,
                },
                "should_fail_nightly": should_fail_nightly,
            },
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "trend_snapshot_json": str(snapshot_json_path),
                "summary_md": str(summary_md_path),
            },
            "exit_code": 2 if should_fail_nightly else 0,
            "error": None,
        }
        _write_json(snapshot_json_path, snapshot_payload)
        _write_summary_md(summary_md_path, snapshot=snapshot_payload)

        run_payload["status"] = "error" if should_fail_nightly else "ok"
        if should_fail_nightly:
            run_payload["error_code"] = "critical_regression_policy_failed"
            run_payload["error"] = "Critical SLA regression detected and critical_policy=fail_nightly."
        run_payload["result"] = {
            "latest_checked_at_utc": latest["checked_at_utc"],
            "baseline_count": rolling_baseline["count"],
            "has_any_regression": rolling_baseline["regression_flags"]["has_any_regression"],
            "metric_max_regression_severity": metric_max_severity,
            "breach_rate_status": breach_drift["breach_rate_status"],
            "breach_rate_severity": breach_rate_severity,
            "critical_policy": critical_policy,
            "has_critical_regression": has_critical_regression,
            "should_fail_nightly": should_fail_nightly,
            "warnings_count": len(warnings),
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": not should_fail_nightly,
            "exit_code": 2 if should_fail_nightly else 0,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "snapshot_payload": snapshot_payload,
        }
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        snapshot_payload = {
            "schema_version": "gateway_sla_trend_snapshot_v1",
            "status": "error",
            "checked_at_utc": _utc_now(),
            "history_limit": history_limit,
            "baseline_window": baseline_window,
            "latest": None,
            "rolling_baseline": None,
            "breach_drift": None,
            "warnings": warnings,
            "critical_policy": {
                "mode": critical_policy,
                "has_critical_regression": False,
                "critical_signals": {
                    "metrics_max_severity": "none",
                    "breach_rate_severity": "none",
                },
                "should_fail_nightly": False,
            },
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "trend_snapshot_json": str(snapshot_json_path),
                "summary_md": str(summary_md_path),
            },
            "exit_code": 2,
            "error": str(exc),
        }
        _write_json(snapshot_json_path, snapshot_payload)
        _write_summary_md(summary_md_path, snapshot=snapshot_payload)
        run_payload["status"] = "error"
        run_payload["error_code"] = "gateway_sla_trend_failed"
        run_payload["error"] = str(exc)
        run_payload["result"] = {
            "critical_policy": critical_policy,
            "warnings_count": len(warnings),
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "exit_code": 2,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "snapshot_payload": snapshot_payload,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build rolling SLA trend snapshot from gateway_sla_summary_v1 history.")
    parser.add_argument(
        "--sla-runs-dir",
        type=Path,
        default=Path("runs") / "ci-smoke-gateway-sla",
        help="Root directory containing gateway_sla_summary.json history.",
    )
    parser.add_argument("--history-limit", type=int, default=10, help="Number of latest SLA summaries to consider.")
    parser.add_argument(
        "--baseline-window",
        type=int,
        default=5,
        help="Number of previous runs used for rolling baseline mean.",
    )
    parser.add_argument(
        "--error-rate-warn-delta",
        type=float,
        default=_DEFAULT_ERROR_RATE_WARN_DELTA,
        help="error_rate warn threshold for abs(latest-baseline).",
    )
    parser.add_argument(
        "--error-rate-critical-delta",
        type=float,
        default=_DEFAULT_ERROR_RATE_CRITICAL_DELTA,
        help="error_rate critical threshold for abs(latest-baseline).",
    )
    parser.add_argument(
        "--timeout-rate-warn-delta",
        type=float,
        default=_DEFAULT_TIMEOUT_RATE_WARN_DELTA,
        help="timeout_rate warn threshold for abs(latest-baseline).",
    )
    parser.add_argument(
        "--timeout-rate-critical-delta",
        type=float,
        default=_DEFAULT_TIMEOUT_RATE_CRITICAL_DELTA,
        help="timeout_rate critical threshold for abs(latest-baseline).",
    )
    parser.add_argument(
        "--latency-p95-warn-delta-ms",
        type=float,
        default=_DEFAULT_LATENCY_P95_WARN_DELTA_MS,
        help="latency_p95_ms warn threshold for abs(latest-baseline).",
    )
    parser.add_argument(
        "--latency-p95-critical-delta-ms",
        type=float,
        default=_DEFAULT_LATENCY_P95_CRITICAL_DELTA_MS,
        help="latency_p95_ms critical threshold for abs(latest-baseline).",
    )
    parser.add_argument(
        "--breach-rate-warn-delta",
        type=float,
        default=_DEFAULT_BREACH_RATE_WARN_DELTA,
        help="breach-rate warn threshold for abs(latest-baseline).",
    )
    parser.add_argument(
        "--breach-rate-critical-delta",
        type=float,
        default=_DEFAULT_BREACH_RATE_CRITICAL_DELTA,
        help="breach-rate critical threshold for abs(latest-baseline).",
    )
    parser.add_argument(
        "--critical-policy",
        choices=_CRITICAL_POLICIES,
        default="signal_only",
        help="Policy for critical severity: signal_only (default) or fail_nightly.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs") / "ci-smoke-gateway-sla-trend",
        help="Run artifact base directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_trend_snapshot(
        sla_runs_dir=args.sla_runs_dir,
        history_limit=args.history_limit,
        baseline_window=args.baseline_window,
        error_rate_warn_delta=args.error_rate_warn_delta,
        error_rate_critical_delta=args.error_rate_critical_delta,
        timeout_rate_warn_delta=args.timeout_rate_warn_delta,
        timeout_rate_critical_delta=args.timeout_rate_critical_delta,
        latency_p95_warn_delta_ms=args.latency_p95_warn_delta_ms,
        latency_p95_critical_delta_ms=args.latency_p95_critical_delta_ms,
        breach_rate_warn_delta=args.breach_rate_warn_delta,
        breach_rate_critical_delta=args.breach_rate_critical_delta,
        critical_policy=args.critical_policy,
        runs_dir=args.runs_dir,
    )
    snapshot_payload = result["snapshot_payload"]
    print(f"[gateway_sla_trend_snapshot] run_dir: {result['run_dir']}")
    print(f"[gateway_sla_trend_snapshot] run_json: {result['run_payload']['paths']['run_json']}")
    print(
        f"[gateway_sla_trend_snapshot] trend_snapshot_json: "
        f"{result['run_payload']['paths']['trend_snapshot_json']}"
    )
    print(f"[gateway_sla_trend_snapshot] summary_md: {result['run_payload']['paths']['summary_md']}")
    if isinstance(snapshot_payload, Mapping):
        print(f"[gateway_sla_trend_snapshot] status: {snapshot_payload.get('status')}")
        print(f"[gateway_sla_trend_snapshot] exit_code: {snapshot_payload.get('exit_code')}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
