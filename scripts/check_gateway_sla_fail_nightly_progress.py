from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_POLICIES: tuple[str, ...] = ("report_only", "fail_if_not_go")
_READINESS_FILE_NAME = "readiness_summary.json"
_GOVERNANCE_FILE_NAME = "governance_summary.json"
_PROGRESS_FILE_NAME = "progress_summary.json"
_EPSILON = 1e-9


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-fail-progress")
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


def _parse_iso_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("checked_at_utc must be a non-empty string.")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _collect_summary_paths(*, runs_dir: Path, file_name: str) -> list[Path]:
    all_paths = sorted(runs_dir.glob(f"**/{file_name}"), key=lambda item: str(item))
    nested_paths = [path for path in all_paths if path.parent != runs_dir]
    if nested_paths:
        return nested_paths
    return all_paths


def _float_matches(observed: Any, expected: float) -> bool:
    return abs(float(observed) - float(expected)) <= _EPSILON


def _criteria_match_readiness(
    *,
    criteria: Mapping[str, Any],
    expected_readiness_window: int,
    expected_required_baseline_count: int,
    expected_max_warn_ratio: float,
) -> bool:
    if int(criteria.get("readiness_window", -1)) != expected_readiness_window:
        return False
    if int(criteria.get("required_baseline_count", -1)) != expected_required_baseline_count:
        return False
    return _float_matches(criteria.get("max_warn_ratio", -1.0), expected_max_warn_ratio)


def _criteria_match_governance(
    *,
    criteria: Mapping[str, Any],
    required_ready_streak: int,
    expected_readiness_window: int,
    expected_required_baseline_count: int,
    expected_max_warn_ratio: float,
) -> bool:
    if int(criteria.get("required_ready_streak", -1)) != required_ready_streak:
        return False
    if int(criteria.get("expected_readiness_window", -1)) != expected_readiness_window:
        return False
    if int(criteria.get("expected_required_baseline_count", -1)) != expected_required_baseline_count:
        return False
    return _float_matches(criteria.get("expected_max_warn_ratio", -1.0), expected_max_warn_ratio)


def _collect_readiness_rows(
    *,
    readiness_runs_dir: Path,
    history_limit: int,
    expected_readiness_window: int,
    expected_required_baseline_count: int,
    expected_max_warn_ratio: float,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    if not readiness_runs_dir.exists():
        return [], 0, [f"readiness_runs_dir does not exist: {readiness_runs_dir}"]

    paths = _collect_summary_paths(runs_dir=readiness_runs_dir, file_name=_READINESS_FILE_NAME)
    if history_limit > 0 and len(paths) > history_limit:
        paths = paths[-history_limit:]

    warnings: list[str] = []
    invalid_or_mismatched_count = 0
    rows: list[dict[str, Any]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("readiness summary root must be object")
            if payload.get("schema_version") != "gateway_sla_fail_nightly_readiness_v1":
                raise ValueError("schema_version must be gateway_sla_fail_nightly_readiness_v1")
            if payload.get("status") != "ok":
                raise ValueError("status must be ok")
            readiness_status = str(payload.get("readiness_status", "")).strip()
            if readiness_status not in {"ready", "not_ready"}:
                raise ValueError("readiness_status must be ready|not_ready")
            criteria = payload.get("criteria")
            if not isinstance(criteria, Mapping):
                raise ValueError("criteria must be object")
            if not _criteria_match_readiness(
                criteria=criteria,
                expected_readiness_window=expected_readiness_window,
                expected_required_baseline_count=expected_required_baseline_count,
                expected_max_warn_ratio=expected_max_warn_ratio,
            ):
                raise ValueError("criteria mismatch against expected readiness baseline")
            checked_at = _parse_iso_datetime(payload.get("checked_at_utc"))
            recommendation = payload.get("recommendation")
            target_critical_policy = None
            if isinstance(recommendation, Mapping):
                target_critical_policy = recommendation.get("target_critical_policy")
            rows.append(
                {
                    "checked_at_utc": checked_at.astimezone(timezone.utc).isoformat(),
                    "checked_at_epoch": checked_at.timestamp(),
                    "run_name": path.parent.name,
                    "readiness_summary_json": str(path),
                    "readiness_status": readiness_status,
                    "window_observed": int(criteria.get("window_observed", 0)),
                    "target_critical_policy": target_critical_policy,
                }
            )
        except Exception as exc:
            invalid_or_mismatched_count += 1
            warnings.append(f"{path}: skipped ({exc})")

    rows.sort(key=lambda item: (float(item["checked_at_epoch"]), str(item["run_name"])))
    return rows, invalid_or_mismatched_count, warnings


def _collect_governance_rows(
    *,
    governance_runs_dir: Path,
    history_limit: int,
    required_ready_streak: int,
    expected_readiness_window: int,
    expected_required_baseline_count: int,
    expected_max_warn_ratio: float,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    if not governance_runs_dir.exists():
        return [], 0, [f"governance_runs_dir does not exist: {governance_runs_dir}"]

    paths = _collect_summary_paths(runs_dir=governance_runs_dir, file_name=_GOVERNANCE_FILE_NAME)
    if history_limit > 0 and len(paths) > history_limit:
        paths = paths[-history_limit:]

    warnings: list[str] = []
    invalid_or_mismatched_count = 0
    rows: list[dict[str, Any]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("governance summary root must be object")
            if payload.get("schema_version") != "gateway_sla_fail_nightly_governance_v1":
                raise ValueError("schema_version must be gateway_sla_fail_nightly_governance_v1")
            if payload.get("status") != "ok":
                raise ValueError("status must be ok")
            decision_status = str(payload.get("decision_status", "")).strip()
            if decision_status not in {"go", "hold"}:
                raise ValueError("decision_status must be go|hold")
            criteria = payload.get("criteria")
            if not isinstance(criteria, Mapping):
                raise ValueError("criteria must be object")
            if not _criteria_match_governance(
                criteria=criteria,
                required_ready_streak=required_ready_streak,
                expected_readiness_window=expected_readiness_window,
                expected_required_baseline_count=expected_required_baseline_count,
                expected_max_warn_ratio=expected_max_warn_ratio,
            ):
                raise ValueError("criteria mismatch against expected governance baseline")
            checked_at = _parse_iso_datetime(payload.get("checked_at_utc"))
            observed = payload.get("observed")
            if not isinstance(observed, Mapping):
                raise ValueError("observed must be object")
            recommendation = payload.get("recommendation")
            target_critical_policy = None
            switch_surface = None
            if isinstance(recommendation, Mapping):
                target_critical_policy = recommendation.get("target_critical_policy")
                switch_surface = recommendation.get("switch_surface")
            rows.append(
                {
                    "checked_at_utc": checked_at.astimezone(timezone.utc).isoformat(),
                    "checked_at_epoch": checked_at.timestamp(),
                    "run_name": path.parent.name,
                    "governance_summary_json": str(path),
                    "decision_status": decision_status,
                    "latest_ready_streak": int(observed.get("latest_ready_streak", 0)),
                    "target_critical_policy": target_critical_policy,
                    "switch_surface": switch_surface,
                }
            )
        except Exception as exc:
            invalid_or_mismatched_count += 1
            warnings.append(f"{path}: skipped ({exc})")

    rows.sort(key=lambda item: (float(item["checked_at_epoch"]), str(item["run_name"])))
    return rows, invalid_or_mismatched_count, warnings


def _compute_ready_streak(rows: list[dict[str, Any]]) -> int:
    streak = 0
    for row in reversed(rows):
        if row["readiness_status"] != "ready":
            break
        streak += 1
    return streak


def run_gateway_sla_fail_nightly_progress(
    *,
    readiness_runs_dir: Path = Path("runs") / "nightly-gateway-sla-readiness",
    governance_runs_dir: Path = Path("runs") / "nightly-gateway-sla-governance",
    readiness_history_limit: int = 60,
    governance_history_limit: int = 60,
    expected_readiness_window: int = 14,
    expected_required_baseline_count: int = 5,
    expected_max_warn_ratio: float = 0.20,
    required_ready_streak: int = 3,
    policy: str = "report_only",
    runs_dir: Path = Path("runs") / "nightly-gateway-sla-progress",
    summary_json: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if readiness_history_limit <= 0:
        raise ValueError("readiness_history_limit must be > 0.")
    if governance_history_limit <= 0:
        raise ValueError("governance_history_limit must be > 0.")
    if expected_readiness_window <= 0:
        raise ValueError("expected_readiness_window must be > 0.")
    if expected_required_baseline_count <= 0:
        raise ValueError("expected_required_baseline_count must be > 0.")
    if expected_max_warn_ratio < 0:
        raise ValueError("expected_max_warn_ratio must be >= 0.")
    if required_ready_streak <= 0:
        raise ValueError("required_ready_streak must be > 0.")
    if policy not in _POLICIES:
        raise ValueError(f"policy must be one of: {', '.join(_POLICIES)}")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    summary_out_path = summary_json if summary_json is not None else (runs_dir / _PROGRESS_FILE_NAME)
    history_summary_path = run_dir / _PROGRESS_FILE_NAME

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "gateway_sla_fail_nightly_progress",
        "status": "started",
        "params": {
            "readiness_runs_dir": str(readiness_runs_dir),
            "governance_runs_dir": str(governance_runs_dir),
            "readiness_history_limit": readiness_history_limit,
            "governance_history_limit": governance_history_limit,
            "expected_readiness_window": expected_readiness_window,
            "expected_required_baseline_count": expected_required_baseline_count,
            "expected_max_warn_ratio": expected_max_warn_ratio,
            "required_ready_streak": required_ready_streak,
            "policy": policy,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_out_path),
            "history_summary_json": str(history_summary_path),
        },
    }
    _write_json(run_json_path, run_payload)

    readiness_invalid_or_mismatched_count = 0
    governance_invalid_or_mismatched_count = 0
    warnings: list[str] = []
    try:
        readiness_rows, readiness_invalid_or_mismatched_count, readiness_warnings = _collect_readiness_rows(
            readiness_runs_dir=readiness_runs_dir,
            history_limit=readiness_history_limit,
            expected_readiness_window=expected_readiness_window,
            expected_required_baseline_count=expected_required_baseline_count,
            expected_max_warn_ratio=expected_max_warn_ratio,
        )
        warnings.extend(readiness_warnings)

        governance_rows, governance_invalid_or_mismatched_count, governance_warnings = _collect_governance_rows(
            governance_runs_dir=governance_runs_dir,
            history_limit=governance_history_limit,
            required_ready_streak=required_ready_streak,
            expected_readiness_window=expected_readiness_window,
            expected_required_baseline_count=expected_required_baseline_count,
            expected_max_warn_ratio=expected_max_warn_ratio,
        )
        warnings.extend(governance_warnings)

        if not readiness_rows:
            raise ValueError(f"No valid {_READINESS_FILE_NAME} found under {readiness_runs_dir}")

        latest_readiness = readiness_rows[-1]
        latest_ready_streak = _compute_ready_streak(readiness_rows)
        latest_window_observed = int(latest_readiness.get("window_observed", 0))
        remaining_for_window = max(0, expected_readiness_window - latest_window_observed)
        remaining_for_streak = max(0, required_ready_streak - latest_ready_streak)
        ready_count_in_history = sum(1 for row in readiness_rows if row["readiness_status"] == "ready")

        latest_governance = governance_rows[-1] if governance_rows else None
        latest_governance_status = None if latest_governance is None else latest_governance["decision_status"]
        latest_governance_ready_streak = (
            0 if latest_governance is None else int(latest_governance.get("latest_ready_streak", 0))
        )
        go_count_in_history = sum(1 for row in governance_rows if row["decision_status"] == "go")

        decision_go = (
            latest_governance is not None
            and latest_governance_status == "go"
            and governance_invalid_or_mismatched_count == 0
        )
        decision_status = "go" if decision_go else "hold"

        reason_codes: list[str] = []
        if latest_readiness["readiness_status"] != "ready":
            reason_codes.append("latest_readiness_not_ready")
        if remaining_for_window > 0:
            reason_codes.append("insufficient_window_observed")
        if latest_ready_streak < required_ready_streak:
            reason_codes.append("ready_streak_below_threshold")
        if readiness_invalid_or_mismatched_count > 0:
            reason_codes.append("invalid_or_mismatched_readiness_present")
        if latest_governance is None:
            reason_codes.append("governance_history_missing")
        elif latest_governance_status != "go":
            reason_codes.append("latest_governance_hold")
        if governance_invalid_or_mismatched_count > 0:
            reason_codes.append("invalid_or_mismatched_governance_present")
        if decision_go:
            reason_codes = []

        exit_code = 0
        if policy == "fail_if_not_go" and not decision_go:
            exit_code = 2

        summary_payload: dict[str, Any] = {
            "schema_version": "gateway_sla_fail_nightly_progress_v1",
            "status": "ok",
            "decision_status": decision_status,
            "checked_at_utc": _utc_now(),
            "policy": policy,
            "criteria": {
                "expected_readiness_window": expected_readiness_window,
                "expected_required_baseline_count": expected_required_baseline_count,
                "expected_max_warn_ratio": expected_max_warn_ratio,
                "required_ready_streak": required_ready_streak,
                "readiness_history_limit": readiness_history_limit,
                "governance_history_limit": governance_history_limit,
            },
            "observed": {
                "readiness": {
                    "valid_count": len(readiness_rows),
                    "invalid_or_mismatched_count": readiness_invalid_or_mismatched_count,
                    "latest_status": latest_readiness["readiness_status"],
                    "latest_window_observed": latest_window_observed,
                    "latest_ready_streak": latest_ready_streak,
                    "ready_count_in_history": ready_count_in_history,
                    "remaining_for_window": remaining_for_window,
                    "remaining_for_streak": remaining_for_streak,
                },
                "governance": {
                    "valid_count": len(governance_rows),
                    "invalid_or_mismatched_count": governance_invalid_or_mismatched_count,
                    "latest_decision_status": latest_governance_status,
                    "latest_ready_streak": latest_governance_ready_streak,
                    "go_count_in_history": go_count_in_history,
                },
            },
            "latest": {
                "readiness": latest_readiness,
                "governance": latest_governance,
            },
            "recommendation": {
                "target_critical_policy": "fail_nightly" if decision_go else "signal_only",
                "switch_surface": "nightly_only",
                "reason_codes": reason_codes,
            },
            "warnings": warnings,
            "error": None,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
                "history_summary_json": str(history_summary_path),
            },
            "exit_code": exit_code,
        }
        for output_path in {summary_out_path, history_summary_path}:
            _write_json(output_path, summary_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "decision_status": decision_status,
            "target_critical_policy": summary_payload["recommendation"]["target_critical_policy"],
            "latest_ready_streak": latest_ready_streak,
            "latest_window_observed": latest_window_observed,
            "remaining_for_window": remaining_for_window,
            "remaining_for_streak": remaining_for_streak,
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
    except (FileNotFoundError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        summary_payload = {
            "schema_version": "gateway_sla_fail_nightly_progress_v1",
            "status": "error",
            "decision_status": "hold",
            "checked_at_utc": _utc_now(),
            "policy": policy,
            "criteria": {
                "expected_readiness_window": expected_readiness_window,
                "expected_required_baseline_count": expected_required_baseline_count,
                "expected_max_warn_ratio": expected_max_warn_ratio,
                "required_ready_streak": required_ready_streak,
                "readiness_history_limit": readiness_history_limit,
                "governance_history_limit": governance_history_limit,
            },
            "observed": {
                "readiness": {
                    "valid_count": 0,
                    "invalid_or_mismatched_count": readiness_invalid_or_mismatched_count,
                    "latest_status": None,
                    "latest_window_observed": 0,
                    "latest_ready_streak": 0,
                    "ready_count_in_history": 0,
                    "remaining_for_window": expected_readiness_window,
                    "remaining_for_streak": required_ready_streak,
                },
                "governance": {
                    "valid_count": 0,
                    "invalid_or_mismatched_count": governance_invalid_or_mismatched_count,
                    "latest_decision_status": None,
                    "latest_ready_streak": 0,
                    "go_count_in_history": 0,
                },
            },
            "latest": {
                "readiness": None,
                "governance": None,
            },
            "recommendation": {
                "target_critical_policy": "signal_only",
                "switch_surface": "nightly_only",
                "reason_codes": ["progress_evaluation_failed"],
            },
            "warnings": warnings,
            "error": str(exc),
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
                "history_summary_json": str(history_summary_path),
            },
            "exit_code": 2,
        }
        for output_path in {summary_out_path, history_summary_path}:
            _write_json(output_path, summary_payload)
        run_payload["status"] = "error"
        run_payload["error_code"] = "gateway_sla_fail_progress_failed"
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
        description="Build progress summary for gateway fail_nightly governance using readiness+governance history."
    )
    parser.add_argument(
        "--readiness-runs-dir",
        type=Path,
        default=Path("runs") / "nightly-gateway-sla-readiness",
        help="Directory with readiness_summary.json history.",
    )
    parser.add_argument(
        "--governance-runs-dir",
        type=Path,
        default=Path("runs") / "nightly-gateway-sla-governance",
        help="Directory with governance_summary.json history.",
    )
    parser.add_argument(
        "--readiness-history-limit",
        type=int,
        default=60,
        help="Latest readiness summaries to inspect.",
    )
    parser.add_argument(
        "--governance-history-limit",
        type=int,
        default=60,
        help="Latest governance summaries to inspect.",
    )
    parser.add_argument(
        "--expected-readiness-window",
        type=int,
        default=14,
        help="Expected readiness window for valid readiness/governance summaries.",
    )
    parser.add_argument(
        "--expected-required-baseline-count",
        type=int,
        default=5,
        help="Expected required_baseline_count for valid readiness/governance summaries.",
    )
    parser.add_argument(
        "--expected-max-warn-ratio",
        type=float,
        default=0.20,
        help="Expected max_warn_ratio for valid readiness/governance summaries.",
    )
    parser.add_argument(
        "--required-ready-streak",
        type=int,
        default=3,
        help="Required ready streak for go decision.",
    )
    parser.add_argument(
        "--policy",
        choices=_POLICIES,
        default="report_only",
        help="Exit policy: report_only (default) or fail_if_not_go.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs") / "nightly-gateway-sla-progress",
        help="Run artifact base directory.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Output path for gateway_sla_fail_nightly_progress_v1 summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_fail_nightly_progress(
        readiness_runs_dir=args.readiness_runs_dir,
        governance_runs_dir=args.governance_runs_dir,
        readiness_history_limit=args.readiness_history_limit,
        governance_history_limit=args.governance_history_limit,
        expected_readiness_window=args.expected_readiness_window,
        expected_required_baseline_count=args.expected_required_baseline_count,
        expected_max_warn_ratio=args.expected_max_warn_ratio,
        required_ready_streak=args.required_ready_streak,
        policy=args.policy,
        runs_dir=args.runs_dir,
        summary_json=args.summary_json,
    )
    summary_payload = result["summary_payload"]
    print(f"[check_gateway_sla_fail_nightly_progress] run_dir: {result['run_dir']}")
    print(
        "[check_gateway_sla_fail_nightly_progress] "
        f"run_json: {result['run_payload']['paths']['run_json']}"
    )
    print(
        "[check_gateway_sla_fail_nightly_progress] "
        f"summary_json: {result['run_payload']['paths']['summary_json']}"
    )
    print(f"[check_gateway_sla_fail_nightly_progress] status: {summary_payload['status']}")
    print(
        "[check_gateway_sla_fail_nightly_progress] "
        f"decision_status: {summary_payload['decision_status']}"
    )
    print(f"[check_gateway_sla_fail_nightly_progress] exit_code: {summary_payload['exit_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
