from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_SCHEMA_VERSION = "gateway_sla_fail_nightly_remediation_v1"
_SOURCE_STATUS_PRESENT = "present"
_SOURCE_STATUS_MISSING = "missing"
_SOURCE_STATUS_INVALID = "invalid"
_POLICIES: tuple[str, ...] = ("report_only", "fail_if_remediation_required")
_MAX_CANDIDATE_ITEMS = 5

_EXPECTED_SCHEMAS: dict[str, str] = {
    "readiness": "gateway_sla_fail_nightly_readiness_v1",
    "governance": "gateway_sla_fail_nightly_governance_v1",
    "progress": "gateway_sla_fail_nightly_progress_v1",
    "transition": "gateway_sla_fail_nightly_transition_v1",
    "manual_cadence": "gateway_sla_manual_cadence_brief_v1",
}
_REQUIRED_SOURCES: tuple[str, ...] = ("readiness", "governance", "progress", "transition")
_SOURCE_ORDER: tuple[str, ...] = (
    "readiness",
    "governance",
    "progress",
    "transition",
    "manual_cadence",
)
_CANDIDATE_ORDER: tuple[str, ...] = (
    "telemetry_integrity",
    "regression_investigation",
    "window_accumulation",
    "ready_streak_stabilization",
    "manual_guardrail",
)
_WINDOW_REASON_CODES = {
    "insufficient_window",
    "insufficient_window_observed",
    "insufficient_baseline_count_in_window",
    "readiness_valid_count_below_window",
}
_STREAK_REASON_CODES = {
    "ready_streak_below_threshold",
    "latest_governance_hold",
}
_REGRESSION_REASON_CODES = {
    "critical_regression_present",
    "warn_ratio_above_threshold",
    "latest_not_ready",
}
_MANUAL_GUARDRAIL_REASON_CODES = {
    "utc_day_quota_exhausted",
    "manual_cycle_unavailable",
}
_TELEMETRY_REASON_CODES = {
    "invalid_or_error_snapshots_present",
    "readiness_history_missing",
    "governance_history_missing",
    "progress_history_missing",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_run_dir(root: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-fail-remediation")
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
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


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


def _coerce_non_negative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        coerced = int(value)
    except Exception:
        return None
    return max(0, coerced)


def _extract_reason_codes_by_source(payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    by_source: dict[str, list[str]] = {}
    for source_name in _SOURCE_ORDER:
        payload = payloads.get(source_name)
        if not isinstance(payload, Mapping):
            continue
        if source_name == "manual_cadence":
            reason_codes = _normalize_reason_codes(payload.get("decision", {}).get("reason_codes"))
        else:
            reason_codes = _normalize_reason_codes(payload.get("recommendation", {}).get("reason_codes"))
        by_source[source_name] = reason_codes
    return by_source


def _build_observed(payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    readiness_payload = payloads.get("readiness", {})
    governance_payload = payloads.get("governance", {})
    progress_payload = payloads.get("progress", {})
    transition_payload = payloads.get("transition", {})
    cadence_payload = payloads.get("manual_cadence", {})

    progress_observed = progress_payload.get("observed")
    progress_observed = progress_observed if isinstance(progress_observed, Mapping) else {}
    progress_readiness = progress_observed.get("readiness")
    progress_readiness = progress_readiness if isinstance(progress_readiness, Mapping) else {}

    observed: dict[str, Any] = {
        "readiness_status": readiness_payload.get("readiness_status"),
        "governance_decision_status": governance_payload.get("decision_status"),
        "progress_decision_status": progress_payload.get("decision_status"),
        "transition_allow_switch": transition_payload.get("allow_switch"),
        "remaining_for_window": _coerce_non_negative_int(progress_readiness.get("remaining_for_window")),
        "remaining_for_streak": _coerce_non_negative_int(progress_readiness.get("remaining_for_streak")),
    }
    attention_state = cadence_payload.get("attention_state")
    if isinstance(attention_state, str) and attention_state.strip():
        observed["attention_state"] = attention_state.strip()
    return observed


def _collect_union_reason_codes(reason_codes_by_source: Mapping[str, list[str]]) -> list[str]:
    combined: list[str] = []
    for source_name in _SOURCE_ORDER:
        combined.extend(reason_codes_by_source.get(source_name, []))
    return _dedupe_preserve(combined)


def _matches_telemetry_reason(reason_code: str) -> bool:
    return (
        reason_code in _TELEMETRY_REASON_CODES
        or reason_code.startswith("invalid_or_mismatched_")
    )


def _matches_regression_reason(reason_code: str) -> bool:
    return (
        reason_code in _REGRESSION_REASON_CODES
        or reason_code.startswith("latest_") and reason_code.endswith("_not_ready")
        or reason_code.startswith("latest_") and reason_code.endswith("_not_go")
    )


def _bucket_summary(
    bucket_id: str,
    *,
    source_refs: list[str],
    sources: Mapping[str, Mapping[str, Any]],
    observed: Mapping[str, Any],
) -> str:
    if bucket_id == "telemetry_integrity":
        broken_parts = [
            f"{source_name}={sources[source_name]['status']}"
            for source_name in source_refs
            if str(sources.get(source_name, {}).get("status", "")) != _SOURCE_STATUS_PRESENT
        ]
        if broken_parts:
            joined = ", ".join(broken_parts)
            return f"Repair G2 telemetry sources before further triage: {joined}."
        return "Investigate invalid or mismatched G2 telemetry signals in the latest published summaries."

    if bucket_id == "regression_investigation":
        return "Investigate latest strict-nightly regression signals before tightening or trusting the current baseline."

    if bucket_id == "window_accumulation":
        remaining = observed.get("remaining_for_window")
        if isinstance(remaining, int) and remaining > 0:
            return f"Accumulate {remaining} more accounted nightly run(s) to satisfy the readiness window."
        return "Continue accumulating clean readiness history until the window and baseline-count criteria are satisfied."

    if bucket_id == "ready_streak_stabilization":
        remaining = observed.get("remaining_for_streak")
        if isinstance(remaining, int) and remaining > 0:
            return f"Stabilize {remaining} more ready run(s) to clear the ready-streak threshold and related hold states."
        return "Stabilize the ready streak so governance and progress summaries can clear their hold state."

    attention_state = observed.get("attention_state")
    if attention_state == "wait_for_utc_reset":
        return "Wait until the next UTC dispatch window before running another accounted manual cycle."
    if attention_state == "run_recovery_only":
        return "Run only the recovery manual cycle path; do not count the rerun toward progression credit."
    if attention_state == "source_repair_required":
        return "Repair manual cadence inputs before using the manual loop for remediation decisions."
    return "Clear the manual cadence guardrail before scheduling another manual remediation cycle."


def _build_candidate_items(
    *,
    sources: Mapping[str, Mapping[str, Any]],
    reason_codes_by_source: Mapping[str, list[str]],
    observed: Mapping[str, Any],
) -> list[dict[str, Any]]:
    required_broken = [
        source_name
        for source_name in _REQUIRED_SOURCES
        if str(sources.get(source_name, {}).get("status", "")) != _SOURCE_STATUS_PRESENT
    ]

    bucket_refs: dict[str, set[str]] = {bucket_id: set() for bucket_id in _CANDIDATE_ORDER}
    if required_broken:
        bucket_refs["telemetry_integrity"].update(required_broken)

    optional_invalid = [
        source_name
        for source_name in ("manual_cadence",)
        if str(sources.get(source_name, {}).get("status", "")) == _SOURCE_STATUS_INVALID
    ]
    if optional_invalid:
        bucket_refs["telemetry_integrity"].update(optional_invalid)

    for source_name, reason_codes in reason_codes_by_source.items():
        for reason_code in reason_codes:
            if _matches_telemetry_reason(reason_code):
                bucket_refs["telemetry_integrity"].add(source_name)
            if reason_code in _WINDOW_REASON_CODES:
                bucket_refs["window_accumulation"].add(source_name)
            if reason_code in _STREAK_REASON_CODES:
                bucket_refs["ready_streak_stabilization"].add(source_name)
            if _matches_regression_reason(reason_code):
                bucket_refs["regression_investigation"].add(source_name)
            if reason_code in _MANUAL_GUARDRAIL_REASON_CODES:
                bucket_refs["manual_guardrail"].add(source_name)

    remaining_for_window = observed.get("remaining_for_window")
    if isinstance(remaining_for_window, int) and remaining_for_window > 0:
        bucket_refs["window_accumulation"].add("progress")

    remaining_for_streak = observed.get("remaining_for_streak")
    if isinstance(remaining_for_streak, int) and remaining_for_streak > 0:
        bucket_refs["ready_streak_stabilization"].update({"progress", "governance"})

    if observed.get("governance_decision_status") == "hold":
        bucket_refs["ready_streak_stabilization"].add("governance")
    if observed.get("progress_decision_status") == "hold":
        bucket_refs["ready_streak_stabilization"].add("progress")

    attention_state = observed.get("attention_state")
    if isinstance(attention_state, str) and attention_state != "ready_for_accounted_run":
        bucket_refs["manual_guardrail"].add("manual_cadence")

    priorities = {
        "telemetry_integrity": "high",
        "regression_investigation": "high",
        "window_accumulation": "medium",
        "ready_streak_stabilization": "medium",
        "manual_guardrail": "high",
    }

    items: list[dict[str, Any]] = []
    for bucket_id in _CANDIDATE_ORDER:
        source_refs = sorted(bucket_refs[bucket_id])
        if not source_refs:
            continue
        items.append(
            {
                "id": bucket_id,
                "priority": priorities[bucket_id],
                "summary": _bucket_summary(bucket_id, source_refs=source_refs, sources=sources, observed=observed),
                "source_refs": source_refs,
            }
        )
        if len(items) >= _MAX_CANDIDATE_ITEMS:
            break
    return items


def run_gateway_sla_fail_nightly_remediation(
    *,
    runs_dir: Path = Path("runs"),
    readiness_summary_json: Path | None = None,
    governance_summary_json: Path | None = None,
    progress_summary_json: Path | None = None,
    transition_summary_json: Path | None = None,
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
    if manual_cadence_summary_json is None:
        manual_cadence_summary_json = (
            Path(runs_dir) / "nightly-gateway-sla-manual-cadence" / "cadence_brief.json"
        )

    run_root = Path(runs_dir) / "nightly-gateway-sla-remediation"
    run_dir = _create_run_dir(run_root, now=now)
    run_json_path = run_dir / "run.json"
    summary_out_path = summary_json if summary_json is not None else (run_root / "remediation_summary.json")
    history_summary_path = run_dir / "remediation_summary.json"

    source_paths: dict[str, Path] = {
        "readiness": readiness_summary_json,
        "governance": governance_summary_json,
        "progress": progress_summary_json,
        "transition": transition_summary_json,
        "manual_cadence": manual_cadence_summary_json,
    }

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.isoformat(),
        "mode": "gateway_sla_fail_nightly_remediation",
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
            "readiness_summary_json": str(readiness_summary_json),
            "governance_summary_json": str(governance_summary_json),
            "progress_summary_json": str(progress_summary_json),
            "transition_summary_json": str(transition_summary_json),
            "manual_cadence_summary_json": str(manual_cadence_summary_json),
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
            if issue is not None and (
                source_name in _REQUIRED_SOURCES or source_status == _SOURCE_STATUS_INVALID
            ):
                warnings.append(issue)

        observed = _build_observed(payloads)
        reason_codes_by_source = _extract_reason_codes_by_source(payloads)
        reason_codes = _collect_union_reason_codes(reason_codes_by_source)
        candidate_items = _build_candidate_items(
            sources=sources,
            reason_codes_by_source=reason_codes_by_source,
            observed=observed,
        )
        required_broken = any(
            str(sources.get(source_name, {}).get("status", "")) != _SOURCE_STATUS_PRESENT
            for source_name in _REQUIRED_SOURCES
        )

        exit_code = 0
        if policy == "fail_if_remediation_required" and (required_broken or candidate_items):
            exit_code = 2

        summary_payload: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "status": "ok",
            "checked_at_utc": now.isoformat(),
            "policy": policy,
            "sources": sources,
            "observed": observed,
            "reason_codes": reason_codes,
            "candidate_items": candidate_items,
            "warnings": warnings,
            "error": None,
            "exit_code": exit_code,
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
            "required_sources_broken": required_broken,
            "candidate_item_ids": [item["id"] for item in candidate_items],
            "exit_code": exit_code,
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
            "exit_code": exit_code,
        }
    except Exception as exc:
        summary_payload = {
            "schema_version": _SCHEMA_VERSION,
            "status": "error",
            "checked_at_utc": now.isoformat(),
            "policy": policy,
            "sources": {},
            "observed": {},
            "reason_codes": ["remediation_snapshot_failed"],
            "candidate_items": [],
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
        run_payload["error_code"] = "remediation_snapshot_failed"
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
        description="Build a remediation snapshot from latest G2 strict-nightly telemetry summaries."
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Root runs directory.")
    parser.add_argument(
        "--readiness-summary-json",
        type=Path,
        default=None,
        help="Optional override for readiness_summary.json.",
    )
    parser.add_argument(
        "--governance-summary-json",
        type=Path,
        default=None,
        help="Optional override for governance_summary.json.",
    )
    parser.add_argument(
        "--progress-summary-json",
        type=Path,
        default=None,
        help="Optional override for progress_summary.json.",
    )
    parser.add_argument(
        "--transition-summary-json",
        type=Path,
        default=None,
        help="Optional override for transition_summary.json.",
    )
    parser.add_argument(
        "--manual-cadence-summary-json",
        type=Path,
        default=None,
        help="Optional override for cadence_brief.json.",
    )
    parser.add_argument(
        "--policy",
        choices=_POLICIES,
        default="report_only",
        help="Exit policy for remediation-required snapshots.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional latest alias output path for remediation_summary.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_fail_nightly_remediation(
        runs_dir=args.runs_dir,
        readiness_summary_json=args.readiness_summary_json,
        governance_summary_json=args.governance_summary_json,
        progress_summary_json=args.progress_summary_json,
        transition_summary_json=args.transition_summary_json,
        manual_cadence_summary_json=args.manual_cadence_summary_json,
        policy=args.policy,
        summary_json=args.summary_json,
    )
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
