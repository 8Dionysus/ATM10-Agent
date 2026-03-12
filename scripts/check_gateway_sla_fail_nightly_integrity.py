from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_SCHEMA_VERSION = "gateway_sla_fail_nightly_integrity_v1"
_POLICIES: tuple[str, ...] = ("report_only",)
_SOURCE_STATUS_PRESENT = "present"
_SOURCE_STATUS_MISSING = "missing"
_SOURCE_STATUS_INVALID = "invalid"

_EXPECTED_SCHEMAS: dict[str, str] = {
    "readiness": "gateway_sla_fail_nightly_readiness_v1",
    "governance": "gateway_sla_fail_nightly_governance_v1",
    "progress": "gateway_sla_fail_nightly_progress_v1",
    "transition": "gateway_sla_fail_nightly_transition_v1",
    "remediation": "gateway_sla_fail_nightly_remediation_v1",
    "manual_cadence": "gateway_sla_manual_cadence_brief_v1",
}
_REQUIRED_SOURCES: tuple[str, ...] = (
    "readiness",
    "governance",
    "progress",
    "transition",
    "remediation",
)
_SOURCE_ORDER: tuple[str, ...] = (
    "readiness",
    "governance",
    "progress",
    "transition",
    "remediation",
    "manual_cadence",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_run_dir(root: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-fail-integrity")
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


def _normalize_reason_codes(value: Any) -> list[str]:
    if isinstance(value, list):
        normalized = [str(item).strip() for item in value if str(item).strip()]
        return normalized
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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
        return _SOURCE_STATUS_INVALID, None, f"{source_name}: invalid JSON: {exc}"

    observed_schema = str(payload.get("schema_version", "")).strip()
    if observed_schema != expected_schema_version:
        return (
            _SOURCE_STATUS_INVALID,
            payload,
            f"{source_name}: schema_version={observed_schema!r} expected={expected_schema_version!r}",
        )

    summary_status = str(payload.get("status", "")).strip()
    if summary_status != "ok":
        return _SOURCE_STATUS_INVALID, payload, f"{source_name}: summary status must be 'ok'"

    return _SOURCE_STATUS_PRESENT, payload, None


def _source_details(
    *,
    path: Path,
    source_status: str,
    expected_schema_version: str,
    payload: Mapping[str, Any] | None,
    issue: str | None,
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
    if issue is not None:
        details["issue"] = issue
    return details


def _coerce_non_negative_int(value: Any, *, field_name: str, warnings: list[str]) -> int | None:
    if value is None:
        warnings.append(f"{field_name}: value is missing")
        return None
    if isinstance(value, bool):
        warnings.append(f"{field_name}: bool value is not allowed")
        return None
    try:
        coerced = int(value)
    except Exception:
        warnings.append(f"{field_name}: cannot parse {value!r}")
        return None
    if coerced < 0:
        warnings.append(f"{field_name}: negative value is not allowed")
        return None
    return coerced


def _read_history_summary(
    *,
    source_name: str,
    history_summary_path: Path | None,
    expected_schema_version: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if history_summary_path is None:
        return None, f"{source_name}: paths.history_summary_json is missing"
    if not history_summary_path.is_file():
        return None, f"{source_name}: history summary file not found: {history_summary_path}"
    try:
        payload = _read_json_object(history_summary_path)
    except Exception as exc:
        return None, f"{source_name}: invalid history JSON: {exc}"

    observed_schema = str(payload.get("schema_version", "")).strip()
    if observed_schema != expected_schema_version:
        return None, (
            f"{source_name}: history schema_version={observed_schema!r} "
            f"expected={expected_schema_version!r}"
        )
    return payload, None


def _validate_dual_write_artifacts(
    *,
    source_name: str,
    latest_path: Path,
    payload: Mapping[str, Any],
    expected_schema_version: str,
    warnings: list[str],
) -> dict[str, Any]:
    paths_payload = payload.get("paths")
    paths_payload = paths_payload if isinstance(paths_payload, Mapping) else {}

    run_dir_raw = paths_payload.get("run_dir")
    run_json_raw = paths_payload.get("run_json")
    summary_json_raw = paths_payload.get("summary_json")
    history_summary_raw = paths_payload.get("history_summary_json")

    run_dir = Path(str(run_dir_raw)) if isinstance(run_dir_raw, str) and str(run_dir_raw).strip() else None
    run_json_path = Path(str(run_json_raw)) if isinstance(run_json_raw, str) and str(run_json_raw).strip() else None
    summary_json_path = (
        Path(str(summary_json_raw)) if isinstance(summary_json_raw, str) and str(summary_json_raw).strip() else None
    )
    history_summary_path = (
        Path(str(history_summary_raw))
        if isinstance(history_summary_raw, str) and str(history_summary_raw).strip()
        else None
    )

    summary_json_matches_latest_alias = summary_json_path == latest_path
    run_json_exists = run_json_path is not None and run_json_path.is_file()
    history_summary_exists = history_summary_path is not None and history_summary_path.is_file()
    history_summary_differs_from_latest_alias = (
        history_summary_path is not None and history_summary_path != latest_path
    )
    run_json_in_run_dir = (
        run_dir is not None and run_json_path is not None and run_json_path.is_relative_to(run_dir)
    )
    history_summary_in_run_dir = (
        run_dir is not None
        and history_summary_path is not None
        and history_summary_path.is_relative_to(run_dir)
    )

    if not summary_json_matches_latest_alias:
        warnings.append(
            f"{source_name}: paths.summary_json does not match latest alias "
            f"({summary_json_path!s} != {latest_path!s})"
        )
    if not run_json_exists:
        warnings.append(f"{source_name}: paths.run_json is missing or unreadable")
    if not history_summary_exists:
        warnings.append(f"{source_name}: paths.history_summary_json is missing or unreadable")
    if run_json_path is not None and run_dir is not None and not run_json_in_run_dir:
        warnings.append(f"{source_name}: run_json is outside run_dir")
    if history_summary_path is not None and run_dir is not None and not history_summary_in_run_dir:
        warnings.append(f"{source_name}: history_summary_json is outside run_dir")
    if history_summary_path is not None and not history_summary_differs_from_latest_alias:
        warnings.append(f"{source_name}: history_summary_json must differ from latest alias")

    history_payload, history_issue = _read_history_summary(
        source_name=source_name,
        history_summary_path=history_summary_path,
        expected_schema_version=expected_schema_version,
    )
    history_summary_matches_contract = False
    if history_issue is not None:
        warnings.append(history_issue)
    else:
        history_schema = str(history_payload.get("schema_version", "")).strip() if history_payload else ""
        history_status = str(history_payload.get("status", "")).strip() if history_payload else ""
        history_summary_matches_contract = (
            history_schema == str(payload.get("schema_version", "")).strip()
            and history_status == str(payload.get("status", "")).strip()
        )
        if not history_summary_matches_contract:
            warnings.append(f"{source_name}: history summary schema/status does not match latest alias")

    dual_write_ok = all(
        (
            summary_json_matches_latest_alias,
            run_json_exists,
            history_summary_exists,
            run_json_in_run_dir,
            history_summary_in_run_dir,
            history_summary_matches_contract,
        )
    )
    anti_double_count_ok = all(
        (
            history_summary_exists,
            history_summary_in_run_dir,
            history_summary_differs_from_latest_alias,
            history_summary_matches_contract,
        )
    )

    return {
        "run_dir": str(run_dir) if run_dir is not None else None,
        "run_json": str(run_json_path) if run_json_path is not None else None,
        "summary_json": str(summary_json_path) if summary_json_path is not None else None,
        "history_summary_json": str(history_summary_path) if history_summary_path is not None else None,
        "run_json_exists": run_json_exists,
        "history_summary_exists": history_summary_exists,
        "summary_json_matches_latest_alias": summary_json_matches_latest_alias,
        "run_json_in_run_dir": run_json_in_run_dir,
        "history_summary_in_run_dir": history_summary_in_run_dir,
        "history_summary_differs_from_latest_alias": history_summary_differs_from_latest_alias,
        "history_summary_matches_contract": history_summary_matches_contract,
        "dual_write_ok": dual_write_ok,
        "anti_double_count_ok": anti_double_count_ok,
    }


def _validate_manual_cadence_guardrail(
    payload: Mapping[str, Any],
) -> tuple[str, dict[str, Any], list[str]]:
    attention_state = str(payload.get("attention_state", "")).strip()
    decision = payload.get("decision")
    decision = decision if isinstance(decision, Mapping) else {}
    accounted_dispatch_allowed = decision.get("accounted_dispatch_allowed")
    decision_status = str(decision.get("decision_status", "")).strip()
    next_accounted_dispatch_at_utc = decision.get("next_accounted_dispatch_at_utc")
    if isinstance(next_accounted_dispatch_at_utc, str):
        next_accounted_dispatch_at_utc = next_accounted_dispatch_at_utc.strip() or None
    elif next_accounted_dispatch_at_utc is not None:
        next_accounted_dispatch_at_utc = str(next_accounted_dispatch_at_utc)
    reason_codes = _normalize_reason_codes(decision.get("reason_codes"))

    details = {
        "attention_state": attention_state or None,
        "decision_status": decision_status or None,
        "accounted_dispatch_allowed": accounted_dispatch_allowed,
        "next_accounted_dispatch_at_utc": next_accounted_dispatch_at_utc,
        "reason_codes": reason_codes,
    }

    issues: list[str] = []
    if attention_state == "ready_for_accounted_run":
        if accounted_dispatch_allowed is not True:
            issues.append("ready_for_accounted_run requires accounted_dispatch_allowed=true")
        if decision_status != "allow_accounted_dispatch":
            issues.append("ready_for_accounted_run requires decision_status=allow_accounted_dispatch")
        if reason_codes:
            issues.append("ready_for_accounted_run expects empty decision.reason_codes")
    elif attention_state == "wait_for_utc_reset":
        if accounted_dispatch_allowed is not False:
            issues.append("wait_for_utc_reset requires accounted_dispatch_allowed=false")
        if decision_status != "block_accounted_dispatch":
            issues.append("wait_for_utc_reset requires decision_status=block_accounted_dispatch")
        if not next_accounted_dispatch_at_utc:
            issues.append("wait_for_utc_reset requires next_accounted_dispatch_at_utc")
        if "utc_day_quota_exhausted" not in reason_codes:
            issues.append("wait_for_utc_reset requires utc_day_quota_exhausted reason code")
    elif attention_state == "run_recovery_only":
        if accounted_dispatch_allowed is not False:
            issues.append("run_recovery_only requires accounted_dispatch_allowed=false")
        if decision_status != "allow_recovery_rerun":
            issues.append("run_recovery_only requires decision_status=allow_recovery_rerun")
    elif attention_state == "source_repair_required":
        if not decision_status:
            issues.append("source_repair_required requires non-empty decision_status")
    else:
        issues.append(f"unsupported attention_state={attention_state!r}")

    status = "ok" if not issues else "attention"
    return status, details, issues


def run_gateway_sla_fail_nightly_integrity(
    *,
    runs_dir: Path = Path("runs"),
    readiness_summary_json: Path | None = None,
    governance_summary_json: Path | None = None,
    progress_summary_json: Path | None = None,
    transition_summary_json: Path | None = None,
    remediation_summary_json: Path | None = None,
    manual_cadence_summary_json: Path | None = None,
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

    if readiness_summary_json is None:
        readiness_summary_json = Path(runs_dir) / "nightly-gateway-sla-readiness" / "readiness_summary.json"
    if governance_summary_json is None:
        governance_summary_json = Path(runs_dir) / "nightly-gateway-sla-governance" / "governance_summary.json"
    if progress_summary_json is None:
        progress_summary_json = Path(runs_dir) / "nightly-gateway-sla-progress" / "progress_summary.json"
    if transition_summary_json is None:
        transition_summary_json = Path(runs_dir) / "nightly-gateway-sla-transition" / "transition_summary.json"
    if remediation_summary_json is None:
        remediation_summary_json = Path(runs_dir) / "nightly-gateway-sla-remediation" / "remediation_summary.json"
    if manual_cadence_summary_json is None:
        manual_cadence_summary_json = (
            Path(runs_dir) / "nightly-gateway-sla-manual-cadence" / "cadence_brief.json"
        )

    run_root = Path(runs_dir) / "nightly-gateway-sla-integrity"
    run_dir = _create_run_dir(run_root, now=now)
    run_json_path = run_dir / "run.json"
    summary_out_path = summary_json if summary_json is not None else (run_root / "integrity_summary.json")
    history_summary_path = run_dir / "integrity_summary.json"

    source_paths: dict[str, Path] = {
        "readiness": readiness_summary_json,
        "governance": governance_summary_json,
        "progress": progress_summary_json,
        "transition": transition_summary_json,
        "remediation": remediation_summary_json,
        "manual_cadence": manual_cadence_summary_json,
    }

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.isoformat(),
        "mode": "gateway_sla_fail_nightly_integrity",
        "status": "started",
        "params": {
            "runs_dir": str(runs_dir),
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

    warnings: list[str] = []
    try:
        sources: dict[str, dict[str, Any]] = {}
        payloads: dict[str, dict[str, Any]] = {}
        for source_name in _SOURCE_ORDER:
            path = source_paths[source_name]
            source_status, payload, issue = _load_source_payload(
                source_name=source_name,
                path=path,
                expected_schema_version=_EXPECTED_SCHEMAS[source_name],
            )
            sources[source_name] = _source_details(
                path=path,
                source_status=source_status,
                expected_schema_version=_EXPECTED_SCHEMAS[source_name],
                payload=payload,
                issue=issue,
            )
            if isinstance(payload, Mapping) and source_status == _SOURCE_STATUS_PRESENT:
                payloads[source_name] = dict(payload)
            if issue is not None and (source_name in _REQUIRED_SOURCES or source_status == _SOURCE_STATUS_INVALID):
                warnings.append(issue)

        required_sources_ok = all(
            str(sources[source_name]["status"]) == _SOURCE_STATUS_PRESENT for source_name in _REQUIRED_SOURCES
        )

        artifact_checks: dict[str, dict[str, Any]] = {}
        for source_name in _REQUIRED_SOURCES:
            payload = payloads.get(source_name)
            if payload is None:
                continue
            checks = _validate_dual_write_artifacts(
                source_name=source_name,
                latest_path=source_paths[source_name],
                payload=payload,
                expected_schema_version=_EXPECTED_SCHEMAS[source_name],
                warnings=warnings,
            )
            artifact_checks[source_name] = checks
            sources[source_name]["artifact_checks"] = checks

        telemetry_warnings: list[str] = []
        governance_invalid = _coerce_non_negative_int(
            payloads.get("governance", {}).get("observed", {}).get("invalid_or_mismatched_count"),
            field_name="governance.observed.invalid_or_mismatched_count",
            warnings=telemetry_warnings,
        )
        progress_readiness_invalid = _coerce_non_negative_int(
            payloads.get("progress", {}).get("observed", {}).get("readiness", {}).get("invalid_or_mismatched_count"),
            field_name="progress.observed.readiness.invalid_or_mismatched_count",
            warnings=telemetry_warnings,
        )
        progress_governance_invalid = _coerce_non_negative_int(
            payloads.get("progress", {}).get("observed", {}).get("governance", {}).get("invalid_or_mismatched_count"),
            field_name="progress.observed.governance.invalid_or_mismatched_count",
            warnings=telemetry_warnings,
        )
        transition_aggregated_invalid = _coerce_non_negative_int(
            payloads.get("transition", {}).get("observed", {}).get("aggregated", {}).get("invalid_or_mismatched_count"),
            field_name="transition.observed.aggregated.invalid_or_mismatched_count",
            warnings=telemetry_warnings,
        )
        warnings.extend(telemetry_warnings)

        invalid_counts = {
            "governance": governance_invalid,
            "progress_readiness": progress_readiness_invalid,
            "progress_governance": progress_governance_invalid,
            "transition_aggregated": transition_aggregated_invalid,
        }
        telemetry_ok = required_sources_ok and all(value == 0 for value in invalid_counts.values())

        dual_write_ok = required_sources_ok and all(
            artifact_checks.get(source_name, {}).get("dual_write_ok") is True for source_name in _REQUIRED_SOURCES
        )
        anti_double_count_ok = required_sources_ok and all(
            artifact_checks.get(source_name, {}).get("anti_double_count_ok") is True
            for source_name in _REQUIRED_SOURCES
        )

        utc_guardrail_status = "not_available"
        utc_guardrail_ok: bool | None = None
        utc_guardrail: dict[str, Any] = {
            "attention_state": None,
            "decision_status": None,
            "accounted_dispatch_allowed": None,
            "next_accounted_dispatch_at_utc": None,
            "reason_codes": [],
        }
        manual_cadence_status = str(sources["manual_cadence"]["status"])
        if manual_cadence_status == _SOURCE_STATUS_PRESENT:
            status, details, issues = _validate_manual_cadence_guardrail(payloads["manual_cadence"])
            utc_guardrail = details
            utc_guardrail_status = status
            utc_guardrail_ok = status == "ok"
            for issue in issues:
                warnings.append(f"manual_cadence: {issue}")
        elif manual_cadence_status == _SOURCE_STATUS_MISSING:
            warnings.append("manual_cadence: UTC guardrail check not available yet")
        else:
            utc_guardrail_status = "attention"
            utc_guardrail_ok = False
            warnings.append("manual_cadence: UTC guardrail source is invalid")

        reason_codes: list[str] = []
        if not required_sources_ok:
            reason_codes.append("required_sources_unhealthy")
        if not telemetry_ok:
            reason_codes.append("telemetry_counters_nonzero")
        if not dual_write_ok:
            reason_codes.append("dual_write_invariant_broken")
        if not anti_double_count_ok:
            reason_codes.append("anti_double_count_invariant_broken")
        if utc_guardrail_status == "attention":
            reason_codes.append("utc_guardrail_inconsistent")

        integrity_status = "clean" if not reason_codes else "attention"

        summary_payload: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "status": "ok",
            "checked_at_utc": now.isoformat(),
            "policy": policy,
            "sources": sources,
            "observed": {
                "telemetry_ok": telemetry_ok,
                "dual_write_ok": dual_write_ok,
                "anti_double_count_ok": anti_double_count_ok,
                "utc_guardrail_status": utc_guardrail_status,
                "utc_guardrail_ok": utc_guardrail_ok,
                "utc_guardrail": utc_guardrail,
                "invalid_counts": invalid_counts,
            },
            "decision": {
                "integrity_status": integrity_status,
                "reason_codes": _dedupe_preserve(reason_codes),
            },
            "warnings": warnings,
            "error": None,
            "exit_code": 0,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
                "history_summary_json": str(history_summary_path),
            },
        }

        _write_json(history_summary_path, summary_payload)
        _write_json(summary_out_path, summary_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "integrity_status": integrity_status,
            "telemetry_ok": telemetry_ok,
            "dual_write_ok": dual_write_ok,
            "anti_double_count_ok": anti_double_count_ok,
            "utc_guardrail_status": utc_guardrail_status,
            "exit_code": 0,
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
            "exit_code": 0,
        }
    except Exception as exc:
        summary_payload = {
            "schema_version": _SCHEMA_VERSION,
            "status": "error",
            "checked_at_utc": now.isoformat(),
            "policy": policy,
            "sources": {},
            "observed": {
                "telemetry_ok": False,
                "dual_write_ok": False,
                "anti_double_count_ok": False,
                "utc_guardrail_status": "not_available",
                "utc_guardrail_ok": None,
                "utc_guardrail": {
                    "attention_state": None,
                    "decision_status": None,
                    "accounted_dispatch_allowed": None,
                    "next_accounted_dispatch_at_utc": None,
                    "reason_codes": [],
                },
                "invalid_counts": {
                    "governance": None,
                    "progress_readiness": None,
                    "progress_governance": None,
                    "transition_aggregated": None,
                },
            },
            "decision": {
                "integrity_status": "attention",
                "reason_codes": ["integrity_snapshot_failed"],
            },
            "warnings": warnings,
            "error": str(exc),
            "exit_code": 2,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
                "history_summary_json": str(history_summary_path),
            },
        }
        _write_json(history_summary_path, summary_payload)
        _write_json(summary_out_path, summary_payload)

        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        run_payload["result"] = {
            "integrity_status": "attention",
            "exit_code": 2,
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
            "exit_code": 2,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate G2 fail_nightly integrity invariants from latest nightly summaries."
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
        help="Exit policy for integrity snapshot (report_only only).",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Output path for gateway_sla_fail_nightly_integrity_v1 summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_fail_nightly_integrity(
        runs_dir=args.runs_dir,
        policy=args.policy,
        summary_json=args.summary_json,
    )
    summary_payload = result["summary_payload"]
    print(f"[check_gateway_sla_fail_nightly_integrity] run_dir: {result['run_dir']}")
    print(
        "[check_gateway_sla_fail_nightly_integrity] "
        f"summary_json: {result['run_payload']['paths']['summary_json']}"
    )
    print(
        "[check_gateway_sla_fail_nightly_integrity] "
        f"integrity_status: {summary_payload['decision']['integrity_status']}"
    )
    print(f"[check_gateway_sla_fail_nightly_integrity] exit_code: {summary_payload['exit_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
