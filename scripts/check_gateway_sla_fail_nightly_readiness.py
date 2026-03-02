from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_SEVERITY_RANK = {"none": 0, "warn": 1, "critical": 2}
_SEVERITIES: tuple[str, ...] = ("none", "warn", "critical")
_POLICIES: tuple[str, ...] = ("report_only", "fail_if_not_ready")
_TREND_FILE_NAME = "gateway_sla_trend_snapshot.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-fail-readiness")
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


def _max_severity(*values: str) -> str:
    normalized = [value if value in _SEVERITIES else "none" for value in values]
    return max(normalized, key=lambda item: _SEVERITY_RANK.get(item, 0))


def _parse_iso_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("checked_at_utc must be a non-empty string.")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _collect_snapshot_rows(
    *,
    trend_runs_dir: Path,
    history_limit: int,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    if not trend_runs_dir.exists():
        return [], 0, [f"trend_runs_dir does not exist: {trend_runs_dir}"]

    paths = sorted(trend_runs_dir.glob(f"**/{_TREND_FILE_NAME}"), key=lambda item: str(item))
    if history_limit > 0 and len(paths) > history_limit:
        paths = paths[-history_limit:]

    warnings: list[str] = []
    valid_rows: list[dict[str, Any]] = []
    invalid_or_error_count = 0

    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("snapshot root must be object")
            if payload.get("schema_version") != "gateway_sla_trend_snapshot_v1":
                raise ValueError("schema_version must be gateway_sla_trend_snapshot_v1")
            if payload.get("status") != "ok":
                raise ValueError("snapshot status must be ok")

            checked_at = _parse_iso_datetime(payload.get("checked_at_utc"))
            rolling = payload.get("rolling_baseline")
            if not isinstance(rolling, Mapping):
                raise ValueError("rolling_baseline must be object")
            flags = rolling.get("regression_flags")
            if not isinstance(flags, Mapping):
                raise ValueError("rolling_baseline.regression_flags must be object")
            metrics_severity = str(flags.get("max_regression_severity", "none"))
            breach_drift = payload.get("breach_drift")
            if not isinstance(breach_drift, Mapping):
                raise ValueError("breach_drift must be object")
            breach_severity = str(breach_drift.get("breach_rate_severity", "none"))
            aggregated_severity = _max_severity(metrics_severity, breach_severity)
            baseline_count = int(rolling.get("count", 0))
            latest = payload.get("latest")
            latest_sla_status = None
            if isinstance(latest, Mapping):
                latest_sla_status = latest.get("sla_status")
            valid_rows.append(
                {
                    "checked_at_utc": checked_at.astimezone(timezone.utc).isoformat(),
                    "checked_at_epoch": checked_at.timestamp(),
                    "run_name": path.parent.name,
                    "trend_snapshot_json": str(path),
                    "severity": aggregated_severity,
                    "metrics_max_severity": metrics_severity,
                    "breach_rate_severity": breach_severity,
                    "baseline_count": baseline_count,
                    "latest_sla_status": latest_sla_status,
                }
            )
        except Exception as exc:
            invalid_or_error_count += 1
            warnings.append(f"{path}: skipped ({exc})")

    valid_rows.sort(key=lambda item: (float(item["checked_at_epoch"]), str(item["run_name"])))
    return valid_rows, invalid_or_error_count, warnings


def _readiness_reason_codes(
    *,
    window_observed: int,
    readiness_window: int,
    critical_count: int,
    warn_ratio: float,
    max_warn_ratio: float,
    insufficient_history_count: int,
    invalid_or_error_count: int,
) -> list[str]:
    reason_codes: list[str] = []
    if window_observed < readiness_window:
        reason_codes.append("insufficient_window")
    if critical_count > 0:
        reason_codes.append("critical_regression_present")
    if warn_ratio > max_warn_ratio:
        reason_codes.append("warn_ratio_above_threshold")
    if insufficient_history_count > 0:
        reason_codes.append("insufficient_baseline_count_in_window")
    if invalid_or_error_count > 0:
        reason_codes.append("invalid_or_error_snapshots_present")
    return reason_codes


def run_gateway_sla_fail_nightly_readiness(
    *,
    trend_runs_dir: Path = Path("runs") / "nightly-gateway-sla-trend-history",
    history_limit: int = 30,
    readiness_window: int = 14,
    required_baseline_count: int = 5,
    max_warn_ratio: float = 0.20,
    policy: str = "report_only",
    runs_dir: Path = Path("runs") / "nightly-gateway-sla-readiness",
    summary_json: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if history_limit <= 0:
        raise ValueError("history_limit must be > 0.")
    if readiness_window <= 0:
        raise ValueError("readiness_window must be > 0.")
    if required_baseline_count <= 0:
        raise ValueError("required_baseline_count must be > 0.")
    if max_warn_ratio < 0:
        raise ValueError("max_warn_ratio must be >= 0.")
    if policy not in _POLICIES:
        raise ValueError(f"policy must be one of: {', '.join(_POLICIES)}")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    summary_out_path = summary_json if summary_json is not None else (runs_dir / "readiness_summary.json")

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "gateway_sla_fail_nightly_readiness",
        "status": "started",
        "params": {
            "trend_runs_dir": str(trend_runs_dir),
            "history_limit": history_limit,
            "readiness_window": readiness_window,
            "required_baseline_count": required_baseline_count,
            "max_warn_ratio": max_warn_ratio,
            "policy": policy,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_out_path),
        },
    }
    _write_json(run_json_path, run_payload)

    warnings: list[str] = []
    invalid_or_error_count = 0
    try:
        valid_rows, invalid_or_error_count, warnings = _collect_snapshot_rows(
            trend_runs_dir=trend_runs_dir,
            history_limit=history_limit,
        )
        if not valid_rows:
            raise ValueError(f"No valid {_TREND_FILE_NAME} found under {trend_runs_dir}")

        window_rows = valid_rows[-readiness_window:]
        window_observed = len(window_rows)
        critical_count = sum(1 for row in window_rows if row["severity"] == "critical")
        warn_count = sum(1 for row in window_rows if row["severity"] == "warn")
        none_count = sum(1 for row in window_rows if row["severity"] == "none")
        warn_ratio = (warn_count / window_observed) if window_observed > 0 else 0.0
        insufficient_history_count = sum(
            1 for row in window_rows if int(row["baseline_count"]) < required_baseline_count
        )

        reason_codes = _readiness_reason_codes(
            window_observed=window_observed,
            readiness_window=readiness_window,
            critical_count=critical_count,
            warn_ratio=warn_ratio,
            max_warn_ratio=max_warn_ratio,
            insufficient_history_count=insufficient_history_count,
            invalid_or_error_count=invalid_or_error_count,
        )
        ready = len(reason_codes) == 0
        readiness_status = "ready" if ready else "not_ready"

        exit_code = 0
        if policy == "fail_if_not_ready" and not ready:
            exit_code = 2

        latest = window_rows[-1] if window_rows else valid_rows[-1]
        summary_payload: dict[str, Any] = {
            "schema_version": "gateway_sla_fail_nightly_readiness_v1",
            "status": "ok",
            "readiness_status": readiness_status,
            "checked_at_utc": _utc_now(),
            "criteria": {
                "readiness_window": readiness_window,
                "required_baseline_count": required_baseline_count,
                "max_warn_ratio": max_warn_ratio,
                "window_observed": window_observed,
            },
            "window_summary": {
                "critical_count": critical_count,
                "warn_count": warn_count,
                "none_count": none_count,
                "warn_ratio": warn_ratio,
                "insufficient_history_count": insufficient_history_count,
                "invalid_or_error_count": invalid_or_error_count,
            },
            "latest": latest,
            "recommendation": {
                "target_critical_policy": "fail_nightly" if ready else "signal_only",
                "reason_codes": reason_codes,
            },
            "policy": policy,
            "exit_code": exit_code,
            "warnings": warnings,
            "error": None,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
            },
        }
        _write_json(summary_out_path, summary_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "readiness_status": readiness_status,
            "target_critical_policy": summary_payload["recommendation"]["target_critical_policy"],
            "reason_codes": reason_codes,
            "exit_code": exit_code,
            "warnings_count": len(warnings),
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": exit_code == 0,
            "exit_code": exit_code,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
        }
    except (FileNotFoundError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        summary_payload = {
            "schema_version": "gateway_sla_fail_nightly_readiness_v1",
            "status": "error",
            "readiness_status": "not_ready",
            "checked_at_utc": _utc_now(),
            "criteria": {
                "readiness_window": readiness_window,
                "required_baseline_count": required_baseline_count,
                "max_warn_ratio": max_warn_ratio,
                "window_observed": 0,
            },
            "window_summary": {
                "critical_count": 0,
                "warn_count": 0,
                "none_count": 0,
                "warn_ratio": 0.0,
                "insufficient_history_count": 0,
                "invalid_or_error_count": invalid_or_error_count,
            },
            "latest": None,
            "recommendation": {
                "target_critical_policy": "signal_only",
                "reason_codes": ["readiness_evaluation_failed"],
            },
            "policy": policy,
            "exit_code": 2,
            "warnings": warnings,
            "error": str(exc),
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
            },
        }
        _write_json(summary_out_path, summary_payload)
        run_payload["status"] = "error"
        run_payload["error_code"] = "gateway_sla_fail_readiness_failed"
        run_payload["error"] = str(exc)
        run_payload["result"] = {"exit_code": 2}
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "exit_code": 2,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate readiness to switch gateway SLA trend critical_policy to fail_nightly."
    )
    parser.add_argument(
        "--trend-runs-dir",
        type=Path,
        default=Path("runs") / "nightly-gateway-sla-trend-history",
        help="Directory with gateway_sla_trend_snapshot.json history.",
    )
    parser.add_argument("--history-limit", type=int, default=30, help="Latest trend snapshots to inspect.")
    parser.add_argument(
        "--readiness-window",
        type=int,
        default=14,
        help="Latest valid snapshots used for readiness decision.",
    )
    parser.add_argument(
        "--required-baseline-count",
        type=int,
        default=5,
        help="Minimum rolling baseline count per snapshot in readiness window.",
    )
    parser.add_argument(
        "--max-warn-ratio",
        type=float,
        default=0.20,
        help="Maximum allowed warn ratio in readiness window.",
    )
    parser.add_argument(
        "--policy",
        choices=_POLICIES,
        default="report_only",
        help="Exit policy: report_only (default) or fail_if_not_ready.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs") / "nightly-gateway-sla-readiness",
        help="Run artifact base directory.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Output path for gateway_sla_fail_nightly_readiness_v1 summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_fail_nightly_readiness(
        trend_runs_dir=args.trend_runs_dir,
        history_limit=args.history_limit,
        readiness_window=args.readiness_window,
        required_baseline_count=args.required_baseline_count,
        max_warn_ratio=args.max_warn_ratio,
        policy=args.policy,
        runs_dir=args.runs_dir,
        summary_json=args.summary_json,
    )
    summary_payload = result["summary_payload"]
    print(f"[check_gateway_sla_fail_nightly_readiness] run_dir: {result['run_dir']}")
    print(f"[check_gateway_sla_fail_nightly_readiness] run_json: {result['run_payload']['paths']['run_json']}")
    print(
        "[check_gateway_sla_fail_nightly_readiness] "
        f"summary_json: {result['run_payload']['paths']['summary_json']}"
    )
    print(f"[check_gateway_sla_fail_nightly_readiness] status: {summary_payload['status']}")
    print(
        "[check_gateway_sla_fail_nightly_readiness] "
        f"readiness_status: {summary_payload['readiness_status']}"
    )
    print(f"[check_gateway_sla_fail_nightly_readiness] exit_code: {summary_payload['exit_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
