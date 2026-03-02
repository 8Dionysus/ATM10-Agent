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

from src.agent_core.ops_policy import (
    MAX_WARN_RATIO,
    READINESS_WINDOW,
    REQUIRED_BASELINE_COUNT,
    REQUIRED_READY_STREAK,
    SWITCH_SURFACE,
)

_EPSILON = 1e-9
_POLICIES: tuple[str, ...] = ("report_only", "fail_if_not_allowed")
_READINESS_FILE_NAME = "readiness_summary.json"
_GOVERNANCE_FILE_NAME = "governance_summary.json"
_PROGRESS_FILE_NAME = "progress_summary.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-transition")
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


def _criteria_match_progress(
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

    paths = sorted(readiness_runs_dir.glob(f"**/{_READINESS_FILE_NAME}"), key=lambda item: str(item))
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
            rows.append(
                {
                    "checked_at_utc": checked_at.astimezone(timezone.utc).isoformat(),
                    "checked_at_epoch": checked_at.timestamp(),
                    "run_name": path.parent.name,
                    "readiness_summary_json": str(path),
                    "readiness_status": readiness_status,
                    "window_observed": int(criteria.get("window_observed", 0)),
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

    paths = sorted(governance_runs_dir.glob(f"**/{_GOVERNANCE_FILE_NAME}"), key=lambda item: str(item))
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
            observed = observed if isinstance(observed, Mapping) else {}
            rows.append(
                {
                    "checked_at_utc": checked_at.astimezone(timezone.utc).isoformat(),
                    "checked_at_epoch": checked_at.timestamp(),
                    "run_name": path.parent.name,
                    "governance_summary_json": str(path),
                    "decision_status": decision_status,
                    "latest_ready_streak": int(observed.get("latest_ready_streak", 0)),
                }
            )
        except Exception as exc:
            invalid_or_mismatched_count += 1
            warnings.append(f"{path}: skipped ({exc})")

    rows.sort(key=lambda item: (float(item["checked_at_epoch"]), str(item["run_name"])))
    return rows, invalid_or_mismatched_count, warnings


def _collect_progress_rows(
    *,
    progress_runs_dir: Path,
    history_limit: int,
    required_ready_streak: int,
    expected_readiness_window: int,
    expected_required_baseline_count: int,
    expected_max_warn_ratio: float,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    if not progress_runs_dir.exists():
        return [], 0, [f"progress_runs_dir does not exist: {progress_runs_dir}"]

    paths = sorted(progress_runs_dir.glob(f"**/{_PROGRESS_FILE_NAME}"), key=lambda item: str(item))
    if history_limit > 0 and len(paths) > history_limit:
        paths = paths[-history_limit:]

    warnings: list[str] = []
    invalid_or_mismatched_count = 0
    rows: list[dict[str, Any]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("progress summary root must be object")
            if payload.get("schema_version") != "gateway_sla_fail_nightly_progress_v1":
                raise ValueError("schema_version must be gateway_sla_fail_nightly_progress_v1")
            if payload.get("status") != "ok":
                raise ValueError("status must be ok")
            decision_status = str(payload.get("decision_status", "")).strip()
            if decision_status not in {"go", "hold"}:
                raise ValueError("decision_status must be go|hold")
            criteria = payload.get("criteria")
            if not isinstance(criteria, Mapping):
                raise ValueError("criteria must be object")
            if not _criteria_match_progress(
                criteria=criteria,
                required_ready_streak=required_ready_streak,
                expected_readiness_window=expected_readiness_window,
                expected_required_baseline_count=expected_required_baseline_count,
                expected_max_warn_ratio=expected_max_warn_ratio,
            ):
                raise ValueError("criteria mismatch against expected progress baseline")
            checked_at = _parse_iso_datetime(payload.get("checked_at_utc"))
            observed = payload.get("observed")
            observed = observed if isinstance(observed, Mapping) else {}
            observed_readiness = observed.get("readiness")
            observed_readiness = observed_readiness if isinstance(observed_readiness, Mapping) else {}
            rows.append(
                {
                    "checked_at_utc": checked_at.astimezone(timezone.utc).isoformat(),
                    "checked_at_epoch": checked_at.timestamp(),
                    "run_name": path.parent.name,
                    "progress_summary_json": str(path),
                    "decision_status": decision_status,
                    "latest_ready_streak": int(observed_readiness.get("latest_ready_streak", 0)),
                    "remaining_for_window": int(observed_readiness.get("remaining_for_window", 0)),
                    "remaining_for_streak": int(observed_readiness.get("remaining_for_streak", 0)),
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


def run_gateway_sla_fail_nightly_transition(
    *,
    readiness_runs_dir: Path = Path("runs") / "nightly-gateway-sla-readiness",
    governance_runs_dir: Path = Path("runs") / "nightly-gateway-sla-governance",
    progress_runs_dir: Path = Path("runs") / "nightly-gateway-sla-progress",
    readiness_history_limit: int = 60,
    governance_history_limit: int = 60,
    progress_history_limit: int = 60,
    expected_readiness_window: int = READINESS_WINDOW,
    expected_required_baseline_count: int = REQUIRED_BASELINE_COUNT,
    expected_max_warn_ratio: float = MAX_WARN_RATIO,
    required_ready_streak: int = REQUIRED_READY_STREAK,
    policy: str = "report_only",
    runs_dir: Path = Path("runs") / "nightly-gateway-sla-transition",
    summary_json: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if readiness_history_limit <= 0:
        raise ValueError("readiness_history_limit must be > 0.")
    if governance_history_limit <= 0:
        raise ValueError("governance_history_limit must be > 0.")
    if progress_history_limit <= 0:
        raise ValueError("progress_history_limit must be > 0.")
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
    summary_out_path = summary_json if summary_json is not None else (runs_dir / "transition_summary.json")

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "gateway_sla_fail_nightly_transition",
        "status": "started",
        "params": {
            "readiness_runs_dir": str(readiness_runs_dir),
            "governance_runs_dir": str(governance_runs_dir),
            "progress_runs_dir": str(progress_runs_dir),
            "readiness_history_limit": readiness_history_limit,
            "governance_history_limit": governance_history_limit,
            "progress_history_limit": progress_history_limit,
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
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        readiness_rows, readiness_invalid, readiness_warnings = _collect_readiness_rows(
            readiness_runs_dir=readiness_runs_dir,
            history_limit=readiness_history_limit,
            expected_readiness_window=expected_readiness_window,
            expected_required_baseline_count=expected_required_baseline_count,
            expected_max_warn_ratio=expected_max_warn_ratio,
        )
        governance_rows, governance_invalid, governance_warnings = _collect_governance_rows(
            governance_runs_dir=governance_runs_dir,
            history_limit=governance_history_limit,
            required_ready_streak=required_ready_streak,
            expected_readiness_window=expected_readiness_window,
            expected_required_baseline_count=expected_required_baseline_count,
            expected_max_warn_ratio=expected_max_warn_ratio,
        )
        progress_rows, progress_invalid, progress_warnings = _collect_progress_rows(
            progress_runs_dir=progress_runs_dir,
            history_limit=progress_history_limit,
            required_ready_streak=required_ready_streak,
            expected_readiness_window=expected_readiness_window,
            expected_required_baseline_count=expected_required_baseline_count,
            expected_max_warn_ratio=expected_max_warn_ratio,
        )
        warnings = readiness_warnings + governance_warnings + progress_warnings

        latest_readiness = readiness_rows[-1] if readiness_rows else None
        latest_governance = governance_rows[-1] if governance_rows else None
        latest_progress = progress_rows[-1] if progress_rows else None

        latest_readiness_status = None if latest_readiness is None else latest_readiness["readiness_status"]
        latest_governance_status = None if latest_governance is None else latest_governance["decision_status"]
        latest_progress_status = None if latest_progress is None else latest_progress["decision_status"]

        computed_ready_streak = _compute_ready_streak(readiness_rows) if readiness_rows else 0
        latest_ready_streak = computed_ready_streak
        if latest_progress is not None:
            latest_ready_streak = int(latest_progress.get("latest_ready_streak", latest_ready_streak))
        elif latest_governance is not None:
            latest_ready_streak = int(latest_governance.get("latest_ready_streak", latest_ready_streak))

        latest_window_observed = 0 if latest_readiness is None else int(latest_readiness.get("window_observed", 0))
        remaining_for_window = max(0, expected_readiness_window - latest_window_observed)
        remaining_for_streak = max(0, required_ready_streak - latest_ready_streak)
        if latest_progress is not None:
            remaining_for_window = int(latest_progress.get("remaining_for_window", remaining_for_window))
            remaining_for_streak = int(latest_progress.get("remaining_for_streak", remaining_for_streak))

        invalid_or_mismatched_count = readiness_invalid + governance_invalid + progress_invalid
        readiness_valid_count = len(readiness_rows)

        allow_switch = (
            latest_readiness_status == "ready"
            and latest_governance_status == "go"
            and latest_progress_status == "go"
            and readiness_valid_count >= expected_readiness_window
            and latest_ready_streak >= required_ready_streak
            and invalid_or_mismatched_count == 0
        )
        decision_status = "allow" if allow_switch else "hold"

        reason_codes: list[str] = []
        if latest_readiness is None:
            reason_codes.append("readiness_history_missing")
        elif latest_readiness_status != "ready":
            reason_codes.append("latest_readiness_not_ready")
        if latest_governance is None:
            reason_codes.append("governance_history_missing")
        elif latest_governance_status != "go":
            reason_codes.append("latest_governance_not_go")
        if latest_progress is None:
            reason_codes.append("progress_history_missing")
        elif latest_progress_status != "go":
            reason_codes.append("latest_progress_not_go")
        if readiness_valid_count < expected_readiness_window:
            reason_codes.append("readiness_valid_count_below_window")
        if latest_ready_streak < required_ready_streak:
            reason_codes.append("ready_streak_below_threshold")
        if invalid_or_mismatched_count > 0:
            reason_codes.append("invalid_or_mismatched_summaries_present")
        if allow_switch:
            reason_codes = []

        exit_code = 0
        if policy == "fail_if_not_allowed" and not allow_switch:
            exit_code = 2

        summary_payload: dict[str, Any] = {
            "schema_version": "gateway_sla_fail_nightly_transition_v1",
            "status": "ok",
            "decision_status": decision_status,
            "allow_switch": allow_switch,
            "checked_at_utc": _utc_now(),
            "policy": policy,
            "criteria": {
                "expected_readiness_window": expected_readiness_window,
                "expected_required_baseline_count": expected_required_baseline_count,
                "expected_max_warn_ratio": expected_max_warn_ratio,
                "required_ready_streak": required_ready_streak,
                "readiness_history_limit": readiness_history_limit,
                "governance_history_limit": governance_history_limit,
                "progress_history_limit": progress_history_limit,
            },
            "observed": {
                "readiness": {
                    "valid_count": readiness_valid_count,
                    "invalid_or_mismatched_count": readiness_invalid,
                    "latest_status": latest_readiness_status,
                    "latest_window_observed": latest_window_observed,
                    "latest_ready_streak": computed_ready_streak,
                },
                "governance": {
                    "valid_count": len(governance_rows),
                    "invalid_or_mismatched_count": governance_invalid,
                    "latest_decision_status": latest_governance_status,
                    "latest_ready_streak": 0
                    if latest_governance is None
                    else int(latest_governance.get("latest_ready_streak", 0)),
                },
                "progress": {
                    "valid_count": len(progress_rows),
                    "invalid_or_mismatched_count": progress_invalid,
                    "latest_decision_status": latest_progress_status,
                    "latest_ready_streak": 0
                    if latest_progress is None
                    else int(latest_progress.get("latest_ready_streak", 0)),
                    "remaining_for_window": remaining_for_window,
                    "remaining_for_streak": remaining_for_streak,
                },
                "aggregated": {
                    "invalid_or_mismatched_count": invalid_or_mismatched_count,
                    "latest_ready_streak": latest_ready_streak,
                },
            },
            "latest": {
                "readiness": latest_readiness,
                "governance": latest_governance,
                "progress": latest_progress,
            },
            "recommendation": {
                "target_critical_policy": "fail_nightly" if allow_switch else "signal_only",
                "switch_surface": SWITCH_SURFACE,
                "reason_codes": reason_codes,
            },
            "warnings": warnings,
            "error": None,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
            },
            "exit_code": exit_code,
        }
        _write_json(summary_out_path, summary_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "decision_status": decision_status,
            "allow_switch": allow_switch,
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
    except (FileNotFoundError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        summary_payload = {
            "schema_version": "gateway_sla_fail_nightly_transition_v1",
            "status": "error",
            "decision_status": "hold",
            "allow_switch": False,
            "checked_at_utc": _utc_now(),
            "policy": policy,
            "criteria": {
                "expected_readiness_window": expected_readiness_window,
                "expected_required_baseline_count": expected_required_baseline_count,
                "expected_max_warn_ratio": expected_max_warn_ratio,
                "required_ready_streak": required_ready_streak,
                "readiness_history_limit": readiness_history_limit,
                "governance_history_limit": governance_history_limit,
                "progress_history_limit": progress_history_limit,
            },
            "observed": {
                "readiness": {
                    "valid_count": 0,
                    "invalid_or_mismatched_count": 0,
                    "latest_status": None,
                    "latest_window_observed": 0,
                    "latest_ready_streak": 0,
                },
                "governance": {
                    "valid_count": 0,
                    "invalid_or_mismatched_count": 0,
                    "latest_decision_status": None,
                    "latest_ready_streak": 0,
                },
                "progress": {
                    "valid_count": 0,
                    "invalid_or_mismatched_count": 0,
                    "latest_decision_status": None,
                    "latest_ready_streak": 0,
                    "remaining_for_window": expected_readiness_window,
                    "remaining_for_streak": required_ready_streak,
                },
                "aggregated": {
                    "invalid_or_mismatched_count": 0,
                    "latest_ready_streak": 0,
                },
            },
            "latest": {
                "readiness": None,
                "governance": None,
                "progress": None,
            },
            "recommendation": {
                "target_critical_policy": "signal_only",
                "switch_surface": SWITCH_SURFACE,
                "reason_codes": ["transition_evaluation_failed"],
            },
            "warnings": [],
            "error": str(exc),
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
            },
            "exit_code": 2,
        }
        _write_json(summary_out_path, summary_payload)
        run_payload["status"] = "error"
        run_payload["error_code"] = "gateway_sla_fail_transition_failed"
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
        description="Evaluate transition eligibility to run gateway SLA trend in fail_nightly mode."
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
        "--progress-runs-dir",
        type=Path,
        default=Path("runs") / "nightly-gateway-sla-progress",
        help="Directory with progress_summary.json history.",
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
        "--progress-history-limit",
        type=int,
        default=60,
        help="Latest progress summaries to inspect.",
    )
    parser.add_argument(
        "--expected-readiness-window",
        type=int,
        default=READINESS_WINDOW,
        help="Expected readiness window for valid readiness/governance/progress summaries.",
    )
    parser.add_argument(
        "--expected-required-baseline-count",
        type=int,
        default=REQUIRED_BASELINE_COUNT,
        help="Expected required_baseline_count for valid readiness/governance/progress summaries.",
    )
    parser.add_argument(
        "--expected-max-warn-ratio",
        type=float,
        default=MAX_WARN_RATIO,
        help="Expected max_warn_ratio for valid readiness/governance/progress summaries.",
    )
    parser.add_argument(
        "--required-ready-streak",
        type=int,
        default=REQUIRED_READY_STREAK,
        help="Required trailing ready streak for transition allow_switch.",
    )
    parser.add_argument(
        "--policy",
        choices=_POLICIES,
        default="report_only",
        help="Exit policy: report_only (default) or fail_if_not_allowed.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs") / "nightly-gateway-sla-transition",
        help="Run artifact base directory.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Output path for gateway_sla_fail_nightly_transition_v1 summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_fail_nightly_transition(
        readiness_runs_dir=args.readiness_runs_dir,
        governance_runs_dir=args.governance_runs_dir,
        progress_runs_dir=args.progress_runs_dir,
        readiness_history_limit=args.readiness_history_limit,
        governance_history_limit=args.governance_history_limit,
        progress_history_limit=args.progress_history_limit,
        expected_readiness_window=args.expected_readiness_window,
        expected_required_baseline_count=args.expected_required_baseline_count,
        expected_max_warn_ratio=args.expected_max_warn_ratio,
        required_ready_streak=args.required_ready_streak,
        policy=args.policy,
        runs_dir=args.runs_dir,
        summary_json=args.summary_json,
    )
    summary_payload = result["summary_payload"]
    print(f"[check_gateway_sla_fail_nightly_transition] run_dir: {result['run_dir']}")
    print(
        "[check_gateway_sla_fail_nightly_transition] "
        f"run_json: {result['run_payload']['paths']['run_json']}"
    )
    print(
        "[check_gateway_sla_fail_nightly_transition] "
        f"summary_json: {result['run_payload']['paths']['summary_json']}"
    )
    print(f"[check_gateway_sla_fail_nightly_transition] status: {summary_payload['status']}")
    print(
        "[check_gateway_sla_fail_nightly_transition] "
        f"allow_switch: {summary_payload['allow_switch']}"
    )
    print(f"[check_gateway_sla_fail_nightly_transition] exit_code: {summary_payload['exit_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
