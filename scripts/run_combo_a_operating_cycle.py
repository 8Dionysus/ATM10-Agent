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

from src.agent_core.combo_a_profile import COMBO_A_PROFILE

_SCHEMA_VERSION = "combo_a_operating_cycle_v1"
_POLICIES: tuple[str, ...] = ("report_only", "fail_on_hold")
_EFFECTIVE_POLICY_OBSERVE_ONLY = "observe_only"
_EFFECTIVE_POLICY_PROMOTED_NIGHTLY = "promoted_nightly"
_ENFORCEMENT_SURFACE = "nightly_only"
_PROFILE_SCOPE = COMBO_A_PROFILE
_FRESHNESS_WINDOW = timedelta(hours=36)

_SAFE_ACTION_LOCAL = "gateway_local_combo_a"
_SAFE_ACTION_HTTP = "gateway_http_combo_a"
_SAFE_ACTION_SUITE = "cross_service_suite_combo_a_smoke"
_SAFE_ACTION_REFRESH = "combo_a_operating_cycle_smoke"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _create_run_dir(root: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-combo-a-operating-cycle")
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


def _canonical_paths(runs_dir: Path) -> dict[str, Path]:
    root = Path(runs_dir)
    return {
        "gateway_combo_a": root / "ci-smoke-gateway-combo-a" / "gateway_smoke_summary.json",
        "gateway_http_combo_a": root / "ci-smoke-gateway-http-combo-a" / "gateway_http_smoke_summary.json",
        "cross_service_suite_combo_a": root
        / "nightly-combo-a-cross-service-suite"
        / "cross_service_benchmark_suite.json",
        "healthz": root / "nightly-combo-a-operator-probes" / "healthz.json",
        "operator_snapshot": root / "nightly-combo-a-operator-probes" / "operator_snapshot.json",
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be object")
    return payload


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _summary_timestamp(payload: Mapping[str, Any], path: Path) -> datetime | None:
    for key in ("checked_at_utc", "finished_at_utc", "timestamp_utc", "started_at_utc"):
        parsed = _parse_iso_datetime(payload.get(key))
        if parsed is not None:
            return parsed
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except Exception:
        return None


def _is_fresh(timestamp: datetime | None, *, now: datetime) -> bool:
    if timestamp is None:
        return False
    return now - timestamp <= _FRESHNESS_WINDOW


def _load_source(
    *,
    source_name: str,
    path: Path,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[str]]:
    details: dict[str, Any] = {
        "source": source_name,
        "path": str(path),
        "status": "missing",
        "fresh_within_window": False,
        "freshness_window_hours": int(_FRESHNESS_WINDOW.total_seconds() // 3600),
    }
    warnings: list[str] = []
    if not path.is_file():
        return details, None, warnings

    try:
        payload = _read_json_object(path)
    except Exception as exc:
        details["status"] = "invalid"
        warnings.append(f"{source_name}: invalid JSON: {exc}")
        return details, None, warnings

    checked_at = _summary_timestamp(payload, path)
    details.update(
        {
            "status": "present",
            "checked_at_utc": None if checked_at is None else checked_at.isoformat(),
            "fresh_within_window": _is_fresh(checked_at, now=now),
            "summary_status": payload.get("status"),
            "profile": payload.get("profile"),
            "surface": payload.get("surface"),
        }
    )
    return details, payload, warnings


def _combo_a_services_from_snapshot(operator_snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    stack_services = operator_snapshot.get("stack_services")
    stack_services = stack_services if isinstance(stack_services, Mapping) else {}
    rows: dict[str, dict[str, Any]] = {}
    for name in ("voice_runtime_service", "tts_runtime_service", "qdrant", "neo4j"):
        raw = stack_services.get(name)
        raw = raw if isinstance(raw, Mapping) else {}
        rows[name] = {
            "service_name": name,
            "configured": raw.get("configured"),
            "status": raw.get("status"),
            "url": raw.get("url"),
            "error": raw.get("error"),
        }
    return rows


def _build_recommended_actions(
    *,
    blocking_reason_codes: list[str],
    source_details: Mapping[str, Mapping[str, Any]],
    next_review_at_utc: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    def _append(action_key: str, label: str, reason: str) -> None:
        actions.append(
            {
                "action_key": action_key,
                "label": label,
                "reason": reason,
                "next_review_at_utc": next_review_at_utc,
                "surface": "gateway_safe_action",
            }
        )

    local_status = str(source_details.get("gateway_combo_a", {}).get("status", "")).strip()
    http_status = str(source_details.get("gateway_http_combo_a", {}).get("status", "")).strip()
    suite_status = str(source_details.get("cross_service_suite_combo_a", {}).get("status", "")).strip()

    if local_status in {"missing", "invalid"} or (
        local_status == "present"
        and (
            bool(source_details.get("gateway_combo_a", {}).get("fresh_within_window")) is not True
            or "gateway_local_combo_a_failed" in blocking_reason_codes
        )
    ):
        _append(
            _SAFE_ACTION_LOCAL,
            "Gateway local smoke Combo A",
            "Refresh the local Combo A gateway smoke artifact before the next nightly review.",
        )
    if http_status in {"missing", "invalid"} or (
        http_status == "present"
        and (
            bool(source_details.get("gateway_http_combo_a", {}).get("fresh_within_window")) is not True
            or "gateway_http_combo_a_failed" in blocking_reason_codes
        )
    ):
        _append(
            _SAFE_ACTION_HTTP,
            "Gateway HTTP smoke Combo A",
            "Refresh the HTTP Combo A gateway smoke artifact before the next nightly review.",
        )
    if suite_status in {"missing", "invalid"} or (
        suite_status == "present"
        and (
            bool(source_details.get("cross_service_suite_combo_a", {}).get("fresh_within_window")) is not True
            or "cross_service_suite_combo_a_error" in blocking_reason_codes
            or "cross_service_suite_combo_a_breach" in blocking_reason_codes
        )
    ):
        _append(
            _SAFE_ACTION_SUITE,
            "Cross-service suite Combo A smoke",
            "Refresh the Combo A cross-service suite artifact before the next nightly review.",
        )

    if not actions:
        _append(
            _SAFE_ACTION_REFRESH,
            "Combo A operating cycle smoke",
            "Re-evaluate the Combo A nightly decision surface after the live workflow updates its artifacts.",
        )
    return actions


def _render_summary_md(*, summary_payload: Mapping[str, Any]) -> str:
    readiness = summary_payload.get("live_readiness")
    readiness = readiness if isinstance(readiness, Mapping) else {}
    services = readiness.get("services")
    services = services if isinstance(services, Mapping) else {}
    lines = [
        "# Combo A Operating Cycle Summary",
        "",
        f"- `status`: {summary_payload.get('status')}",
        f"- `effective_policy`: {summary_payload.get('effective_policy')}",
        f"- `promotion_state`: {summary_payload.get('promotion_state')}",
        f"- `availability_status`: {summary_payload.get('availability_status')}",
        f"- `next_review_at_utc`: {summary_payload.get('next_review_at_utc')}",
        "",
        "| source | status | fresh_within_window | summary_status |",
        "|---|---|---|---|",
    ]
    sources = summary_payload.get("sources")
    sources = sources if isinstance(sources, Mapping) else {}
    for source_name in (
        "gateway_combo_a",
        "gateway_http_combo_a",
        "cross_service_suite_combo_a",
        "healthz",
        "operator_snapshot",
    ):
        source = sources.get(source_name)
        source = source if isinstance(source, Mapping) else {}
        lines.append(
            "| {source} | {status} | {fresh} | {summary_status} |".format(
                source=source_name,
                status=source.get("status", "-"),
                fresh=source.get("fresh_within_window", "-"),
                summary_status=source.get("summary_status", "-"),
            )
        )

    if services:
        lines.extend(
            [
                "",
                "| service | status | configured |",
                "|---|---|---|",
            ]
        )
        for service_name in ("voice_runtime_service", "tts_runtime_service", "qdrant", "neo4j"):
            service = services.get(service_name)
            service = service if isinstance(service, Mapping) else {}
            lines.append(
                "| {service} | {status} | {configured} |".format(
                    service=service_name,
                    status=service.get("status", "-"),
                    configured=service.get("configured", "-"),
                )
            )
    return "\n".join(lines) + "\n"


def run_combo_a_operating_cycle(
    *,
    runs_dir: Path = Path("runs"),
    policy: str = "report_only",
    summary_json: Path | None = None,
    summary_md: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if policy not in _POLICIES:
        raise ValueError(f"policy must be one of: {', '.join(_POLICIES)}")

    if now is None:
        now = datetime.now(timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    run_root = Path(runs_dir) / "nightly-combo-a-operating-cycle"
    run_dir = _create_run_dir(run_root, now=now)
    run_json_path = run_dir / "run.json"
    summary_out_path = summary_json if summary_json is not None else (run_root / "operating_cycle_summary.json")
    history_summary_path = run_dir / "operating_cycle_summary.json"
    summary_md_out_path = summary_md if summary_md is not None else (run_root / "summary.md")
    history_summary_md_path = run_dir / "summary.md"
    run_payload: dict[str, Any] = {
        "timestamp_utc": now.isoformat(),
        "mode": "combo_a_operating_cycle",
        "status": "started",
        "params": {
            "runs_dir": str(runs_dir),
            "policy": policy,
            "freshness_window_hours": int(_FRESHNESS_WINDOW.total_seconds() // 3600),
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_out_path),
            "history_summary_json": str(history_summary_path),
            "summary_md": str(summary_md_out_path),
            "history_summary_md": str(history_summary_md_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        source_details: dict[str, dict[str, Any]] = {}
        source_payloads: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for source_name, path in _canonical_paths(runs_dir).items():
            details, payload, source_warnings = _load_source(source_name=source_name, path=path, now=now)
            source_details[source_name] = details
            if payload is not None:
                source_payloads[source_name] = payload
            warnings.extend(source_warnings)

        blocking_reason_codes: list[str] = []

        missing_artifacts = [
            source_name
            for source_name, details in source_details.items()
            if str(details.get("status")) != "present"
        ]
        stale_artifacts = [
            source_name
            for source_name, details in source_details.items()
            if str(details.get("status")) == "present" and bool(details.get("fresh_within_window")) is not True
        ]
        if missing_artifacts:
            blocking_reason_codes.append("missing_live_artifact")
        if stale_artifacts:
            blocking_reason_codes.append("stale_live_artifact")

        gateway_local = source_payloads.get("gateway_combo_a", {})
        if gateway_local and str(gateway_local.get("status")) != "ok":
            blocking_reason_codes.append("gateway_local_combo_a_failed")

        gateway_http = source_payloads.get("gateway_http_combo_a", {})
        if gateway_http and str(gateway_http.get("status")) != "ok":
            blocking_reason_codes.append("gateway_http_combo_a_failed")

        suite_payload = source_payloads.get("cross_service_suite_combo_a", {})
        degraded_services = suite_payload.get("degraded_services")
        degraded_services = degraded_services if isinstance(degraded_services, list) else []
        if suite_payload:
            if str(suite_payload.get("status")) == "error":
                blocking_reason_codes.append("cross_service_suite_combo_a_error")
            elif str(suite_payload.get("overall_sla_status")) != "pass" or degraded_services:
                blocking_reason_codes.append("cross_service_suite_combo_a_breach")

        health_payload = source_payloads.get("healthz", {})
        supported_profiles = health_payload.get("supported_profiles")
        supported_profiles = supported_profiles if isinstance(supported_profiles, list) else []
        if health_payload:
            if str(health_payload.get("status")) != "ok" or COMBO_A_PROFILE not in [str(item) for item in supported_profiles]:
                blocking_reason_codes.append("operator_profile_not_ready")

        operator_snapshot = source_payloads.get("operator_snapshot", {})
        if not operator_snapshot:
            blocking_reason_codes.append("operator_snapshot_missing")

        operator_profile = {}
        combo_a_services: dict[str, dict[str, Any]] = {}
        availability_status = "unknown"
        available = False
        if operator_snapshot:
            operator_context = operator_snapshot.get("operator_context")
            operator_context = operator_context if isinstance(operator_context, Mapping) else {}
            profiles_payload = operator_context.get("profiles")
            profiles_payload = profiles_payload if isinstance(profiles_payload, Mapping) else {}
            operator_profile = profiles_payload.get("combo_a")
            operator_profile = operator_profile if isinstance(operator_profile, Mapping) else {}
            combo_a_services = _combo_a_services_from_snapshot(operator_snapshot)
            availability_status = str(operator_profile.get("availability_status", "unknown"))
            available = bool(operator_profile.get("available"))
            if str(operator_snapshot.get("status")) != "ok" or available is not True or availability_status != "ready":
                blocking_reason_codes.append("operator_profile_not_ready")

            service_code_map = {
                "voice_runtime_service": "voice_service_unhealthy",
                "tts_runtime_service": "tts_service_unhealthy",
                "qdrant": "qdrant_unhealthy",
                "neo4j": "neo4j_unhealthy",
            }
            for service_name, reason_code in service_code_map.items():
                service_row = combo_a_services.get(service_name, {})
                if not service_row:
                    continue
                if str(service_row.get("status")) != "ok":
                    blocking_reason_codes.append(reason_code)

        blocking_reason_codes = _dedupe_preserve(blocking_reason_codes)

        if blocking_reason_codes:
            promotion_state = "hold"
            effective_policy = _EFFECTIVE_POLICY_OBSERVE_ONLY
        elif policy == "fail_on_hold":
            promotion_state = "promoted"
            effective_policy = _EFFECTIVE_POLICY_PROMOTED_NIGHTLY
        else:
            promotion_state = "eligible"
            effective_policy = _EFFECTIVE_POLICY_PROMOTED_NIGHTLY

        latest_checked_at = max(
            (
                _parse_iso_datetime(details.get("checked_at_utc"))
                for details in source_details.values()
                if _parse_iso_datetime(details.get("checked_at_utc")) is not None
            ),
            default=now,
        )
        next_review_at_utc = (latest_checked_at + timedelta(days=1)).isoformat()
        recommended_actions = _build_recommended_actions(
            blocking_reason_codes=blocking_reason_codes,
            source_details=source_details,
            next_review_at_utc=next_review_at_utc,
        ) if blocking_reason_codes else []

        actionable_message = "Combo A nightly promotion is healthy and ready for promoted_nightly enforcement."
        if "operator_profile_not_ready" in blocking_reason_codes:
            actionable_message = "Combo A promotion is held until live operator readiness returns to ready."
        elif "cross_service_suite_combo_a_breach" in blocking_reason_codes or "cross_service_suite_combo_a_error" in blocking_reason_codes:
            actionable_message = "Combo A promotion is held until the live cross-service suite is green again."
        elif "gateway_local_combo_a_failed" in blocking_reason_codes or "gateway_http_combo_a_failed" in blocking_reason_codes:
            actionable_message = "Combo A promotion is held until gateway combo_a smoke artifacts are green again."
        elif "stale_live_artifact" in blocking_reason_codes:
            actionable_message = "Combo A promotion is held until live artifacts are refreshed within the 36-hour window."
        elif "missing_live_artifact" in blocking_reason_codes or "operator_snapshot_missing" in blocking_reason_codes:
            actionable_message = "Combo A promotion is held until all required live artifacts are present."

        summary_payload: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "status": "ok",
            "checked_at_utc": now.isoformat(),
            "scenario": "combo_a_policy",
            "policy": policy,
            "effective_policy": effective_policy,
            "promotion_state": promotion_state,
            "enforcement_surface": _ENFORCEMENT_SURFACE,
            "blocking_reason_codes": blocking_reason_codes,
            "recommended_actions": recommended_actions,
            "next_review_at_utc": next_review_at_utc,
            "profile_scope": _PROFILE_SCOPE,
            "availability_status": availability_status,
            "actionable_message": actionable_message,
            "sources": source_details,
            "live_readiness": {
                "profile": COMBO_A_PROFILE,
                "available": available,
                "availability_status": availability_status,
                "supported_profiles": supported_profiles,
                "services": combo_a_services,
            },
            "warnings": warnings,
            "error": None,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
                "history_summary_json": str(history_summary_path),
                "summary_md": str(summary_md_out_path),
                "history_summary_md": str(history_summary_md_path),
            },
        }
        summary_text = _render_summary_md(summary_payload=summary_payload)
        _write_json(history_summary_path, summary_payload)
        if summary_out_path != history_summary_path:
            _write_json(summary_out_path, summary_payload)
        _write_text(history_summary_md_path, summary_text)
        if summary_md_out_path != history_summary_md_path:
            _write_text(summary_md_out_path, summary_text)

        exit_code = 0
        if policy == "fail_on_hold" and promotion_state == "hold":
            exit_code = 1
        summary_payload["exit_code"] = exit_code
        _write_json(history_summary_path, summary_payload)
        if summary_out_path != history_summary_path:
            _write_json(summary_out_path, summary_payload)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "effective_policy": effective_policy,
            "promotion_state": promotion_state,
            "availability_status": availability_status,
            "blocking_reason_codes": blocking_reason_codes,
            "next_review_at_utc": next_review_at_utc,
            "profile_scope": _PROFILE_SCOPE,
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": exit_code == 0,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
            "summary_text": summary_text,
            "exit_code": exit_code,
        }
    except Exception as exc:
        summary_payload = {
            "schema_version": _SCHEMA_VERSION,
            "status": "error",
            "checked_at_utc": now.isoformat(),
            "scenario": "combo_a_policy",
            "policy": policy,
            "effective_policy": _EFFECTIVE_POLICY_OBSERVE_ONLY,
            "promotion_state": "hold",
            "enforcement_surface": _ENFORCEMENT_SURFACE,
            "blocking_reason_codes": ["operating_cycle_error"],
            "recommended_actions": [
                {
                    "action_key": _SAFE_ACTION_REFRESH,
                    "label": "Combo A operating cycle smoke",
                    "reason": "Re-run the Combo A operating cycle after the workflow error is resolved.",
                    "next_review_at_utc": None,
                    "surface": "gateway_safe_action",
                }
            ],
            "next_review_at_utc": None,
            "profile_scope": _PROFILE_SCOPE,
            "availability_status": "unknown",
            "actionable_message": "Combo A operating cycle failed before it could evaluate nightly promotion.",
            "sources": {},
            "live_readiness": {
                "profile": COMBO_A_PROFILE,
                "available": False,
                "availability_status": "unknown",
                "supported_profiles": [],
                "services": {},
            },
            "warnings": [],
            "error": str(exc),
            "exit_code": 2,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
                "history_summary_json": str(history_summary_path),
                "summary_md": str(summary_md_out_path),
                "history_summary_md": str(history_summary_md_path),
            },
        }
        summary_text = _render_summary_md(summary_payload=summary_payload)
        _write_json(history_summary_path, summary_payload)
        if summary_out_path != history_summary_path:
            _write_json(summary_out_path, summary_payload)
        _write_text(history_summary_md_path, summary_text)
        if summary_md_out_path != history_summary_md_path:
            _write_text(summary_md_out_path, summary_text)
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
            "summary_text": summary_text,
            "exit_code": 2,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Combo A nightly promotion posture from live artifacts.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    parser.add_argument(
        "--policy",
        choices=_POLICIES,
        default="report_only",
        help="report_only (default) or fail_on_hold for promoted strict evaluation.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional output path for the canonical Combo A operating cycle summary.",
    )
    parser.add_argument(
        "--summary-md",
        type=Path,
        default=None,
        help="Optional output path for the human-readable Combo A operating cycle summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_combo_a_operating_cycle(
        runs_dir=args.runs_dir,
        policy=args.policy,
        summary_json=args.summary_json,
        summary_md=args.summary_md,
    )
    summary_payload = result["summary_payload"]
    print(f"[combo_a_operating_cycle] status: {summary_payload['status']}")
    print(f"[combo_a_operating_cycle] effective_policy: {summary_payload['effective_policy']}")
    print(f"[combo_a_operating_cycle] promotion_state: {summary_payload['promotion_state']}")
    print(f"[combo_a_operating_cycle] availability_status: {summary_payload['availability_status']}")
    return int(result["exit_code"])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
