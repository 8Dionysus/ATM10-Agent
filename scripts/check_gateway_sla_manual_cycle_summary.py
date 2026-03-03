from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_SCHEMA_VERSION = "gateway_sla_manual_cycle_summary_v1"
_POLICIES: tuple[str, ...] = ("report_only", "fail_if_blocked")
_SOURCE_STATUS_PRESENT = "present"
_SOURCE_STATUS_MISSING = "missing"
_SOURCE_STATUS_INVALID = "invalid"

_EXPECTED_SCHEMAS: dict[str, str] = {
    "preflight": "gateway_sla_manual_preflight_v1",
    "readiness": "gateway_sla_fail_nightly_readiness_v1",
    "governance": "gateway_sla_fail_nightly_governance_v1",
    "progress": "gateway_sla_fail_nightly_progress_v1",
    "transition": "gateway_sla_fail_nightly_transition_v1",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _create_run_dir(runs_root: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-sla-manual-cycle-summary")
    run_dir = runs_root / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    suffix = 1
    while True:
        candidate = runs_root / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def _load_source_payload(
    *,
    source_name: str,
    path: Path,
    expected_schema_version: str,
) -> tuple[str, dict[str, Any] | None, str | None]:
    if not path.is_file():
        return _SOURCE_STATUS_MISSING, None, f"{source_name}: source file not found: {path}"

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _SOURCE_STATUS_INVALID, None, f"{source_name}: invalid JSON: {exc}"

    if not isinstance(payload, dict):
        return _SOURCE_STATUS_INVALID, None, f"{source_name}: JSON root must be object"

    schema_version = str(payload.get("schema_version", "")).strip()
    if schema_version != expected_schema_version:
        return (
            _SOURCE_STATUS_INVALID,
            None,
            f"{source_name}: schema_version={schema_version!r} expected={expected_schema_version!r}",
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


def _extract_preflight_observed(payload: Mapping[str, Any]) -> dict[str, Any]:
    observed = payload.get("observed")
    observed = observed if isinstance(observed, Mapping) else {}
    return {
        "workflow_runs_observed": observed.get("workflow_runs_observed"),
        "today_dispatch_count": observed.get("today_dispatch_count"),
        "latest_dispatch_run": observed.get("latest_dispatch_run"),
    }


def _extract_preflight_decision(payload: Mapping[str, Any]) -> dict[str, Any]:
    decision = payload.get("decision")
    if not isinstance(decision, Mapping):
        raise ValueError("preflight.decision must be object")

    if "accounted_dispatch_allowed" not in decision:
        raise ValueError("preflight.decision.accounted_dispatch_allowed is required")
    decision_status = str(decision.get("decision_status", "")).strip()
    if not decision_status:
        raise ValueError("preflight.decision.decision_status is required")

    reason_codes_raw = decision.get("reason_codes")
    if reason_codes_raw is None:
        reason_codes: list[str] = []
    elif isinstance(reason_codes_raw, list):
        reason_codes = [str(item).strip() for item in reason_codes_raw if str(item).strip()]
    else:
        raise ValueError("preflight.decision.reason_codes must be array when provided")

    next_accounted_dispatch_at = decision.get("next_accounted_dispatch_at_utc")
    if next_accounted_dispatch_at is not None:
        next_accounted_dispatch_at = str(next_accounted_dispatch_at).strip() or None

    return {
        "accounted_dispatch_allowed": bool(decision.get("accounted_dispatch_allowed")),
        "decision_status": decision_status,
        "next_accounted_dispatch_at_utc": next_accounted_dispatch_at,
        "reason_codes": reason_codes,
    }


def _extract_optional_observed(
    *,
    readiness_payload: Mapping[str, Any] | None,
    governance_payload: Mapping[str, Any] | None,
    progress_payload: Mapping[str, Any] | None,
    transition_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "readiness_status": None,
        "governance_decision_status": None,
        "progress": {
            "remaining_for_window": None,
            "remaining_for_streak": None,
            "decision_status": None,
        },
        "transition": {
            "allow_switch": None,
            "reason_codes": None,
            "decision_status": None,
        },
    }

    if isinstance(readiness_payload, Mapping):
        result["readiness_status"] = readiness_payload.get("readiness_status")

    if isinstance(governance_payload, Mapping):
        result["governance_decision_status"] = governance_payload.get("decision_status")

    if isinstance(progress_payload, Mapping):
        progress_observed = progress_payload.get("observed")
        progress_observed = progress_observed if isinstance(progress_observed, Mapping) else {}
        progress_readiness = progress_observed.get("readiness")
        progress_readiness = progress_readiness if isinstance(progress_readiness, Mapping) else {}
        result["progress"] = {
            "remaining_for_window": progress_readiness.get("remaining_for_window"),
            "remaining_for_streak": progress_readiness.get("remaining_for_streak"),
            "decision_status": progress_payload.get("decision_status"),
        }

    if isinstance(transition_payload, Mapping):
        recommendation = transition_payload.get("recommendation")
        recommendation = recommendation if isinstance(recommendation, Mapping) else {}
        result["transition"] = {
            "allow_switch": transition_payload.get("allow_switch"),
            "reason_codes": recommendation.get("reason_codes"),
            "decision_status": transition_payload.get("decision_status"),
        }

    return result


def run_gateway_sla_manual_cycle_summary(
    *,
    runs_dir: Path = Path("runs"),
    preflight_summary_json: Path | None = None,
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

    run_root = Path(runs_dir) / "nightly-gateway-sla-manual-cycle"
    run_dir = _create_run_dir(run_root, now=now)
    run_json_path = run_dir / "run.json"

    if preflight_summary_json is None:
        preflight_summary_json = Path(runs_dir) / "nightly-gateway-sla-preflight" / "preflight_summary.json"
    if readiness_summary_json is None:
        readiness_summary_json = Path(runs_dir) / "nightly-gateway-sla-readiness" / "readiness_summary.json"
    if governance_summary_json is None:
        governance_summary_json = Path(runs_dir) / "nightly-gateway-sla-governance" / "governance_summary.json"
    if progress_summary_json is None:
        progress_summary_json = Path(runs_dir) / "nightly-gateway-sla-progress" / "progress_summary.json"
    if transition_summary_json is None:
        transition_summary_json = Path(runs_dir) / "nightly-gateway-sla-transition" / "transition_summary.json"
    if summary_json is None:
        summary_json = run_root / "manual_cycle_summary.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.isoformat(),
        "mode": "gateway_sla_manual_cycle_summary",
        "status": "started",
        "params": {
            "runs_dir": str(runs_dir),
            "policy": policy,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_json),
            "preflight_summary_json": str(preflight_summary_json),
            "readiness_summary_json": str(readiness_summary_json),
            "governance_summary_json": str(governance_summary_json),
            "progress_summary_json": str(progress_summary_json),
            "transition_summary_json": str(transition_summary_json),
        },
    }
    _write_json(run_json_path, run_payload)

    warnings: list[str] = []
    failure_reason_codes: list[str] | None = None
    source_payloads: dict[str, dict[str, Any] | None] = {}
    sources: dict[str, dict[str, Any]] = {}
    source_inputs: list[tuple[str, Path]] = [
        ("preflight", preflight_summary_json),
        ("readiness", readiness_summary_json),
        ("governance", governance_summary_json),
        ("progress", progress_summary_json),
        ("transition", transition_summary_json),
    ]
    try:

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

        preflight_source_status = sources["preflight"]["status"]
        if preflight_source_status != _SOURCE_STATUS_PRESENT or source_payloads["preflight"] is None:
            if preflight_source_status == _SOURCE_STATUS_MISSING:
                failure_reason_codes = ["preflight_summary_missing"]
            else:
                failure_reason_codes = ["preflight_summary_invalid"]
            raise RuntimeError(
                f"required preflight summary is not available: {sources['preflight']['path']}"
            )

        preflight_payload = source_payloads["preflight"]
        assert preflight_payload is not None
        preflight_status = str(preflight_payload.get("status", "")).strip()
        if preflight_status != "ok":
            failure_reason_codes = ["preflight_summary_not_ok"]
            raise RuntimeError(f"preflight summary status must be 'ok', observed {preflight_status!r}")

        try:
            preflight_decision = _extract_preflight_decision(preflight_payload)
        except ValueError as exc:
            failure_reason_codes = ["preflight_decision_invalid"]
            raise RuntimeError(str(exc)) from exc
        preflight_observed = _extract_preflight_observed(preflight_payload)
        optional_observed = _extract_optional_observed(
            readiness_payload=source_payloads["readiness"],
            governance_payload=source_payloads["governance"],
            progress_payload=source_payloads["progress"],
            transition_payload=source_payloads["transition"],
        )

        exit_code = 0
        if policy == "fail_if_blocked" and not bool(preflight_decision["accounted_dispatch_allowed"]):
            exit_code = 2

        summary_payload: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "status": "ok",
            "checked_at_utc": _utc_now(),
            "policy": policy,
            "sources": sources,
            "observed": {
                "preflight": preflight_observed,
                **optional_observed,
            },
            "decision": preflight_decision,
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
            "decision_status": preflight_decision["decision_status"],
            "accounted_dispatch_allowed": preflight_decision["accounted_dispatch_allowed"],
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
        error_message = str(exc)
        reason_codes = list(failure_reason_codes or ["manual_cycle_summary_failed"])
        if sources:
            summary_sources = sources
        else:
            summary_sources = {}
            for source_name, source_path in source_inputs:
                source_status = _SOURCE_STATUS_INVALID if source_path.is_file() else _SOURCE_STATUS_MISSING
                summary_sources[source_name] = _source_details(
                    path=source_path,
                    source_status=source_status,
                    expected_schema_version=_EXPECTED_SCHEMAS[source_name],
                    payload=None,
                )
        summary_payload = {
            "schema_version": _SCHEMA_VERSION,
            "status": "error",
            "checked_at_utc": _utc_now(),
            "policy": policy,
            "sources": summary_sources,
            "observed": {
                "preflight": {
                    "workflow_runs_observed": None,
                    "today_dispatch_count": None,
                    "latest_dispatch_run": None,
                },
                "readiness_status": None,
                "governance_decision_status": None,
                "progress": {
                    "remaining_for_window": None,
                    "remaining_for_streak": None,
                    "decision_status": None,
                },
                "transition": {
                    "allow_switch": None,
                    "reason_codes": None,
                    "decision_status": None,
                },
            },
            "decision": {
                "accounted_dispatch_allowed": False,
                "decision_status": "error",
                "next_accounted_dispatch_at_utc": None,
                "reason_codes": reason_codes,
            },
            "warnings": warnings,
            "error": error_message,
            "exit_code": 2,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_json),
            },
        }
        _write_json(summary_json, summary_payload)

        run_payload["status"] = "error"
        run_payload["error_code"] = "gateway_sla_manual_cycle_summary_failed"
        run_payload["error"] = error_message
        run_payload["result"] = {
            "decision_status": "error",
            "accounted_dispatch_allowed": False,
            "exit_code": 2,
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
        description="Build unified machine-readable summary for G2 manual cycle (preflight + readiness/governance/progress/transition)."
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base runs directory.",
    )
    parser.add_argument(
        "--preflight-summary-json",
        type=Path,
        default=None,
        help="Optional path override for gateway_sla_manual_preflight_v1 summary.",
    )
    parser.add_argument(
        "--readiness-summary-json",
        type=Path,
        default=None,
        help="Optional path override for gateway_sla_fail_nightly_readiness_v1 summary.",
    )
    parser.add_argument(
        "--governance-summary-json",
        type=Path,
        default=None,
        help="Optional path override for gateway_sla_fail_nightly_governance_v1 summary.",
    )
    parser.add_argument(
        "--progress-summary-json",
        type=Path,
        default=None,
        help="Optional path override for gateway_sla_fail_nightly_progress_v1 summary.",
    )
    parser.add_argument(
        "--transition-summary-json",
        type=Path,
        default=None,
        help="Optional path override for gateway_sla_fail_nightly_transition_v1 summary.",
    )
    parser.add_argument(
        "--policy",
        choices=_POLICIES,
        default="report_only",
        help="Exit policy: report_only (default) or fail_if_blocked.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Output path for gateway_sla_manual_cycle_summary_v1 summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_sla_manual_cycle_summary(
        runs_dir=args.runs_dir,
        preflight_summary_json=args.preflight_summary_json,
        readiness_summary_json=args.readiness_summary_json,
        governance_summary_json=args.governance_summary_json,
        progress_summary_json=args.progress_summary_json,
        transition_summary_json=args.transition_summary_json,
        policy=args.policy,
        summary_json=args.summary_json,
    )
    summary_payload = result["summary_payload"]
    print(f"[check_gateway_sla_manual_cycle_summary] run_dir: {result['run_dir']}")
    print(
        "[check_gateway_sla_manual_cycle_summary] "
        f"summary_json: {result['run_payload']['paths']['summary_json']}"
    )
    print(
        "[check_gateway_sla_manual_cycle_summary] "
        f"decision_status: {summary_payload['decision']['decision_status']}"
    )
    print(
        "[check_gateway_sla_manual_cycle_summary] "
        f"accounted_dispatch_allowed: {summary_payload['decision']['accounted_dispatch_allowed']}"
    )
    print(f"[check_gateway_sla_manual_cycle_summary] exit_code: {summary_payload['exit_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
