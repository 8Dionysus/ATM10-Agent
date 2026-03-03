from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_gateway_sla import run_gateway_sla_check
from scripts.check_gateway_sla_fail_nightly_governance import run_gateway_sla_fail_nightly_governance
from scripts.check_gateway_sla_fail_nightly_progress import run_gateway_sla_fail_nightly_progress
from scripts.check_gateway_sla_fail_nightly_readiness import run_gateway_sla_fail_nightly_readiness
from scripts.check_gateway_sla_fail_nightly_transition import run_gateway_sla_fail_nightly_transition
from scripts.check_gateway_sla_manual_cycle_summary import run_gateway_sla_manual_cycle_summary
from scripts.gateway_sla_trend_snapshot import run_gateway_sla_trend_snapshot
from scripts.gateway_v1_http_smoke import run_gateway_v1_http_smoke

_SCHEMA_VERSION = "gateway_sla_manual_nightly_runner_v1"
_PREFLIGHT_SCHEMA = "gateway_sla_manual_preflight_v1"
_POLICIES: tuple[str, ...] = ("report_only", "fail_if_blocked")
_SOURCE_STATUS_PRESENT = "present"
_SOURCE_STATUS_MISSING = "missing"
_SOURCE_STATUS_INVALID = "invalid"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_run_dir(root: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-manual-nightly-runner")
    run_dir = root / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    suffix = 1
    while True:
        candidate = root / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def _parse_iso_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty string")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be object")
    return payload


def _source_state(path: Path, expected_schema: str) -> tuple[str, dict[str, Any] | None]:
    if not path.is_file():
        return _SOURCE_STATUS_MISSING, None
    try:
        payload = _read_json_object(path)
    except Exception:
        return _SOURCE_STATUS_INVALID, None
    if str(payload.get("schema_version", "")).strip() != expected_schema:
        return _SOURCE_STATUS_INVALID, None
    if str(payload.get("status", "")).strip() != "ok":
        return _SOURCE_STATUS_INVALID, payload
    return _SOURCE_STATUS_PRESENT, payload


def _runner_history_run_json_paths(runs_dir: Path) -> list[Path]:
    root = runs_dir / "nightly-gateway-sla-manual-runner"
    if not root.exists():
        return []
    return sorted(
        [
            path
            for path in root.glob("*-gateway-sla-manual-nightly-runner*/run.json")
            if path.is_file()
        ]
    )


def _scan_accounted_today_runs(
    *,
    runs_dir: Path,
    utc_date: datetime.date,
) -> tuple[int, list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    for run_json_path in _runner_history_run_json_paths(runs_dir):
        try:
            payload = _read_json_object(run_json_path)
            timestamp_utc = _parse_iso_datetime(payload.get("timestamp_utc"))
            result = payload.get("result")
            result = result if isinstance(result, Mapping) else {}
            progression_credit = bool(result.get("progression_credit", False))
            execution_mode = str(result.get("execution_mode", "")).strip()
            if not progression_credit:
                continue
            if timestamp_utc.date() != utc_date:
                continue
            rows.append(
                {
                    "run_json": str(run_json_path),
                    "run_dir": str(run_json_path.parent),
                    "execution_mode": execution_mode,
                    "progression_credit": progression_credit,
                    "timestamp_utc": timestamp_utc.isoformat(),
                    "timestamp_epoch": timestamp_utc.timestamp(),
                }
            )
        except Exception as exc:
            warnings.append(f"skipped invalid runner history file {run_json_path}: {exc}")

    rows.sort(key=lambda item: float(item["timestamp_epoch"]))
    return len(rows), rows, warnings


def _should_allow_recovery(
    *,
    runs_dir: Path,
) -> tuple[bool, list[str], dict[str, dict[str, Any]]]:
    readiness_path = runs_dir / "nightly-gateway-sla-readiness" / "readiness_summary.json"
    governance_path = runs_dir / "nightly-gateway-sla-governance" / "governance_summary.json"
    progress_path = runs_dir / "nightly-gateway-sla-progress" / "progress_summary.json"
    transition_path = runs_dir / "nightly-gateway-sla-transition" / "transition_summary.json"

    readiness_state, _ = _source_state(readiness_path, "gateway_sla_fail_nightly_readiness_v1")
    governance_state, _ = _source_state(governance_path, "gateway_sla_fail_nightly_governance_v1")
    progress_state, _ = _source_state(progress_path, "gateway_sla_fail_nightly_progress_v1")
    transition_state, _ = _source_state(transition_path, "gateway_sla_fail_nightly_transition_v1")

    states = {
        "readiness": {"path": str(readiness_path), "status": readiness_state},
        "governance": {"path": str(governance_path), "status": governance_state},
        "progress": {"path": str(progress_path), "status": progress_state},
        "transition": {"path": str(transition_path), "status": transition_state},
    }

    reason_codes: list[str] = []
    if readiness_state != _SOURCE_STATUS_PRESENT:
        reason_codes.append("recovery_readiness_not_ok")
    if governance_state != _SOURCE_STATUS_PRESENT:
        reason_codes.append("recovery_governance_not_ok")
    if progress_state != _SOURCE_STATUS_PRESENT:
        reason_codes.append("recovery_progress_not_ok")
    if transition_state == _SOURCE_STATUS_PRESENT:
        reason_codes.append("recovery_transition_already_present")
    else:
        reason_codes.append("recovery_transition_missing_or_invalid")

    recovery_allowed = (
        readiness_state == _SOURCE_STATUS_PRESENT
        and governance_state == _SOURCE_STATUS_PRESENT
        and progress_state == _SOURCE_STATUS_PRESENT
        and transition_state in {_SOURCE_STATUS_MISSING, _SOURCE_STATUS_INVALID}
    )
    return recovery_allowed, reason_codes, states


def _write_local_preflight_summary(
    *,
    runs_dir: Path,
    policy: str,
    max_runs_per_utc_day: int,
    allow_recovery_rerun: bool,
    preflight_summary_json: Path,
    now: datetime,
) -> dict[str, Any]:
    preflight_root = runs_dir / "nightly-gateway-sla-preflight"
    preflight_run_dir = _create_run_dir(preflight_root, now=now)
    preflight_run_json = preflight_run_dir / "run.json"

    warnings: list[str] = []
    today_utc = now.date()
    today_count, today_rows, scan_warnings = _scan_accounted_today_runs(runs_dir=runs_dir, utc_date=today_utc)
    warnings.extend(scan_warnings)

    accounted_dispatch_allowed = today_count < max_runs_per_utc_day
    recovery_rerun_allowed = False
    recovery_states: dict[str, dict[str, Any]] = {}
    decision_status = "allow_accounted_dispatch"
    reason_codes: list[str] = []

    if not accounted_dispatch_allowed:
        decision_status = "block_accounted_dispatch"
        reason_codes = ["utc_day_quota_exhausted"]
        if allow_recovery_rerun:
            recovery_rerun_allowed, recovery_reason_codes, recovery_states = _should_allow_recovery(runs_dir=runs_dir)
            if recovery_rerun_allowed:
                decision_status = "allow_recovery_rerun"
                reason_codes = ["utc_day_quota_exhausted", "recovery_transition_missing_or_invalid"]
            else:
                reason_codes.extend(recovery_reason_codes)

    next_accounted_dispatch_at: str | None = None
    if not accounted_dispatch_allowed:
        next_day = today_utc + timedelta(days=1)
        next_accounted_dispatch_at = datetime(
            year=next_day.year,
            month=next_day.month,
            day=next_day.day,
            tzinfo=timezone.utc,
        ).isoformat()

    latest_dispatch_run = today_rows[-1] if today_rows else None
    preflight_payload: dict[str, Any] = {
        "schema_version": _PREFLIGHT_SCHEMA,
        "status": "ok",
        "checked_at_utc": _utc_now(),
        "utc_date": today_utc.isoformat(),
        "policy": policy,
        "inputs": {
            "preflight_source": "local_artifact",
            "max_runs_per_utc_day": max_runs_per_utc_day,
            "allow_recovery_rerun": allow_recovery_rerun,
            "runner_history_glob": str(
                runs_dir / "nightly-gateway-sla-manual-runner" / "*-gateway-sla-manual-nightly-runner*" / "run.json"
            ),
        },
        "observed": {
            "workflow_runs_observed": len(today_rows),
            "today_dispatch_count": today_count,
            "latest_dispatch_run": latest_dispatch_run,
            "recovery_sources": recovery_states if recovery_states else None,
        },
        "decision": {
            "accounted_dispatch_allowed": accounted_dispatch_allowed,
            "recovery_rerun_allowed": recovery_rerun_allowed,
            "decision_status": decision_status,
            "next_accounted_dispatch_at_utc": next_accounted_dispatch_at,
            "reason_codes": reason_codes,
        },
        "warnings": warnings,
        "error": None,
        "exit_code": 0,
        "paths": {
            "run_dir": str(preflight_run_dir),
            "run_json": str(preflight_run_json),
            "summary_json": str(preflight_summary_json),
        },
    }

    _write_json(preflight_summary_json, preflight_payload)
    _write_json(
        preflight_run_json,
        {
            "timestamp_utc": now.isoformat(),
            "mode": "gateway_sla_manual_preflight_local_artifact",
            "status": "ok",
            "params": {
                "policy": policy,
                "max_runs_per_utc_day": max_runs_per_utc_day,
                "allow_recovery_rerun": allow_recovery_rerun,
            },
            "paths": preflight_payload["paths"],
            "result": {
                "decision_status": decision_status,
                "accounted_dispatch_allowed": accounted_dispatch_allowed,
                "recovery_rerun_allowed": recovery_rerun_allowed,
                "today_dispatch_count": today_count,
                "warnings_count": len(warnings),
                "exit_code": 0,
            },
        },
    )
    return preflight_payload


StepRunner = Callable[[], dict[str, Any]]


def _extract_step_status(result: Mapping[str, Any]) -> tuple[str, int]:
    summary_payload = result.get("summary_payload")
    snapshot_payload = result.get("snapshot_payload")
    if isinstance(summary_payload, Mapping):
        status = str(summary_payload.get("status", "")).strip() or ("ok" if bool(result.get("ok")) else "error")
        exit_code = int(result.get("exit_code", summary_payload.get("exit_code", 0 if status == "ok" else 2)))
        return status, exit_code
    if isinstance(snapshot_payload, Mapping):
        status = str(snapshot_payload.get("status", "")).strip() or ("ok" if bool(result.get("ok")) else "error")
        exit_code = int(result.get("exit_code", snapshot_payload.get("exit_code", 0 if status == "ok" else 2)))
        return status, exit_code
    status = "ok" if bool(result.get("ok", False)) else "error"
    exit_code = int(result.get("exit_code", 0 if status == "ok" else 2))
    return status, exit_code


def _extract_step_paths(result: Mapping[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    run_payload = result.get("run_payload")
    if isinstance(run_payload, Mapping):
        run_paths = run_payload.get("paths")
        if isinstance(run_paths, Mapping):
            paths.update({str(k): v for k, v in run_paths.items()})
    summary_payload = result.get("summary_payload")
    if isinstance(summary_payload, Mapping):
        summary_paths = summary_payload.get("paths")
        if isinstance(summary_paths, Mapping):
            paths.update({str(k): v for k, v in summary_paths.items()})
    snapshot_payload = result.get("snapshot_payload")
    if isinstance(snapshot_payload, Mapping):
        snapshot_paths = snapshot_payload.get("paths")
        if isinstance(snapshot_paths, Mapping):
            paths.update({str(k): v for k, v in snapshot_paths.items()})
    run_dir = result.get("run_dir")
    if run_dir is not None:
        paths.setdefault("run_dir", str(run_dir))
    return paths


def _execute_step(
    *,
    step_id: str,
    runner: StepRunner,
    steps: list[dict[str, Any]],
    fail_fast: bool,
) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
    started_at = _utc_now()
    try:
        result = runner()
        status, exit_code = _extract_step_status(result)
        step_row = {
            "id": step_id,
            "status": status,
            "exit_code": exit_code,
            "started_at_utc": started_at,
            "finished_at_utc": _utc_now(),
            "paths": _extract_step_paths(result),
            "error": None,
        }
        steps.append(step_row)
        if fail_fast and status != "ok":
            return False, step_row, result
        return True, step_row, result
    except Exception as exc:
        step_row = {
            "id": step_id,
            "status": "error",
            "exit_code": 2,
            "started_at_utc": started_at,
            "finished_at_utc": _utc_now(),
            "paths": {},
            "error": str(exc),
        }
        steps.append(step_row)
        return False, step_row, None


def run_gateway_sla_manual_nightly(
    *,
    runs_dir: Path = Path("runs"),
    policy: str = "report_only",
    max_runs_per_utc_day: int = 1,
    allow_recovery_rerun: bool = True,
    summary_json: Path | None = None,
    manual_cycle_summary_json: Path | None = None,
    preflight_summary_json: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if policy not in _POLICIES:
        raise ValueError(f"policy must be one of: {', '.join(_POLICIES)}")
    if max_runs_per_utc_day <= 0:
        raise ValueError("max_runs_per_utc_day must be > 0")

    if now is None:
        now = datetime.now(timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    runner_root = runs_dir / "nightly-gateway-sla-manual-runner"
    run_dir = _create_run_dir(runner_root, now=now)
    run_json_path = run_dir / "run.json"

    if summary_json is None:
        summary_json = runner_root / "manual_nightly_summary.json"
    if manual_cycle_summary_json is None:
        manual_cycle_summary_json = runs_dir / "nightly-gateway-sla-manual-cycle" / "manual_cycle_summary.json"
    if preflight_summary_json is None:
        preflight_summary_json = runs_dir / "nightly-gateway-sla-preflight" / "local_preflight_summary.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.isoformat(),
        "mode": "gateway_sla_manual_nightly_runner",
        "status": "started",
        "params": {
            "runs_dir": str(runs_dir),
            "policy": policy,
            "max_runs_per_utc_day": max_runs_per_utc_day,
            "allow_recovery_rerun": allow_recovery_rerun,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_json),
            "preflight_summary_json": str(preflight_summary_json),
            "manual_cycle_summary_json": str(manual_cycle_summary_json),
        },
    }
    _write_json(run_json_path, run_payload)

    warnings: list[str] = []
    steps: list[dict[str, Any]] = []
    error_text: str | None = None
    execution_mode = "blocked"
    progression_credit = False
    exit_code = 0

    try:
        preflight_payload = _write_local_preflight_summary(
            runs_dir=runs_dir,
            policy=policy,
            max_runs_per_utc_day=max_runs_per_utc_day,
            allow_recovery_rerun=allow_recovery_rerun,
            preflight_summary_json=preflight_summary_json,
            now=now,
        )
        warnings.extend(list(preflight_payload.get("warnings") or []))
        decision = preflight_payload.get("decision")
        decision = decision if isinstance(decision, Mapping) else {}
        accounted_allowed = bool(decision.get("accounted_dispatch_allowed"))
        recovery_allowed = bool(decision.get("recovery_rerun_allowed"))
        decision_status = str(decision.get("decision_status", "")).strip()

        if accounted_allowed:
            execution_mode = "accounted"
            progression_credit = True
            transition_allow_switch = False
            accounted_steps: list[tuple[str, StepRunner]] = [
                (
                    "gateway_http_core",
                    lambda: run_gateway_v1_http_smoke(
                        scenario="core",
                        runs_dir=runs_dir / "nightly-gateway-http-core",
                        summary_json=runs_dir / "nightly-gateway-http-core" / "gateway_http_smoke_summary.json",
                    ),
                ),
                (
                    "gateway_sla_signal",
                    lambda: run_gateway_sla_check(
                        http_summary_json=runs_dir / "nightly-gateway-http-core" / "gateway_http_smoke_summary.json",
                        summary_json=runs_dir / "nightly-gateway-sla-history" / "gateway_sla_summary.json",
                        profile="conservative",
                        policy="signal_only",
                        runs_dir=runs_dir / "nightly-gateway-sla-history",
                    ),
                ),
                (
                    "gateway_sla_trend_signal",
                    lambda: run_gateway_sla_trend_snapshot(
                        sla_runs_dir=runs_dir / "nightly-gateway-sla-history",
                        history_limit=30,
                        baseline_window=5,
                        critical_policy="signal_only",
                        runs_dir=runs_dir / "nightly-gateway-sla-trend-history",
                    ),
                ),
                (
                    "readiness",
                    lambda: run_gateway_sla_fail_nightly_readiness(
                        trend_runs_dir=runs_dir / "nightly-gateway-sla-trend-history",
                        history_limit=30,
                        readiness_window=14,
                        required_baseline_count=5,
                        max_warn_ratio=0.20,
                        policy="report_only",
                        runs_dir=runs_dir / "nightly-gateway-sla-readiness",
                        summary_json=runs_dir / "nightly-gateway-sla-readiness" / "readiness_summary.json",
                    ),
                ),
                (
                    "governance",
                    lambda: run_gateway_sla_fail_nightly_governance(
                        readiness_runs_dir=runs_dir / "nightly-gateway-sla-readiness",
                        history_limit=60,
                        required_ready_streak=3,
                        expected_readiness_window=14,
                        expected_required_baseline_count=5,
                        expected_max_warn_ratio=0.20,
                        policy="report_only",
                        runs_dir=runs_dir / "nightly-gateway-sla-governance",
                        summary_json=runs_dir / "nightly-gateway-sla-governance" / "governance_summary.json",
                    ),
                ),
                (
                    "progress",
                    lambda: run_gateway_sla_fail_nightly_progress(
                        readiness_runs_dir=runs_dir / "nightly-gateway-sla-readiness",
                        governance_runs_dir=runs_dir / "nightly-gateway-sla-governance",
                        readiness_history_limit=60,
                        governance_history_limit=60,
                        expected_readiness_window=14,
                        expected_required_baseline_count=5,
                        expected_max_warn_ratio=0.20,
                        required_ready_streak=3,
                        policy="report_only",
                        runs_dir=runs_dir / "nightly-gateway-sla-progress",
                        summary_json=runs_dir / "nightly-gateway-sla-progress" / "progress_summary.json",
                    ),
                ),
                (
                    "transition",
                    lambda: run_gateway_sla_fail_nightly_transition(
                        readiness_runs_dir=runs_dir / "nightly-gateway-sla-readiness",
                        governance_runs_dir=runs_dir / "nightly-gateway-sla-governance",
                        progress_runs_dir=runs_dir / "nightly-gateway-sla-progress",
                        readiness_history_limit=60,
                        governance_history_limit=60,
                        progress_history_limit=60,
                        expected_readiness_window=14,
                        expected_required_baseline_count=5,
                        expected_max_warn_ratio=0.20,
                        required_ready_streak=3,
                        policy="report_only",
                        runs_dir=runs_dir / "nightly-gateway-sla-transition",
                        summary_json=runs_dir / "nightly-gateway-sla-transition" / "transition_summary.json",
                    ),
                ),
            ]

            for step_id, step_runner in accounted_steps:
                ok, failed_step, step_result = _execute_step(
                    step_id=step_id,
                    runner=step_runner,
                    steps=steps,
                    fail_fast=True,
                )
                if step_id == "transition" and isinstance(step_result, Mapping):
                    transition_summary = step_result.get("summary_payload")
                    if isinstance(transition_summary, Mapping):
                        transition_allow_switch = bool(transition_summary.get("allow_switch"))
                if not ok:
                    execution_mode = "error"
                    progression_credit = False
                    error_text = f"failed step: {failed_step['id']}" if failed_step else "failed step"
                    break

            if execution_mode != "error":
                if transition_allow_switch:
                    ok, failed_step, _ = _execute_step(
                        step_id="gateway_sla_trend_fail_nightly",
                        runner=lambda: run_gateway_sla_trend_snapshot(
                            sla_runs_dir=runs_dir / "nightly-gateway-sla-history",
                            history_limit=30,
                            baseline_window=5,
                            critical_policy="fail_nightly",
                            runs_dir=runs_dir / "nightly-gateway-sla-trend-history",
                        ),
                        steps=steps,
                        fail_fast=True,
                    )
                    if not ok:
                        execution_mode = "error"
                        error_text = f"failed step: {failed_step['id']}" if failed_step else "failed step"
                        progression_credit = False

        elif recovery_allowed:
            execution_mode = "recovery"
            progression_credit = False
            recovery_steps: list[tuple[str, StepRunner]] = [
                (
                    "transition",
                    lambda: run_gateway_sla_fail_nightly_transition(
                        readiness_runs_dir=runs_dir / "nightly-gateway-sla-readiness",
                        governance_runs_dir=runs_dir / "nightly-gateway-sla-governance",
                        progress_runs_dir=runs_dir / "nightly-gateway-sla-progress",
                        readiness_history_limit=60,
                        governance_history_limit=60,
                        progress_history_limit=60,
                        expected_readiness_window=14,
                        expected_required_baseline_count=5,
                        expected_max_warn_ratio=0.20,
                        required_ready_streak=3,
                        policy="report_only",
                        runs_dir=runs_dir / "nightly-gateway-sla-transition",
                        summary_json=runs_dir / "nightly-gateway-sla-transition" / "transition_summary.json",
                    ),
                ),
            ]
            for step_id, step_runner in recovery_steps:
                ok, failed_step, _ = _execute_step(
                    step_id=step_id,
                    runner=step_runner,
                    steps=steps,
                    fail_fast=True,
                )
                if not ok:
                    execution_mode = "error"
                    error_text = f"failed step: {failed_step['id']}" if failed_step else "failed step"
                    break
        else:
            execution_mode = "blocked"
            progression_credit = False
            if policy == "fail_if_blocked":
                exit_code = 2

        if execution_mode != "error":
            _, cycle_step, _ = _execute_step(
                step_id="manual_cycle_summary",
                runner=lambda: run_gateway_sla_manual_cycle_summary(
                    runs_dir=runs_dir,
                    preflight_summary_json=preflight_summary_json,
                    policy="report_only",
                    summary_json=manual_cycle_summary_json,
                ),
                steps=steps,
                fail_fast=True,
            )
            if cycle_step is not None and cycle_step["status"] != "ok":
                execution_mode = "error"
                error_text = f"failed step: {cycle_step['id']}"
            elif execution_mode == "blocked" and policy == "fail_if_blocked":
                exit_code = 2
            elif execution_mode in {"accounted", "recovery", "blocked"}:
                exit_code = 0

        if execution_mode == "error":
            exit_code = 2

        status = "error" if execution_mode == "error" else "ok"
        summary_payload: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "status": status,
            "checked_at_utc": _utc_now(),
            "policy": policy,
            "execution_mode": execution_mode,
            "guardrail": {
                "preflight_summary_json": str(preflight_summary_json),
                "decision_status": decision_status,
                "accounted_dispatch_allowed": accounted_allowed,
                "recovery_rerun_allowed": recovery_allowed,
                "max_runs_per_utc_day": max_runs_per_utc_day,
            },
            "steps": steps,
            "decision": {
                "accounted_dispatch_allowed": bool(decision.get("accounted_dispatch_allowed")),
                "recovery_rerun_allowed": bool(decision.get("recovery_rerun_allowed")),
                "decision_status": str(decision.get("decision_status", "")).strip(),
                "next_accounted_dispatch_at_utc": decision.get("next_accounted_dispatch_at_utc"),
                "reason_codes": list(decision.get("reason_codes") or []),
            },
            "warnings": warnings,
            "error": error_text,
            "exit_code": exit_code,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_json),
                "preflight_summary_json": str(preflight_summary_json),
                "manual_cycle_summary_json": str(manual_cycle_summary_json),
            },
        }
        _write_json(summary_json, summary_payload)
        run_payload["status"] = status
        run_payload["result"] = {
            "execution_mode": execution_mode,
            "progression_credit": progression_credit,
            "decision_status": summary_payload["decision"]["decision_status"],
            "exit_code": exit_code,
            "steps_count": len(steps),
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
    except Exception as exc:
        summary_payload = {
            "schema_version": _SCHEMA_VERSION,
            "status": "error",
            "checked_at_utc": _utc_now(),
            "policy": policy,
            "execution_mode": "error",
            "guardrail": {
                "preflight_summary_json": str(preflight_summary_json),
                "decision_status": "error",
                "accounted_dispatch_allowed": False,
                "recovery_rerun_allowed": False,
                "max_runs_per_utc_day": max_runs_per_utc_day,
            },
            "steps": steps,
            "decision": {
                "accounted_dispatch_allowed": False,
                "recovery_rerun_allowed": False,
                "decision_status": "error",
                "next_accounted_dispatch_at_utc": None,
                "reason_codes": ["manual_nightly_runner_failed"],
            },
            "warnings": warnings,
            "error": str(exc),
            "exit_code": 2,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_json),
                "preflight_summary_json": str(preflight_summary_json),
                "manual_cycle_summary_json": str(manual_cycle_summary_json),
            },
        }
        _write_json(summary_json, summary_payload)
        run_payload["status"] = "error"
        run_payload["error_code"] = "gateway_sla_manual_nightly_runner_failed"
        run_payload["error"] = str(exc)
        run_payload["result"] = {
            "execution_mode": "error",
            "progression_credit": False,
            "exit_code": 2,
            "steps_count": len(steps),
            "warnings_count": len(warnings),
        }
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
        description="Run local manual nightly wrapper for gateway SLA chain with UTC guardrail and recovery mode."
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base runs directory.",
    )
    parser.add_argument(
        "--policy",
        choices=_POLICIES,
        default="report_only",
        help="Exit policy when accounted dispatch is blocked.",
    )
    parser.add_argument(
        "--max-runs-per-utc-day",
        type=int,
        default=1,
        help="Maximum accounted runs per UTC day.",
    )
    parser.add_argument(
        "--allow-recovery-rerun",
        type=str,
        choices=("true", "false"),
        default="true",
        help="Allow recovery rerun when UTC quota is exhausted and transition summary is missing/invalid.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Output path for gateway_sla_manual_nightly_runner_v1 summary.",
    )
    parser.add_argument(
        "--manual-cycle-summary-json",
        type=Path,
        default=None,
        help="Output path for gateway_sla_manual_cycle_summary_v1 summary.",
    )
    parser.add_argument(
        "--preflight-summary-json",
        type=Path,
        default=None,
        help="Output path for local gateway_sla_manual_preflight_v1 summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_manual_nightly(
        runs_dir=args.runs_dir,
        policy=args.policy,
        max_runs_per_utc_day=args.max_runs_per_utc_day,
        allow_recovery_rerun=args.allow_recovery_rerun == "true",
        summary_json=args.summary_json,
        manual_cycle_summary_json=args.manual_cycle_summary_json,
        preflight_summary_json=args.preflight_summary_json,
    )
    summary_payload = result["summary_payload"]
    print(f"[run_gateway_sla_manual_nightly] run_dir: {result['run_dir']}")
    print(
        "[run_gateway_sla_manual_nightly] "
        f"summary_json: {result['run_payload']['paths']['summary_json']}"
    )
    print(
        "[run_gateway_sla_manual_nightly] "
        f"execution_mode: {summary_payload['execution_mode']}"
    )
    print(
        "[run_gateway_sla_manual_nightly] "
        f"decision_status: {summary_payload['decision']['decision_status']}"
    )
    print(f"[run_gateway_sla_manual_nightly] exit_code: {summary_payload['exit_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
