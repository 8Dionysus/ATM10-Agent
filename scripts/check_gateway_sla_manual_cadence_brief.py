from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

_SCHEMA_VERSION = "gateway_sla_manual_cadence_brief_v1"
_POLICIES: tuple[str, ...] = ("report_only", "fail_if_attention_required")
_SOURCE_STATUS_PRESENT = "present"
_SOURCE_STATUS_MISSING = "missing"
_SOURCE_STATUS_INVALID = "invalid"

_EXPECTED_SCHEMAS: dict[str, str] = {
    "manual_runner": "gateway_sla_manual_nightly_runner_v1",
    "manual_cycle": "gateway_sla_manual_cycle_summary_v1",
    "readiness": "gateway_sla_fail_nightly_readiness_v1",
    "governance": "gateway_sla_fail_nightly_governance_v1",
    "progress": "gateway_sla_fail_nightly_progress_v1",
    "transition": "gateway_sla_fail_nightly_transition_v1",
}
_REQUIRED_SOURCES: tuple[str, ...] = ("manual_cycle", "progress")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_run_dir(root: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-manual-cadence-brief")
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


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be object")
    return payload


def _parse_iso_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty string")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _load_source_payload(
    *,
    source_name: str,
    path: Path,
    expected_schema_version: str,
) -> tuple[str, dict[str, Any] | None, str | None]:
    if not path.is_file():
        return _SOURCE_STATUS_MISSING, None, f"{source_name}: source file not found: {path}"

    try:
        payload = _read_json_object(path)
    except Exception as exc:
        raise RuntimeError(f"{source_name}: invalid JSON: {exc}") from exc

    schema_version = str(payload.get("schema_version", "")).strip()
    if schema_version != expected_schema_version:
        return (
            _SOURCE_STATUS_INVALID,
            payload,
            f"{source_name}: schema_version={schema_version!r} expected={expected_schema_version!r}",
        )
    if str(payload.get("status", "")).strip() != "ok":
        return (
            _SOURCE_STATUS_INVALID,
            payload,
            f"{source_name}: summary status must be 'ok'",
        )
    return _SOURCE_STATUS_PRESENT, payload, None


def _source_details(
    *,
    path: Path,
    source_status: str,
    expected_schema_version: str,
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "path": str(path),
        "status": source_status,
        "expected_schema_version": expected_schema_version,
    }
    if isinstance(payload, Mapping):
        details["observed_schema_version"] = payload.get("schema_version")
        details["summary_status"] = payload.get("status")
        checked_at = payload.get("checked_at_utc")
        if checked_at is not None:
            details["checked_at_utc"] = checked_at
    return details


def _coerce_non_negative_int(value: Any, *, field_name: str, warnings: list[str]) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        warnings.append(f"{field_name}: bool value is not allowed; fallback to 0")
        return 0
    try:
        coerced = int(value)
    except Exception:
        warnings.append(f"{field_name}: cannot parse {value!r}; fallback to 0")
        return 0
    return max(0, coerced)


def _extract_decision(payload: Mapping[str, Any]) -> dict[str, Any]:
    decision = payload.get("decision")
    if not isinstance(decision, Mapping):
        raise ValueError("manual_cycle.decision must be object")

    if "accounted_dispatch_allowed" not in decision:
        raise ValueError("manual_cycle.decision.accounted_dispatch_allowed is required")
    decision_status = str(decision.get("decision_status", "")).strip()
    if not decision_status:
        raise ValueError("manual_cycle.decision.decision_status is required")

    next_accounted_dispatch_at = decision.get("next_accounted_dispatch_at_utc")
    if next_accounted_dispatch_at is not None:
        next_accounted_dispatch_at = str(next_accounted_dispatch_at).strip() or None

    reason_codes_raw = decision.get("reason_codes")
    if reason_codes_raw is None:
        reason_codes: list[str] = []
    elif isinstance(reason_codes_raw, list):
        reason_codes = [str(item).strip() for item in reason_codes_raw if str(item).strip()]
    else:
        raise ValueError("manual_cycle.decision.reason_codes must be array when provided")

    return {
        "accounted_dispatch_allowed": bool(decision.get("accounted_dispatch_allowed")),
        "decision_status": decision_status,
        "next_accounted_dispatch_at_utc": next_accounted_dispatch_at,
        "reason_codes": reason_codes,
    }


def run_gateway_sla_manual_cadence_brief(
    *,
    runs_dir: Path = Path("runs"),
    manual_runner_summary_json: Path | None = None,
    manual_cycle_summary_json: Path | None = None,
    readiness_summary_json: Path | None = None,
    governance_summary_json: Path | None = None,
    progress_summary_json: Path | None = None,
    transition_summary_json: Path | None = None,
    policy: str = "report_only",
    summary_json: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if policy not in _POLICIES:
        raise ValueError(f"policy must be one of: {', '.join(_POLICIES)}")
    if now is None:
        now = datetime.now(timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    run_root = Path(runs_dir) / "nightly-gateway-sla-manual-cadence"
    run_dir = _create_run_dir(run_root, now=now)
    run_json_path = run_dir / "run.json"

    if manual_runner_summary_json is None:
        manual_runner_summary_json = Path(runs_dir) / "nightly-gateway-sla-manual-runner" / "manual_nightly_summary.json"
    if manual_cycle_summary_json is None:
        manual_cycle_summary_json = Path(runs_dir) / "nightly-gateway-sla-manual-cycle" / "manual_cycle_summary.json"
    if readiness_summary_json is None:
        readiness_summary_json = Path(runs_dir) / "nightly-gateway-sla-readiness" / "readiness_summary.json"
    if governance_summary_json is None:
        governance_summary_json = Path(runs_dir) / "nightly-gateway-sla-governance" / "governance_summary.json"
    if progress_summary_json is None:
        progress_summary_json = Path(runs_dir) / "nightly-gateway-sla-progress" / "progress_summary.json"
    if transition_summary_json is None:
        transition_summary_json = Path(runs_dir) / "nightly-gateway-sla-transition" / "transition_summary.json"
    if summary_json is None:
        summary_json = run_root / "cadence_brief.json"

    source_inputs: list[tuple[str, Path]] = [
        ("manual_runner", manual_runner_summary_json),
        ("manual_cycle", manual_cycle_summary_json),
        ("readiness", readiness_summary_json),
        ("governance", governance_summary_json),
        ("progress", progress_summary_json),
        ("transition", transition_summary_json),
    ]

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.isoformat(),
        "mode": "gateway_sla_manual_cadence_brief",
        "status": "started",
        "params": {
            "runs_dir": str(runs_dir),
            "policy": policy,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_json),
            "manual_runner_summary_json": str(manual_runner_summary_json),
            "manual_cycle_summary_json": str(manual_cycle_summary_json),
            "readiness_summary_json": str(readiness_summary_json),
            "governance_summary_json": str(governance_summary_json),
            "progress_summary_json": str(progress_summary_json),
            "transition_summary_json": str(transition_summary_json),
        },
    }
    _write_json(run_json_path, run_payload)

    warnings: list[str] = []
    try:
        source_payloads: dict[str, dict[str, Any] | None] = {}
        sources: dict[str, dict[str, Any]] = {}
        for source_name, source_path in source_inputs:
            source_status, source_payload, source_issue = _load_source_payload(
                source_name=source_name,
                path=source_path,
                expected_schema_version=_EXPECTED_SCHEMAS[source_name],
            )
            source_payloads[source_name] = source_payload
            sources[source_name] = _source_details(
                path=source_path,
                source_status=source_status,
                expected_schema_version=_EXPECTED_SCHEMAS[source_name],
                payload=source_payload,
            )
            if source_issue is not None:
                warnings.append(source_issue)

        required_broken = any(sources[name]["status"] != _SOURCE_STATUS_PRESENT for name in _REQUIRED_SOURCES)
        decision: dict[str, Any]
        if sources["manual_cycle"]["status"] == _SOURCE_STATUS_PRESENT and source_payloads["manual_cycle"] is not None:
            decision = _extract_decision(source_payloads["manual_cycle"])
        else:
            decision = {
                "accounted_dispatch_allowed": False,
                "decision_status": "unknown",
                "next_accounted_dispatch_at_utc": None,
                "reason_codes": ["manual_cycle_unavailable"],
            }

        progress_payload = source_payloads["progress"] if isinstance(source_payloads["progress"], Mapping) else {}
        progress_observed = progress_payload.get("observed")
        progress_observed = progress_observed if isinstance(progress_observed, Mapping) else {}
        progress_readiness = progress_observed.get("readiness")
        progress_readiness = progress_readiness if isinstance(progress_readiness, Mapping) else {}

        remaining_for_window = _coerce_non_negative_int(
            progress_readiness.get("remaining_for_window"),
            field_name="progress.observed.readiness.remaining_for_window",
            warnings=warnings,
        )
        remaining_for_streak = _coerce_non_negative_int(
            progress_readiness.get("remaining_for_streak"),
            field_name="progress.observed.readiness.remaining_for_streak",
            warnings=warnings,
        )

        readiness_payload = source_payloads["readiness"] if isinstance(source_payloads["readiness"], Mapping) else {}
        governance_payload = source_payloads["governance"] if isinstance(source_payloads["governance"], Mapping) else {}
        transition_payload = source_payloads["transition"] if isinstance(source_payloads["transition"], Mapping) else {}

        observed = {
            "remaining_for_window": remaining_for_window,
            "remaining_for_streak": remaining_for_streak,
            "readiness_status": readiness_payload.get("readiness_status"),
            "governance_decision_status": governance_payload.get("decision_status"),
            "transition_allow_switch": transition_payload.get("allow_switch"),
        }

        decision_status = str(decision.get("decision_status", "")).strip()
        if required_broken:
            attention_state = "source_repair_required"
        elif decision_status == "block_accounted_dispatch":
            attention_state = "wait_for_utc_reset"
        elif decision_status == "allow_recovery_rerun":
            attention_state = "run_recovery_only"
        elif decision_status == "allow_accounted_dispatch":
            attention_state = "ready_for_accounted_run"
        else:
            attention_state = "unknown"

        now_utc = now.astimezone(timezone.utc)
        next_dispatch_raw = decision.get("next_accounted_dispatch_at_utc")
        if isinstance(next_dispatch_raw, str) and next_dispatch_raw.strip():
            next_dispatch_at = _parse_iso_datetime(next_dispatch_raw.strip())
        else:
            next_dispatch_at = now_utc

        if remaining_for_window > 0:
            earliest_window_ready_at = next_dispatch_at + timedelta(days=remaining_for_window - 1)
        else:
            earliest_window_ready_at = now_utc
        if remaining_for_streak > 0:
            earliest_streak_ready_at = next_dispatch_at + timedelta(days=remaining_for_streak - 1)
        else:
            earliest_streak_ready_at = now_utc
        earliest_go_candidate_at = max(earliest_window_ready_at, earliest_streak_ready_at)

        if policy == "fail_if_attention_required" and attention_state in {
            "source_repair_required",
            "wait_for_utc_reset",
            "run_recovery_only",
            "unknown",
        }:
            exit_code = 2
        else:
            exit_code = 0

        summary_payload: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "status": "ok",
            "checked_at_utc": _utc_now(),
            "policy": policy,
            "sources": sources,
            "observed": observed,
            "decision": decision,
            "attention_state": attention_state,
            "forecast": {
                "min_accounted_runs_to_window": remaining_for_window,
                "min_accounted_runs_to_streak": remaining_for_streak,
                "next_accounted_dispatch_at_utc": next_dispatch_at.isoformat(),
                "earliest_window_ready_at_utc": earliest_window_ready_at.isoformat(),
                "earliest_streak_ready_at_utc": earliest_streak_ready_at.isoformat(),
                "earliest_go_candidate_at_utc": earliest_go_candidate_at.isoformat(),
            },
            "warnings": warnings,
            "error": None,
            "exit_code": exit_code,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_json),
            },
        }
        _write_json(summary_json, summary_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "attention_state": attention_state,
            "decision_status": decision_status,
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
    except Exception as exc:
        summary_payload = {
            "schema_version": _SCHEMA_VERSION,
            "status": "error",
            "checked_at_utc": _utc_now(),
            "policy": policy,
            "sources": {},
            "observed": {
                "remaining_for_window": 0,
                "remaining_for_streak": 0,
                "readiness_status": None,
                "governance_decision_status": None,
                "transition_allow_switch": None,
            },
            "decision": {
                "accounted_dispatch_allowed": False,
                "decision_status": "error",
                "next_accounted_dispatch_at_utc": None,
                "reason_codes": ["manual_cadence_brief_failed"],
            },
            "attention_state": "unknown",
            "forecast": {
                "min_accounted_runs_to_window": 0,
                "min_accounted_runs_to_streak": 0,
                "next_accounted_dispatch_at_utc": now.isoformat(),
                "earliest_window_ready_at_utc": now.isoformat(),
                "earliest_streak_ready_at_utc": now.isoformat(),
                "earliest_go_candidate_at_utc": now.isoformat(),
            },
            "warnings": warnings,
            "error": str(exc),
            "exit_code": 2,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_json),
            },
        }
        _write_json(summary_json, summary_payload)
        run_payload["status"] = "error"
        run_payload["error_code"] = "gateway_sla_manual_cadence_brief_failed"
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
    parser = argparse.ArgumentParser(description="Build local daily cadence brief for G2 manual nightly operator loop.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Base runs directory.")
    parser.add_argument("--manual-runner-summary-json", type=Path, default=None, help="Optional manual runner summary path.")
    parser.add_argument("--manual-cycle-summary-json", type=Path, default=None, help="Optional manual cycle summary path.")
    parser.add_argument("--readiness-summary-json", type=Path, default=None, help="Optional readiness summary path.")
    parser.add_argument("--governance-summary-json", type=Path, default=None, help="Optional governance summary path.")
    parser.add_argument("--progress-summary-json", type=Path, default=None, help="Optional progress summary path.")
    parser.add_argument("--transition-summary-json", type=Path, default=None, help="Optional transition summary path.")
    parser.add_argument(
        "--policy",
        choices=_POLICIES,
        default="report_only",
        help="Exit policy: report_only (default) or fail_if_attention_required.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Output path for gateway_sla_manual_cadence_brief_v1 summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_manual_cadence_brief(
        runs_dir=args.runs_dir,
        manual_runner_summary_json=args.manual_runner_summary_json,
        manual_cycle_summary_json=args.manual_cycle_summary_json,
        readiness_summary_json=args.readiness_summary_json,
        governance_summary_json=args.governance_summary_json,
        progress_summary_json=args.progress_summary_json,
        transition_summary_json=args.transition_summary_json,
        policy=args.policy,
        summary_json=args.summary_json,
    )
    summary_payload = result["summary_payload"]
    print(f"[check_gateway_sla_manual_cadence_brief] run_dir: {result['run_dir']}")
    print(
        "[check_gateway_sla_manual_cadence_brief] "
        f"summary_json: {result['run_payload']['paths']['summary_json']}"
    )
    print(
        "[check_gateway_sla_manual_cadence_brief] "
        f"attention_state: {summary_payload['attention_state']}"
    )
    print(
        "[check_gateway_sla_manual_cadence_brief] "
        f"decision_status: {summary_payload['decision']['decision_status']}"
    )
    print(f"[check_gateway_sla_manual_cadence_brief] exit_code: {summary_payload['exit_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
