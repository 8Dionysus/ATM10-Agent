from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_gateway_sla_fail_nightly_integrity import run_gateway_sla_fail_nightly_integrity
from scripts.check_gateway_sla_fail_nightly_remediation import run_gateway_sla_fail_nightly_remediation
from scripts.check_gateway_sla_manual_cadence_brief import run_gateway_sla_manual_cadence_brief
from scripts.run_gateway_sla_manual_nightly import run_gateway_sla_manual_nightly

_SCHEMA_VERSION = "gateway_sla_operating_cycle_v1"
_POLICIES: tuple[str, ...] = ("report_only",)
_SOURCE_STATUS_PRESENT = "present"
_SOURCE_STATUS_MISSING = "missing"
_SOURCE_STATUS_INVALID = "invalid"
_MANUAL_CLUSTER_WINDOW = timedelta(minutes=15)
_CRITICAL_INTEGRITY_CODES = {
    "required_sources_unhealthy",
    "dual_write_invariant_broken",
    "anti_double_count_invariant_broken",
}
_EXPECTED_SCHEMAS: dict[str, str] = {
    "readiness": "gateway_sla_fail_nightly_readiness_v1",
    "governance": "gateway_sla_fail_nightly_governance_v1",
    "progress": "gateway_sla_fail_nightly_progress_v1",
    "transition": "gateway_sla_fail_nightly_transition_v1",
    "remediation": "gateway_sla_fail_nightly_remediation_v1",
    "integrity": "gateway_sla_fail_nightly_integrity_v1",
    "cadence": "gateway_sla_manual_cadence_brief_v1",
    "manual_runner": "gateway_sla_manual_nightly_runner_v1",
}
_REQUIRED_SOURCES: tuple[str, ...] = (
    "readiness",
    "governance",
    "progress",
    "transition",
    "remediation",
    "integrity",
)
_SOURCE_ORDER: tuple[str, ...] = _REQUIRED_SOURCES + ("cadence",)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _create_run_dir(root: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-operating-cycle")
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


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _is_same_utc_day(timestamp: datetime | None, now: datetime) -> bool:
    if timestamp is None:
        return False
    return timestamp.date() == now.date()


def _coerce_string_list(value: Any) -> list[str]:
    if value is None or not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _load_source_details(
    *,
    source_name: str,
    path: Path,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
    expected_schema_version = _EXPECTED_SCHEMAS[source_name]
    details: dict[str, Any] = {
        "path": str(path),
        "status": _SOURCE_STATUS_MISSING,
        "expected_schema_version": expected_schema_version,
        "fresh_for_current_utc_day": False,
    }

    if not path.is_file():
        return details, None, f"{source_name}: source file not found: {path}"

    try:
        payload = _read_json_object(path)
    except Exception as exc:
        details["status"] = _SOURCE_STATUS_INVALID
        return details, None, f"{source_name}: invalid JSON: {exc}"

    details["observed_schema_version"] = payload.get("schema_version")
    details["summary_status"] = payload.get("status")
    checked_at_utc = payload.get("checked_at_utc")
    if checked_at_utc is not None:
        details["checked_at_utc"] = checked_at_utc
    checked_at = _parse_iso_datetime(checked_at_utc)
    details["fresh_for_current_utc_day"] = _is_same_utc_day(checked_at, now)

    if str(payload.get("schema_version", "")).strip() != expected_schema_version:
        details["status"] = _SOURCE_STATUS_INVALID
        return (
            details,
            payload,
            f"{source_name}: schema_version={payload.get('schema_version')!r} expected={expected_schema_version!r}",
        )
    if str(payload.get("status", "")).strip() != "ok":
        details["status"] = _SOURCE_STATUS_INVALID
        return details, payload, f"{source_name}: summary status must be 'ok'"

    details["status"] = _SOURCE_STATUS_PRESENT
    return details, payload, None


def _load_source_bundle(
    *,
    runs_dir: Path,
    now: datetime,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    paths = {
        "readiness": runs_dir / "nightly-gateway-sla-readiness" / "readiness_summary.json",
        "governance": runs_dir / "nightly-gateway-sla-governance" / "governance_summary.json",
        "progress": runs_dir / "nightly-gateway-sla-progress" / "progress_summary.json",
        "transition": runs_dir / "nightly-gateway-sla-transition" / "transition_summary.json",
        "remediation": runs_dir / "nightly-gateway-sla-remediation" / "remediation_summary.json",
        "integrity": runs_dir / "nightly-gateway-sla-integrity" / "integrity_summary.json",
        "cadence": runs_dir / "nightly-gateway-sla-manual-cadence" / "cadence_brief.json",
        "manual_runner": runs_dir / "nightly-gateway-sla-manual-runner" / "manual_nightly_summary.json",
    }

    sources: dict[str, dict[str, Any]] = {}
    payloads: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for source_name, path in paths.items():
        details, payload, issue = _load_source_details(source_name=source_name, path=path, now=now)
        sources[source_name] = details
        if payload is not None:
            payloads[source_name] = payload
        if issue is not None:
            warnings.append(issue)
    return sources, payloads, warnings


def _required_sources_fresh(sources: Mapping[str, Mapping[str, Any]]) -> bool:
    for source_name in _REQUIRED_SOURCES:
        source = sources.get(source_name, {})
        if str(source.get("status", "")) != _SOURCE_STATUS_PRESENT:
            return False
        if bool(source.get("fresh_for_current_utc_day")) is not True:
            return False
    return True


def _manual_snapshot_is_current_cluster(
    *,
    sources: Mapping[str, Mapping[str, Any]],
    payloads: Mapping[str, Mapping[str, Any]],
    now: datetime,
) -> bool:
    manual_source = sources.get("manual_runner", {})
    if str(manual_source.get("status", "")) != _SOURCE_STATUS_PRESENT:
        return False
    manual_checked_at = _parse_iso_datetime(manual_source.get("checked_at_utc"))
    if not _is_same_utc_day(manual_checked_at, now):
        return False

    manual_payload = payloads.get("manual_runner", {})
    if not str(manual_payload.get("execution_mode", "")).strip():
        return False

    cluster_sources = list(_REQUIRED_SOURCES)
    if str(sources.get("cadence", {}).get("status", "")) == _SOURCE_STATUS_PRESENT:
        cluster_sources.append("cadence")

    for source_name in cluster_sources:
        source_checked_at = _parse_iso_datetime(sources.get(source_name, {}).get("checked_at_utc"))
        if not _is_same_utc_day(source_checked_at, now):
            return False
        if source_checked_at is None or manual_checked_at is None:
            return False
        delta = source_checked_at - manual_checked_at
        if delta < timedelta(minutes=-1) or delta > _MANUAL_CLUSTER_WINDOW:
            return False
    return True


def _extract_manual_runner_details(payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    manual_payload = payloads.get("manual_runner")
    if not isinstance(manual_payload, Mapping):
        return {
            "checked_at_utc": None,
            "execution_mode": None,
            "decision_status": None,
            "next_accounted_dispatch_at_utc": None,
        }

    decision = manual_payload.get("decision")
    decision = decision if isinstance(decision, Mapping) else {}
    return {
        "checked_at_utc": manual_payload.get("checked_at_utc"),
        "execution_mode": manual_payload.get("execution_mode"),
        "decision_status": decision.get("decision_status"),
        "next_accounted_dispatch_at_utc": decision.get("next_accounted_dispatch_at_utc"),
    }


def _extract_triage(payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    progress = payloads.get("progress", {})
    remediation = payloads.get("remediation", {})
    integrity = payloads.get("integrity", {})
    cadence = payloads.get("cadence", {})

    remediation_candidate_items = remediation.get("candidate_items")
    remediation_candidate_items = remediation_candidate_items if isinstance(remediation_candidate_items, list) else []
    integrity_decision = integrity.get("decision")
    integrity_decision = integrity_decision if isinstance(integrity_decision, Mapping) else {}
    integrity_observed = integrity.get("observed")
    integrity_observed = integrity_observed if isinstance(integrity_observed, Mapping) else {}
    cadence_forecast = cadence.get("forecast")
    cadence_forecast = cadence_forecast if isinstance(cadence_forecast, Mapping) else {}
    cadence_decision = cadence.get("decision")
    cadence_decision = cadence_decision if isinstance(cadence_decision, Mapping) else {}

    return {
        "readiness_status": payloads.get("readiness", {}).get("readiness_status"),
        "governance_decision_status": payloads.get("governance", {}).get("decision_status"),
        "progress_decision_status": progress.get("decision_status"),
        "remaining_for_window": progress.get("observed", {}).get("readiness", {}).get("remaining_for_window"),
        "remaining_for_streak": progress.get("observed", {}).get("readiness", {}).get("remaining_for_streak"),
        "transition_allow_switch": payloads.get("transition", {}).get("allow_switch"),
        "candidate_item_ids": [
            str(item.get("id", "")).strip()
            for item in remediation_candidate_items
            if isinstance(item, Mapping) and str(item.get("id", "")).strip()
        ],
        "candidate_item_count": len(remediation_candidate_items),
        "reason_codes": _coerce_string_list(remediation.get("reason_codes")),
        "integrity_status": integrity_decision.get("integrity_status"),
        "integrity_reason_codes": _coerce_string_list(integrity_decision.get("reason_codes")),
        "invalid_counts": integrity_observed.get("invalid_counts", {}),
        "attention_state": cadence.get("attention_state"),
        "earliest_go_candidate_at_utc": cadence_forecast.get("earliest_go_candidate_at_utc"),
        "next_accounted_dispatch_at_utc": cadence_decision.get("next_accounted_dispatch_at_utc"),
    }


def _build_interpretation(*, triage: Mapping[str, Any], manual_details: Mapping[str, Any]) -> dict[str, Any]:
    integrity_status = str(triage.get("integrity_status", "")).strip()
    integrity_reason_codes = set(_coerce_string_list(triage.get("integrity_reason_codes")))
    telemetry_repair_required = integrity_status == "attention" or bool(
        integrity_reason_codes.intersection(_CRITICAL_INTEGRITY_CODES)
    )
    blocked_manual_gate = str(manual_details.get("execution_mode", "")).strip() == "blocked"
    remediation_backlog_primary = bool(triage.get("candidate_item_count")) and not telemetry_repair_required

    next_action_hint = "monitor_next_cycle"
    if telemetry_repair_required:
        next_action_hint = "repair_telemetry_first"
    elif blocked_manual_gate:
        next_action_hint = "wait_for_utc_reset"
    elif str(triage.get("attention_state", "")).strip() == "run_recovery_only":
        next_action_hint = "run_recovery_only"
    elif remediation_backlog_primary:
        next_action_hint = "continue_g2_backlog"

    return {
        "telemetry_repair_required": telemetry_repair_required,
        "remediation_backlog_primary": remediation_backlog_primary,
        "blocked_manual_gate": blocked_manual_gate,
        "next_action_hint": next_action_hint,
    }


def _render_brief_markdown(
    *,
    checked_at_utc: str,
    cycle: Mapping[str, Any],
    triage: Mapping[str, Any],
    interpretation: Mapping[str, Any],
) -> str:
    lines = [
        "# G2 Operating Cycle Brief",
        "",
        f"- checked_at_utc: `{checked_at_utc}`",
        f"- source: `{cycle.get('source')}`",
        f"- operating_mode: `{cycle.get('operating_mode')}`",
        f"- used_manual_fallback: `{cycle.get('used_manual_fallback')}`",
    ]
    if cycle.get("manual_execution_mode") is not None:
        lines.append(f"- manual_execution_mode: `{cycle.get('manual_execution_mode')}`")
    if cycle.get("manual_decision_status") is not None:
        lines.append(f"- manual_decision_status: `{cycle.get('manual_decision_status')}`")
    lines.extend(
        [
            f"- readiness_status: `{triage.get('readiness_status')}`",
            f"- governance_decision_status: `{triage.get('governance_decision_status')}`",
            f"- progress_decision_status: `{triage.get('progress_decision_status')}`",
            f"- remaining_for_window: `{triage.get('remaining_for_window')}`",
            f"- remaining_for_streak: `{triage.get('remaining_for_streak')}`",
            f"- transition_allow_switch: `{triage.get('transition_allow_switch')}`",
            f"- candidate_item_ids: `{', '.join(_coerce_string_list(triage.get('candidate_item_ids')))}`",
            f"- integrity_status: `{triage.get('integrity_status')}`",
            f"- attention_state: `{triage.get('attention_state')}`",
            f"- earliest_go_candidate_at_utc: `{triage.get('earliest_go_candidate_at_utc')}`",
            f"- telemetry_repair_required: `{interpretation.get('telemetry_repair_required')}`",
            f"- remediation_backlog_primary: `{interpretation.get('remediation_backlog_primary')}`",
            f"- next_action_hint: `{interpretation.get('next_action_hint')}`",
        ]
    )
    return "\n".join(lines) + "\n"


def run_gateway_sla_operating_cycle(
    *,
    runs_dir: Path = Path("runs"),
    policy: str = "report_only",
    summary_json: Path | None = None,
    brief_md: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if policy not in _POLICIES:
        raise ValueError(f"policy must be one of: {', '.join(_POLICIES)}")

    if now is None:
        now = datetime.now(timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    run_root = Path(runs_dir) / "nightly-gateway-sla-operating-cycle"
    run_dir = _create_run_dir(run_root, now=now)
    run_json_path = run_dir / "run.json"
    summary_out_path = summary_json if summary_json is not None else (run_root / "operating_cycle_summary.json")
    history_summary_path = run_dir / "operating_cycle_summary.json"
    brief_out_path = brief_md if brief_md is not None else (run_root / "triage_brief.md")
    history_brief_path = run_dir / "triage_brief.md"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.isoformat(),
        "mode": "gateway_sla_operating_cycle",
        "status": "started",
        "params": {
            "runs_dir": str(runs_dir),
            "policy": policy,
            "manual_cluster_window_minutes": int(_MANUAL_CLUSTER_WINDOW.total_seconds() // 60),
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_out_path),
            "history_summary_json": str(history_summary_path),
            "brief_md": str(brief_out_path),
            "history_brief_md": str(history_brief_path),
        },
    }
    _write_json(run_json_path, run_payload)

    warnings: list[str] = []
    try:
        precheck_sources, precheck_payloads, precheck_warnings = _load_source_bundle(runs_dir=runs_dir, now=now)
        warnings.extend(precheck_warnings)
        fresh_latest_available = _required_sources_fresh(precheck_sources)
        manual_snapshot_reused = fresh_latest_available and _manual_snapshot_is_current_cluster(
            sources=precheck_sources,
            payloads=precheck_payloads,
            now=now,
        )

        cycle_source = "manual" if manual_snapshot_reused else "nightly"
        operating_mode = "reuse_fresh_latest"
        used_manual_fallback = False

        if not fresh_latest_available:
            operating_mode = "manual_fallback"
            cycle_source = "manual"
            used_manual_fallback = True

            manual_result = run_gateway_sla_manual_nightly(
                runs_dir=Path(runs_dir),
                policy=policy,
                summary_json=Path(runs_dir) / "nightly-gateway-sla-manual-runner" / "manual_nightly_summary.json",
                manual_cycle_summary_json=Path(runs_dir)
                / "nightly-gateway-sla-manual-cycle"
                / "manual_cycle_summary.json",
                preflight_summary_json=Path(runs_dir)
                / "nightly-gateway-sla-preflight"
                / "local_preflight_summary.json",
                now=now,
            )
            cadence_result = run_gateway_sla_manual_cadence_brief(
                runs_dir=Path(runs_dir),
                policy=policy,
                summary_json=Path(runs_dir) / "nightly-gateway-sla-manual-cadence" / "cadence_brief.json",
                now=now,
            )
            remediation_result = run_gateway_sla_fail_nightly_remediation(
                runs_dir=Path(runs_dir),
                policy=policy,
                summary_json=Path(runs_dir) / "nightly-gateway-sla-remediation" / "remediation_summary.json",
                now=now,
            )
            integrity_result = run_gateway_sla_fail_nightly_integrity(
                runs_dir=Path(runs_dir),
                policy=policy,
                summary_json=Path(runs_dir) / "nightly-gateway-sla-integrity" / "integrity_summary.json",
                now=now,
            )

            for step_name, step_result in (
                ("manual_nightly", manual_result),
                ("cadence", cadence_result),
                ("remediation", remediation_result),
                ("integrity", integrity_result),
            ):
                exit_code = int(step_result.get("exit_code", 2)) if isinstance(step_result, Mapping) else 2
                if exit_code != 0:
                    raise RuntimeError(f"{step_name}: exit_code={exit_code}")

        sources, payloads, final_warnings = _load_source_bundle(runs_dir=runs_dir, now=now)
        warnings.extend(final_warnings)
        manual_details = _extract_manual_runner_details(payloads)
        triage = _extract_triage(payloads)
        interpretation = _build_interpretation(triage=triage, manual_details=manual_details)

        summary_payload: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "status": "ok",
            "checked_at_utc": now.isoformat(),
            "policy": policy,
            "precheck": {
                "required_sources_fresh_current_utc_day": fresh_latest_available,
                "sources": {name: precheck_sources[name] for name in _SOURCE_ORDER if name in precheck_sources},
                "manual_snapshot_reused": manual_snapshot_reused,
            },
            "cycle": {
                "source": cycle_source,
                "operating_mode": operating_mode,
                "used_manual_fallback": used_manual_fallback,
                "manual_execution_mode": manual_details.get("execution_mode"),
                "manual_decision_status": manual_details.get("decision_status"),
                "next_accounted_dispatch_at_utc": manual_details.get("next_accounted_dispatch_at_utc"),
            },
            "sources": {name: sources[name] for name in _SOURCE_ORDER if name in sources},
            "triage": triage,
            "interpretation": interpretation,
            "warnings": warnings,
            "error": None,
            "exit_code": 0,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
                "history_summary_json": str(history_summary_path),
                "brief_md": str(brief_out_path),
                "history_brief_md": str(history_brief_path),
            },
        }

        brief_text = _render_brief_markdown(
            checked_at_utc=summary_payload["checked_at_utc"],
            cycle=summary_payload["cycle"],
            triage=triage,
            interpretation=interpretation,
        )

        _write_json(history_summary_path, summary_payload)
        _write_json(summary_out_path, summary_payload)
        _write_text(history_brief_path, brief_text)
        _write_text(brief_out_path, brief_text)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "cycle_source": cycle_source,
            "operating_mode": operating_mode,
            "used_manual_fallback": used_manual_fallback,
            "telemetry_repair_required": interpretation["telemetry_repair_required"],
            "next_action_hint": interpretation["next_action_hint"],
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
            "brief_text": brief_text,
            "exit_code": 0,
        }
    except Exception as exc:
        summary_payload = {
            "schema_version": _SCHEMA_VERSION,
            "status": "error",
            "checked_at_utc": now.isoformat(),
            "policy": policy,
            "precheck": {},
            "cycle": {
                "source": "unknown",
                "operating_mode": "error",
                "used_manual_fallback": False,
                "manual_execution_mode": None,
                "manual_decision_status": None,
                "next_accounted_dispatch_at_utc": None,
            },
            "sources": {},
            "triage": {},
            "interpretation": {
                "telemetry_repair_required": False,
                "remediation_backlog_primary": False,
                "blocked_manual_gate": False,
                "next_action_hint": "error",
            },
            "warnings": warnings,
            "error": str(exc),
            "exit_code": 2,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
                "history_summary_json": str(history_summary_path),
                "brief_md": str(brief_out_path),
                "history_brief_md": str(history_brief_path),
            },
        }
        brief_text = "# G2 Operating Cycle Brief\n\n- status: `error`\n"
        _write_json(history_summary_path, summary_payload)
        _write_json(summary_out_path, summary_payload)
        _write_text(history_brief_path, brief_text)
        _write_text(brief_out_path, brief_text)

        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        run_payload["error_code"] = "gateway_sla_operating_cycle_failed"
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
            "brief_text": brief_text,
            "exit_code": 2,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one G2 operating cycle: reuse fresh latest summaries or execute manual fallback."
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Base runs directory.")
    parser.add_argument("--policy", choices=_POLICIES, default="report_only", help="Exit policy.")
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional latest alias output path for gateway_sla_operating_cycle_v1 summary.",
    )
    parser.add_argument(
        "--brief-md",
        type=Path,
        default=None,
        help="Optional latest alias output path for short triage brief markdown.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_operating_cycle(
        runs_dir=args.runs_dir,
        policy=args.policy,
        summary_json=args.summary_json,
        brief_md=args.brief_md,
    )
    summary_payload = result["summary_payload"]
    triage = summary_payload.get("triage", {})
    cycle = summary_payload.get("cycle", {})
    interpretation = summary_payload.get("interpretation", {})
    print(f"[run_gateway_sla_operating_cycle] run_dir: {result['run_dir']}")
    print(f"[run_gateway_sla_operating_cycle] summary_json: {summary_payload['paths']['summary_json']}")
    print(f"[run_gateway_sla_operating_cycle] source: {cycle.get('source')}")
    print(f"[run_gateway_sla_operating_cycle] operating_mode: {cycle.get('operating_mode')}")
    print(f"[run_gateway_sla_operating_cycle] remaining_for_window: {triage.get('remaining_for_window')}")
    print(f"[run_gateway_sla_operating_cycle] integrity_status: {triage.get('integrity_status')}")
    print(f"[run_gateway_sla_operating_cycle] next_action_hint: {interpretation.get('next_action_hint')}")
    print(f"[run_gateway_sla_operating_cycle] exit_code: {result['exit_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
