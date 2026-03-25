from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib import error as url_error
from urllib import request

from src.agent_core.combo_a_profile import (
    COMBO_A_PROFILE,
    DEFAULT_PROFILE,
    DEFAULT_COMBO_A_NEO4J_DATABASE,
    DEFAULT_COMBO_A_NEO4J_USER,
    SUPPORTED_PROFILES,
    probe_neo4j_service,
    probe_qdrant_service,
)

GATEWAY_OPERATOR_STATUS_SCHEMA = "gateway_operator_status_v1"
GATEWAY_OPERATOR_RUNS_SCHEMA = "gateway_operator_runs_v1"
GATEWAY_OPERATOR_HISTORY_SCHEMA = "gateway_operator_history_v1"
GATEWAY_OPERATOR_GOVERNANCE_SCHEMA = "gateway_operator_governance_summary_v1"
OPERATOR_PRODUCT_STARTUP_SCHEMA = "operator_product_startup_v1"
PILOT_RUNTIME_STATUS_SCHEMA = "pilot_runtime_status_v1"
PILOT_TURN_SCHEMA = "pilot_turn_v1"
PILOT_RUNTIME_STATUS_FILENAME = "pilot_runtime_status_latest.json"

FAIL_NIGHTLY_PROGRESS_SOURCE_SPECS: dict[str, dict[str, tuple[str, ...] | str]] = {
    "readiness": {
        "path_parts": ("nightly-gateway-sla-readiness", "readiness_summary.json"),
        "schema_version": "gateway_sla_fail_nightly_readiness_v1",
    },
    "governance": {
        "path_parts": ("nightly-gateway-sla-governance", "governance_summary.json"),
        "schema_version": "gateway_sla_fail_nightly_governance_v1",
    },
    "progress": {
        "path_parts": ("nightly-gateway-sla-progress", "progress_summary.json"),
        "schema_version": "gateway_sla_fail_nightly_progress_v1",
    },
}

FAIL_NIGHTLY_REMEDIATION_SOURCE_SPEC: dict[str, tuple[str, ...] | str] = {
    "path_parts": ("nightly-gateway-sla-remediation", "remediation_summary.json"),
    "schema_version": "gateway_sla_fail_nightly_remediation_v1",
}

FAIL_NIGHTLY_TRANSITION_SOURCE_SPEC: dict[str, tuple[str, ...] | str] = {
    "path_parts": ("nightly-gateway-sla-transition", "transition_summary.json"),
    "schema_version": "gateway_sla_fail_nightly_transition_v1",
}

FAIL_NIGHTLY_INTEGRITY_SOURCE_SPEC: dict[str, tuple[str, ...] | str] = {
    "path_parts": ("nightly-gateway-sla-integrity", "integrity_summary.json"),
    "schema_version": "gateway_sla_fail_nightly_integrity_v1",
}

OPERATING_CYCLE_SOURCE_SPEC: dict[str, tuple[str, ...] | str] = {
    "path_parts": ("nightly-gateway-sla-operating-cycle", "operating_cycle_summary.json"),
    "schema_version": "gateway_sla_operating_cycle_v1",
}

COMBO_A_OPERATING_CYCLE_SOURCE_SPEC: dict[str, tuple[str, ...] | str] = {
    "path_parts": ("nightly-combo-a-operating-cycle", "operating_cycle_summary.json"),
    "schema_version": "combo_a_operating_cycle_v1",
}

PILOT_RUNTIME_READINESS_SOURCE_SPEC: dict[str, tuple[str, ...] | str] = {
    "path_parts": ("pilot-runtime-readiness", "readiness_summary.json"),
    "schema_version": "pilot_runtime_readiness_v1",
}

HISTORY_SOURCE_SPECS: dict[str, dict[str, str | None]] = {
    "phase_a": {
        "root_subdir": "ci-smoke-phase-a",
        "expected_mode": "phase_a_smoke",
        "expected_scenario": None,
    },
    "retrieve": {
        "root_subdir": "ci-smoke-retrieve",
        "expected_mode": "retrieve_demo",
        "expected_scenario": None,
    },
    "eval": {
        "root_subdir": "ci-smoke-eval",
        "expected_mode": "eval_retrieval",
        "expected_scenario": None,
    },
    "gateway_core": {
        "root_subdir": "ci-smoke-gateway-core",
        "expected_mode": "gateway_v1_smoke",
        "expected_scenario": "core",
    },
    "gateway_hybrid": {
        "root_subdir": "ci-smoke-gateway-hybrid",
        "expected_mode": "gateway_v1_smoke",
        "expected_scenario": "hybrid",
    },
    "gateway_automation": {
        "root_subdir": "ci-smoke-gateway-automation",
        "expected_mode": "gateway_v1_smoke",
        "expected_scenario": "automation",
    },
    "gateway_combo_a": {
        "root_subdir": "ci-smoke-gateway-combo-a",
        "expected_mode": "gateway_v1_smoke",
        "expected_scenario": "combo_a",
    },
    "gateway_http_core": {
        "root_subdir": "ci-smoke-gateway-http-core",
        "expected_mode": "gateway_v1_http_smoke",
        "expected_scenario": "core",
    },
    "gateway_http_hybrid": {
        "root_subdir": "ci-smoke-gateway-http-hybrid",
        "expected_mode": "gateway_v1_http_smoke",
        "expected_scenario": "hybrid",
    },
    "gateway_http_automation": {
        "root_subdir": "ci-smoke-gateway-http-automation",
        "expected_mode": "gateway_v1_http_smoke",
        "expected_scenario": "automation",
    },
    "gateway_http_combo_a": {
        "root_subdir": "ci-smoke-gateway-http-combo-a",
        "expected_mode": "gateway_v1_http_smoke",
        "expected_scenario": "combo_a",
    },
    "cross_service_suite": {
        "root_subdir": "ci-smoke-cross-service-suite",
        "expected_mode": "cross_service_benchmark_suite",
        "expected_scenario": None,
    },
    "cross_service_suite_combo_a": {
        "root_subdir": "nightly-combo-a-cross-service-suite",
        "expected_mode": "cross_service_benchmark_suite",
        "expected_scenario": None,
    },
    "combo_a_operating_cycle": {
        "root_subdir": "nightly-combo-a-operating-cycle",
        "expected_mode": "combo_a_operating_cycle",
        "expected_scenario": "combo_a_policy",
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_summary_sources(runs_dir: Path) -> dict[str, Path]:
    base = Path(runs_dir)
    return {
        "phase_a": base / "ci-smoke-phase-a" / "smoke_summary.json",
        "retrieve": base / "ci-smoke-retrieve" / "smoke_summary.json",
        "eval": base / "ci-smoke-eval" / "smoke_summary.json",
        "gateway_core": base / "ci-smoke-gateway-core" / "gateway_smoke_summary.json",
        "gateway_hybrid": base / "ci-smoke-gateway-hybrid" / "gateway_smoke_summary.json",
        "gateway_automation": base / "ci-smoke-gateway-automation" / "gateway_smoke_summary.json",
        "gateway_combo_a": base / "ci-smoke-gateway-combo-a" / "gateway_smoke_summary.json",
        "gateway_http_core": base / "ci-smoke-gateway-http-core" / "gateway_http_smoke_summary.json",
        "gateway_http_hybrid": base / "ci-smoke-gateway-http-hybrid" / "gateway_http_smoke_summary.json",
        "gateway_http_automation": base / "ci-smoke-gateway-http-automation" / "gateway_http_smoke_summary.json",
        "gateway_http_combo_a": base / "ci-smoke-gateway-http-combo-a" / "gateway_http_smoke_summary.json",
        "cross_service_suite": base / "ci-smoke-cross-service-suite" / "cross_service_benchmark_suite.json",
        "cross_service_suite_combo_a": base
        / "nightly-combo-a-cross-service-suite"
        / "cross_service_benchmark_suite.json",
        "combo_a_operating_cycle": base
        / "nightly-combo-a-operating-cycle"
        / "operating_cycle_summary.json",
    }


def canonical_fail_nightly_progress_sources(runs_dir: Path) -> dict[str, Path]:
    base = Path(runs_dir)
    return {
        source: base.joinpath(*tuple(spec["path_parts"]))
        for source, spec in FAIL_NIGHTLY_PROGRESS_SOURCE_SPECS.items()
    }


def canonical_fail_nightly_remediation_source(runs_dir: Path) -> Path:
    base = Path(runs_dir)
    return base.joinpath(*tuple(FAIL_NIGHTLY_REMEDIATION_SOURCE_SPEC["path_parts"]))


def canonical_fail_nightly_transition_source(runs_dir: Path) -> Path:
    base = Path(runs_dir)
    return base.joinpath(*tuple(FAIL_NIGHTLY_TRANSITION_SOURCE_SPEC["path_parts"]))


def canonical_fail_nightly_integrity_source(runs_dir: Path) -> Path:
    base = Path(runs_dir)
    return base.joinpath(*tuple(FAIL_NIGHTLY_INTEGRITY_SOURCE_SPEC["path_parts"]))


def canonical_operating_cycle_source(runs_dir: Path) -> Path:
    base = Path(runs_dir)
    return base.joinpath(*tuple(OPERATING_CYCLE_SOURCE_SPEC["path_parts"]))


def canonical_combo_a_operating_cycle_source(runs_dir: Path) -> Path:
    base = Path(runs_dir)
    return base.joinpath(*tuple(COMBO_A_OPERATING_CYCLE_SOURCE_SPEC["path_parts"]))


def canonical_pilot_runtime_readiness_source(runs_dir: Path) -> Path:
    base = Path(runs_dir)
    return base.joinpath(*tuple(PILOT_RUNTIME_READINESS_SOURCE_SPEC["path_parts"]))


def canonical_pilot_runtime_latest_status_source(runs_dir: Path) -> Path:
    return Path(runs_dir) / "pilot-runtime" / PILOT_RUNTIME_STATUS_FILENAME


def canonical_history_roots(runs_dir: Path) -> dict[str, Path]:
    base = Path(runs_dir)
    return {
        source: base / str(spec["root_subdir"])
        for source, spec in HISTORY_SOURCE_SPECS.items()
    }


def load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"missing file: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"failed to parse JSON {path}: {exc}"
    if not isinstance(payload, dict):
        return None, f"json root must be object: {path}"
    return payload, None


def load_latest_pilot_runtime_status(
    pilot_runs_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    status_path = Path(pilot_runs_dir) / PILOT_RUNTIME_STATUS_FILENAME
    payload, load_error = load_json_object(status_path)
    if payload is None:
        if load_error is not None and not load_error.startswith("missing file:"):
            warnings.append(f"{status_path}: skipped ({load_error})")
        return None, warnings
    if str(payload.get("schema_version", "")).strip() != PILOT_RUNTIME_STATUS_SCHEMA:
        warnings.append(
            f"{status_path}: skipped (schema_version={payload.get('schema_version')!r} "
            f"expected={PILOT_RUNTIME_STATUS_SCHEMA!r})"
        )
        return None, warnings
    return payload, warnings


def _load_optional_contract_payload(
    source_name: str,
    path: Path,
    *,
    expected_schema_version: str,
) -> tuple[dict[str, Any] | None, str | None]:
    payload, load_error = load_json_object(path)
    if payload is None:
        return None, load_error
    observed_schema = str(payload.get("schema_version", "")).strip()
    if observed_schema != expected_schema_version:
        return None, (
            f"{source_name}: schema_version mismatch for {path} "
            f"(observed={observed_schema!r}, expected={expected_schema_version!r})"
        )
    return payload, None


def _nested_get(payload: dict[str, Any] | None, *keys: str) -> Any:
    if payload is None:
        return None
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _normalize_reason_codes(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _unique_strings(*values: Any) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        for item in _normalize_reason_codes(value):
            if item in seen:
                continue
            seen.add(item)
            items.append(item)
    return items


def load_fail_nightly_progress_snapshot(
    runs_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    source_paths = canonical_fail_nightly_progress_sources(runs_dir)
    warnings: list[str] = []
    missing_sources: list[str] = []
    payloads: dict[str, dict[str, Any]] = {}

    for source_name, path in source_paths.items():
        spec = FAIL_NIGHTLY_PROGRESS_SOURCE_SPECS[source_name]
        expected_schema = str(spec["schema_version"])
        payload, load_error = _load_optional_contract_payload(
            source_name,
            path,
            expected_schema_version=expected_schema,
        )
        if payload is None:
            if load_error is not None and load_error.startswith("missing file:"):
                missing_sources.append(source_name)
            elif load_error is not None:
                warnings.append(load_error)
            continue
        payloads[source_name] = payload

    if not payloads:
        return None, warnings

    readiness_payload = payloads.get("readiness")
    governance_payload = payloads.get("governance")
    progress_payload = payloads.get("progress")

    target_policy = _coalesce(
        _nested_get(progress_payload, "recommendation", "target_critical_policy"),
        _nested_get(governance_payload, "recommendation", "target_critical_policy"),
        _nested_get(readiness_payload, "recommendation", "target_critical_policy"),
    )
    reason_codes = _normalize_reason_codes(
        _coalesce(
            _nested_get(progress_payload, "recommendation", "reason_codes"),
            _nested_get(governance_payload, "recommendation", "reason_codes"),
            _nested_get(readiness_payload, "recommendation", "reason_codes"),
        )
    )

    snapshot: dict[str, Any] = {
        "schema_version": "streamlit_gateway_fail_nightly_snapshot_v1",
        "readiness_status": _nested_get(readiness_payload, "readiness_status"),
        "latest_ready_streak": _coalesce(
            _nested_get(progress_payload, "observed", "readiness", "latest_ready_streak"),
            _nested_get(governance_payload, "observed", "latest_ready_streak"),
        ),
        "decision_status": _coalesce(
            _nested_get(progress_payload, "decision_status"),
            _nested_get(governance_payload, "decision_status"),
        ),
        "remaining_for_window": _nested_get(progress_payload, "observed", "readiness", "remaining_for_window"),
        "remaining_for_streak": _nested_get(progress_payload, "observed", "readiness", "remaining_for_streak"),
        "target_critical_policy": target_policy,
        "reason_codes": reason_codes,
        "available_sources": sorted(payloads.keys()),
        "missing_sources": sorted(missing_sources),
        "source_paths": {name: str(path) for name, path in source_paths.items()},
    }
    return snapshot, warnings


def load_fail_nightly_remediation_snapshot(
    runs_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    path = canonical_fail_nightly_remediation_source(runs_dir)
    payload, load_error = _load_optional_contract_payload(
        "remediation",
        path,
        expected_schema_version=str(FAIL_NIGHTLY_REMEDIATION_SOURCE_SPEC["schema_version"]),
    )
    if payload is None:
        if load_error is not None and load_error.startswith("missing file:"):
            return None, []
        return None, [] if load_error is None else [load_error]
    return payload, []


def load_fail_nightly_transition_snapshot(
    runs_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    path = canonical_fail_nightly_transition_source(runs_dir)
    payload, load_error = _load_optional_contract_payload(
        "transition",
        path,
        expected_schema_version=str(FAIL_NIGHTLY_TRANSITION_SOURCE_SPEC["schema_version"]),
    )
    if payload is None:
        if load_error is not None and load_error.startswith("missing file:"):
            return None, []
        return None, [] if load_error is None else [load_error]

    observed = payload.get("observed")
    observed = observed if isinstance(observed, dict) else {}
    recommendation = payload.get("recommendation")
    recommendation = recommendation if isinstance(recommendation, dict) else {}
    latest = payload.get("latest")
    latest = latest if isinstance(latest, dict) else {}
    paths_payload = payload.get("paths")
    paths_payload = paths_payload if isinstance(paths_payload, dict) else {}
    snapshot = {
        "schema_version": str(payload.get("schema_version")),
        "status": payload.get("status"),
        "decision_status": payload.get("decision_status"),
        "allow_switch": payload.get("allow_switch"),
        "checked_at_utc": payload.get("checked_at_utc"),
        "policy": payload.get("policy"),
        "observed": observed,
        "latest": latest,
        "recommendation": recommendation,
        "paths": {
            "summary_json": _coalesce(paths_payload.get("summary_json"), str(path)),
            "history_summary_json": paths_payload.get("history_summary_json"),
        },
        "source_path": str(path),
    }
    return snapshot, []


def load_fail_nightly_integrity_snapshot(
    runs_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    path = canonical_fail_nightly_integrity_source(runs_dir)
    payload, load_error = _load_optional_contract_payload(
        "integrity",
        path,
        expected_schema_version=str(FAIL_NIGHTLY_INTEGRITY_SOURCE_SPEC["schema_version"]),
    )
    if payload is None:
        if load_error is not None and load_error.startswith("missing file:"):
            return None, []
        return None, [] if load_error is None else [load_error]
    return payload, []


def load_operating_cycle_snapshot(
    runs_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    path = canonical_operating_cycle_source(runs_dir)
    payload, load_error = _load_optional_contract_payload(
        "operating_cycle",
        path,
        expected_schema_version=str(OPERATING_CYCLE_SOURCE_SPEC["schema_version"]),
    )
    if payload is None:
        if load_error is not None and load_error.startswith("missing file:"):
            return None, []
        return None, [] if load_error is None else [load_error]

    cycle = payload.get("cycle")
    cycle = cycle if isinstance(cycle, dict) else {}
    triage = payload.get("triage")
    triage = triage if isinstance(triage, dict) else {}
    interpretation = payload.get("interpretation")
    interpretation = interpretation if isinstance(interpretation, dict) else {}
    paths_payload = payload.get("paths")
    paths_payload = paths_payload if isinstance(paths_payload, dict) else {}

    snapshot = {
        "schema_version": str(payload.get("schema_version")),
        "status": payload.get("status"),
        "checked_at_utc": payload.get("checked_at_utc"),
        "policy": payload.get("policy"),
        "effective_policy": payload.get("effective_policy"),
        "promotion_state": payload.get("promotion_state"),
        "enforcement_surface": payload.get("enforcement_surface"),
        "blocking_reason_codes": _normalize_reason_codes(payload.get("blocking_reason_codes")),
        "recommended_actions": payload.get("recommended_actions")
        if isinstance(payload.get("recommended_actions"), list)
        else [],
        "next_review_at_utc": payload.get("next_review_at_utc"),
        "profile_scope": payload.get("profile_scope"),
        "actionable_message": payload.get("actionable_message"),
        "cycle": cycle,
        "triage": triage,
        "interpretation": interpretation,
        "paths": {
            "summary_json": _coalesce(paths_payload.get("summary_json"), str(path)),
            "history_summary_json": paths_payload.get("history_summary_json"),
            "brief_md": paths_payload.get("brief_md"),
            "history_brief_md": paths_payload.get("history_brief_md"),
        },
        "source_path": str(path),
    }
    return snapshot, []


def load_combo_a_operating_cycle_snapshot(
    runs_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    path = canonical_combo_a_operating_cycle_source(runs_dir)
    payload, load_error = _load_optional_contract_payload(
        "combo_a_operating_cycle",
        path,
        expected_schema_version=str(COMBO_A_OPERATING_CYCLE_SOURCE_SPEC["schema_version"]),
    )
    if payload is None:
        if load_error is not None and load_error.startswith("missing file:"):
            return None, []
        return None, [] if load_error is None else [load_error]

    live_readiness = payload.get("live_readiness")
    live_readiness = live_readiness if isinstance(live_readiness, dict) else {}
    paths_payload = payload.get("paths")
    paths_payload = paths_payload if isinstance(paths_payload, dict) else {}
    snapshot = {
        "schema_version": str(payload.get("schema_version")),
        "status": payload.get("status"),
        "checked_at_utc": payload.get("checked_at_utc"),
        "scenario": payload.get("scenario"),
        "policy": payload.get("policy"),
        "effective_policy": payload.get("effective_policy"),
        "promotion_state": payload.get("promotion_state"),
        "enforcement_surface": payload.get("enforcement_surface"),
        "blocking_reason_codes": _normalize_reason_codes(payload.get("blocking_reason_codes")),
        "recommended_actions": payload.get("recommended_actions")
        if isinstance(payload.get("recommended_actions"), list)
        else [],
        "next_review_at_utc": payload.get("next_review_at_utc"),
        "profile_scope": payload.get("profile_scope"),
        "availability_status": payload.get("availability_status"),
        "actionable_message": payload.get("actionable_message"),
        "live_readiness": live_readiness,
        "sources": payload.get("sources") if isinstance(payload.get("sources"), dict) else {},
        "paths": {
            "summary_json": _coalesce(paths_payload.get("summary_json"), str(path)),
            "history_summary_json": paths_payload.get("history_summary_json"),
            "summary_md": paths_payload.get("summary_md"),
            "history_summary_md": paths_payload.get("history_summary_md"),
        },
        "source_path": str(path),
    }
    return snapshot, []


def load_pilot_runtime_readiness_snapshot(
    runs_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    path = canonical_pilot_runtime_readiness_source(runs_dir)
    payload, load_error = _load_optional_contract_payload(
        "pilot_runtime_readiness",
        path,
        expected_schema_version=str(PILOT_RUNTIME_READINESS_SOURCE_SPEC["schema_version"]),
    )
    if payload is None:
        if load_error is not None and load_error.startswith("missing file:"):
            return None, []
        return None, [] if load_error is None else [load_error]

    paths_payload = payload.get("paths")
    paths_payload = paths_payload if isinstance(paths_payload, dict) else {}
    snapshot = {
        "schema_version": str(payload.get("schema_version")),
        "status": payload.get("status"),
        "checked_at_utc": payload.get("checked_at_utc"),
        "readiness_status": payload.get("readiness_status"),
        "actionable_message": payload.get("actionable_message"),
        "blocking_reason_codes": _normalize_reason_codes(payload.get("blocking_reason_codes")),
        "next_step_code": payload.get("next_step_code"),
        "next_step": payload.get("next_step"),
        "sources": payload.get("sources") if isinstance(payload.get("sources"), dict) else {},
        "evidence": payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {},
        "paths": {
            "summary_json": _coalesce(paths_payload.get("summary_json"), str(path)),
            "history_summary_json": paths_payload.get("history_summary_json"),
            "summary_md": paths_payload.get("summary_md"),
            "history_summary_md": paths_payload.get("history_summary_md"),
        },
        "source_path": str(path),
    }
    return snapshot, []


def build_operator_combo_a_profile_summary(
    *,
    combo_a_readiness: dict[str, Any] | None,
    combo_a_operating_cycle_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    readiness = combo_a_readiness if isinstance(combo_a_readiness, dict) else {}
    operating_cycle = (
        combo_a_operating_cycle_snapshot if isinstance(combo_a_operating_cycle_snapshot, dict) else {}
    )
    live_readiness = operating_cycle.get("live_readiness")
    live_readiness = live_readiness if isinstance(live_readiness, dict) else {}
    services = readiness.get("services")
    services = services if isinstance(services, dict) else {}
    if not services:
        services = live_readiness.get("services")
        services = services if isinstance(services, dict) else {}

    warnings = _unique_strings(
        readiness.get("warnings"),
        [str(item) for item in operating_cycle.get("warnings", [])]
        if isinstance(operating_cycle.get("warnings"), list)
        else [],
    )
    return {
        "profile": COMBO_A_PROFILE,
        "availability_status": _coalesce(
            readiness.get("availability_status"),
            operating_cycle.get("availability_status"),
            live_readiness.get("availability_status"),
            "unknown",
        ),
        "available": _coalesce(
            readiness.get("available"),
            live_readiness.get("available"),
            False,
        ),
        "missing_config": readiness.get("missing_config", []),
        "warnings": warnings,
        "services": services,
        "effective_policy": operating_cycle.get("effective_policy"),
        "promotion_state": operating_cycle.get("promotion_state"),
        "blocking_reason_codes": _normalize_reason_codes(operating_cycle.get("blocking_reason_codes")),
        "recommended_actions": operating_cycle.get("recommended_actions")
        if isinstance(operating_cycle.get("recommended_actions"), list)
        else [],
        "next_review_at_utc": operating_cycle.get("next_review_at_utc"),
        "operating_cycle_path": _nested_get(operating_cycle, "paths", "summary_json"),
        "actionable_message": operating_cycle.get("actionable_message"),
    }


def _iter_operator_startup_run_dirs(operator_runs_dir: Path) -> list[Path]:
    if not operator_runs_dir.is_dir():
        return []
    candidates = [
        child
        for child in operator_runs_dir.iterdir()
        if child.is_dir()
        and "start-operator-product" in child.name
        and (child / "run.json").is_file()
    ]
    return sorted(candidates, key=lambda path: path.name, reverse=True)


def _normalize_startup_session_state(
    session_state: Any,
    child_processes: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    if not isinstance(session_state, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for service_name, raw_entry in session_state.items():
        entry = raw_entry if isinstance(raw_entry, dict) else {}
        child_process = child_processes.get(service_name)
        child_process = child_process if isinstance(child_process, dict) else {}
        last_probe = entry.get("last_probe")
        last_probe = last_probe if isinstance(last_probe, dict) else None
        normalized[str(service_name)] = {
            "service_name": str(service_name),
            "managed": bool(entry.get("managed", False)),
            "status": entry.get("status"),
            "configured": entry.get("configured"),
            "effective_url": _coalesce(entry.get("effective_url"), entry.get("url")),
            "runs_dir": entry.get("runs_dir"),
            "log_path": entry.get("log_path"),
            "pid": _coalesce(entry.get("pid"), child_process.get("pid")),
            "last_probe": last_probe,
            "error": entry.get("error"),
            "started_at_utc": entry.get("started_at_utc"),
            "finished_at_utc": entry.get("finished_at_utc"),
            "last_event": entry.get("last_event"),
        }
    return normalized


def _ordered_startup_service_names(session_state: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(session_state, Mapping):
        return []
    preferred_order = (
        "gateway",
        "streamlit",
        "voice_runtime_service",
        "tts_runtime_service",
        "pilot_runtime",
        "qdrant",
        "neo4j",
    )
    ordered_services: list[str] = [name for name in preferred_order if name in session_state]
    ordered_services.extend(
        sorted(str(name) for name in session_state.keys() if str(name) not in preferred_order)
    )
    return ordered_services


def _summarize_startup_service(service_name: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    probe = entry.get("last_probe")
    probe = probe if isinstance(probe, Mapping) else {}
    status = str(entry.get("status", "")).strip().lower()
    probe_status = str(probe.get("status", "")).strip().lower()
    managed = bool(entry.get("managed", False))
    configured = bool(entry.get("configured"))
    issue = _coalesce(entry.get("error"), probe.get("error"))
    state_class = "unknown"
    attention_kind: str | None = None

    if not configured or status == "not_configured":
        state_class = "not_configured"
    elif status in {"error", "failed", "fail", "degraded"}:
        state_class = "attention"
        attention_kind = "service_error"
        issue = issue or f"status={status}"
    elif probe_status in {"error", "failed", "fail", "degraded"}:
        state_class = "attention"
        attention_kind = "probe_error"
        issue = issue or f"last_probe.status={probe_status}"
    elif status in {"pending", "starting", "not_started"}:
        state_class = "attention"
        attention_kind = "pending"
        issue = issue or f"status={status}"
    elif status == "stopped" and managed:
        state_class = "attention"
        attention_kind = "stopped"
        issue = issue or "status=stopped"
    elif status == "external":
        state_class = "attention"
        attention_kind = "external_unverified"
        issue = issue or "configured external service has not been probed yet"
    elif status in {"running", "ok"} or probe_status == "ok":
        state_class = "healthy"
    elif issue:
        state_class = "attention"
        attention_kind = "unknown"

    return {
        "service_name": service_name,
        "managed": managed,
        "configured": configured,
        "status": entry.get("status"),
        "last_probe_status": probe.get("status"),
        "effective_url": entry.get("effective_url"),
        "log_path": entry.get("log_path"),
        "state_class": state_class,
        "attention_kind": attention_kind,
        "issue": issue,
    }


def load_latest_operator_startup_status(
    operator_runs_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    root = Path(operator_runs_dir)
    warnings: list[str] = []
    for run_dir in _iter_operator_startup_run_dirs(root):
        run_json_path = run_dir / "run.json"
        payload, load_error = load_json_object(run_json_path)
        if payload is None:
            if load_error is not None:
                warnings.append(f"{run_json_path}: skipped ({load_error})")
            continue
        if str(payload.get("schema_version", "")).strip() != OPERATOR_PRODUCT_STARTUP_SCHEMA:
            warnings.append(
                f"{run_json_path}: skipped (schema_version={payload.get('schema_version')!r} "
                f"expected={OPERATOR_PRODUCT_STARTUP_SCHEMA!r})"
            )
            continue
        if str(payload.get("mode", "")).strip() != "start_operator_product":
            warnings.append(
                f"{run_json_path}: skipped (mode={payload.get('mode')!r} expected='start_operator_product')"
            )
            continue

        paths_payload = payload.get("paths")
        paths_payload = paths_payload if isinstance(paths_payload, dict) else {}
        child_processes = payload.get("child_processes")
        child_processes = child_processes if isinstance(child_processes, dict) else {}
        checkpoints = payload.get("startup_checkpoints")
        checkpoints = checkpoints if isinstance(checkpoints, list) else []

        summary = {
            "schema_version": "operator_product_startup_status_v1",
            "status": payload.get("status"),
            "profile": payload.get("profile"),
            "timestamp_utc": payload.get("timestamp_utc"),
            "started_at_utc": payload.get("started_at_utc"),
            "stopped_at_utc": payload.get("stopped_at_utc"),
            "finished_at_utc": payload.get("finished_at_utc"),
            "error": payload.get("error"),
            "gateway_url": payload.get("gateway_url"),
            "streamlit_url": payload.get("streamlit_url"),
            "effective_urls": payload.get("effective_urls"),
            "artifact_roots": payload.get("artifact_roots"),
            "managed_processes": payload.get("managed_processes"),
            "session_state": _normalize_startup_session_state(
                payload.get("session_state"),
                child_processes,
            ),
            "child_processes": child_processes,
            "checkpoint_count": len(checkpoints),
            "last_checkpoint": payload.get("last_checkpoint"),
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "startup_plan_json": paths_payload.get("startup_plan_json"),
                "gateway_log": paths_payload.get("gateway_log"),
                "streamlit_log": paths_payload.get("streamlit_log"),
                "voice_runtime_service_log": paths_payload.get("voice_runtime_service_log"),
                "tts_runtime_service_log": paths_payload.get("tts_runtime_service_log"),
                "pilot_runtime_log": paths_payload.get("pilot_runtime_log"),
            },
        }
        summary["diagnostics"] = _build_startup_diagnostics(summary)
        return summary, warnings
    return None, warnings


def _find_startup_service_probe_issue(
    session_state: Mapping[str, Any] | None,
) -> str | None:
    if not isinstance(session_state, Mapping):
        return None

    for service_name in _ordered_startup_service_names(session_state):
        entry = session_state.get(service_name)
        if not isinstance(entry, Mapping):
            continue
        summary = _summarize_startup_service(service_name, entry)
        if summary.get("attention_kind") in {"service_error", "probe_error", "stopped", "unknown"}:
            issue = summary.get("issue") or f"status={summary.get('status')}"
            return f"{service_name}: {issue}"
    return None


def _build_startup_service_rollup(
    session_state: Mapping[str, Any] | None,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    rollup = {
        "total_services": 0,
        "configured_services": 0,
        "managed_services": 0,
        "healthy_services": 0,
        "attention_services": 0,
        "not_configured_services": 0,
        "unknown_services": 0,
    }
    attention_services: list[dict[str, Any]] = []
    if not isinstance(session_state, Mapping):
        return rollup, attention_services

    for service_name in _ordered_startup_service_names(session_state):
        entry = session_state.get(service_name)
        if not isinstance(entry, Mapping):
            continue
        summary = _summarize_startup_service(service_name, entry)
        rollup["total_services"] += 1
        if summary["configured"]:
            rollup["configured_services"] += 1
        if summary["managed"]:
            rollup["managed_services"] += 1

        state_class = str(summary["state_class"])
        if state_class == "healthy":
            rollup["healthy_services"] += 1
        elif state_class == "attention":
            rollup["attention_services"] += 1
            attention_services.append(summary)
        elif state_class == "not_configured":
            rollup["not_configured_services"] += 1
        else:
            rollup["unknown_services"] += 1
    return rollup, attention_services


def _build_startup_next_step(
    attention_services: list[dict[str, Any]],
) -> tuple[str, str | None]:
    if not attention_services:
        return "none", None

    priority_order = {
        "service_error": 0,
        "probe_error": 0,
        "stopped": 1,
        "unknown": 1,
        "external_unverified": 2,
        "pending": 3,
        None: 4,
    }
    next_item = min(
        attention_services,
        key=lambda item: (
            priority_order.get(item.get("attention_kind"), 4),
            str(item.get("service_name", "")),
        ),
    )
    service_name = str(next_item.get("service_name", "service")).strip() or "service"
    attention_kind = next_item.get("attention_kind")
    log_path = next_item.get("log_path")
    if attention_kind == "pending":
        return "wait_for_startup", f"Wait for {service_name} startup to finish and refresh the operator snapshot."
    if next_item.get("managed"):
        if isinstance(log_path, str) and log_path.strip():
            return "inspect_managed_log", f"Inspect {service_name} log at {log_path}."
        return "inspect_managed_service", f"Inspect managed service {service_name} startup state."
    if attention_kind in {"service_error", "probe_error", "external_unverified", "unknown"}:
        return "check_service_connectivity", f"Check connectivity and credentials for {service_name}."
    return "refresh_operator_snapshot", "Refresh the operator snapshot after the stack settles."


def _build_startup_diagnostics(
    startup_snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(startup_snapshot, Mapping):
        return {
            "overall_state": "not_available",
            "primary_issue": "startup_artifact_not_found",
            "service_rollup": {
                "total_services": 0,
                "configured_services": 0,
                "managed_services": 0,
                "healthy_services": 0,
                "attention_services": 0,
                "not_configured_services": 0,
                "unknown_services": 0,
            },
            "attention_services": [],
            "next_step_code": "launch_operator_product",
            "next_step": "Launch the canonical stack with `python scripts/start_operator_product.py --runs-dir runs`.",
        }

    status = str(startup_snapshot.get("status", "")).strip().lower()
    snapshot_error = startup_snapshot.get("error")
    snapshot_error = snapshot_error.strip() if isinstance(snapshot_error, str) else None
    last_checkpoint = startup_snapshot.get("last_checkpoint")
    last_checkpoint = last_checkpoint if isinstance(last_checkpoint, Mapping) else {}
    checkpoint_status = str(last_checkpoint.get("status", "")).strip().lower()
    failing_checkpoint = checkpoint_status in {"error", "failed", "fail", "degraded"}
    session_state = startup_snapshot.get("session_state")
    service_issue = _find_startup_service_probe_issue(session_state)
    service_rollup, attention_services = _build_startup_service_rollup(session_state)
    next_step_code, next_step = _build_startup_next_step(attention_services)

    primary_issue: str | None = None
    if snapshot_error:
        primary_issue = snapshot_error
    elif failing_checkpoint:
        stage = str(last_checkpoint.get("stage") or "checkpoint").strip()
        message = str(last_checkpoint.get("message", "")).strip()
        if message:
            primary_issue = f"{stage}: {checkpoint_status}: {message}"
        else:
            primary_issue = f"{stage}: {checkpoint_status}"
    elif service_issue:
        primary_issue = service_issue

    if status in {"error", "failed", "fail", "degraded"} or primary_issue is not None:
        overall_state = "degraded"
    elif status in {"running", "ok"}:
        overall_state = "healthy"
    elif status == "stopped":
        overall_state = "stopped"
    elif status in {"not_available", "missing"}:
        overall_state = "not_available"
    else:
        overall_state = "unknown"

    return {
        "overall_state": overall_state,
        "primary_issue": primary_issue,
        "service_rollup": service_rollup,
        "attention_services": attention_services,
        "next_step_code": next_step_code,
        "next_step": next_step,
    }


def _attach_startup_diagnostics(
    startup_snapshot: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(startup_snapshot, dict):
        return startup_snapshot
    enriched = dict(startup_snapshot)
    enriched["diagnostics"] = _build_startup_diagnostics(startup_snapshot)
    return enriched


def _summarize_tts_engine(tts_payload: Mapping[str, Any] | None) -> str | None:
    if not isinstance(tts_payload, Mapping):
        return None
    chunk_engines = tts_payload.get("chunk_engines")
    if isinstance(chunk_engines, list):
        normalized = [str(item).strip() for item in chunk_engines if str(item).strip()]
        if normalized:
            return normalized[0]
    completed_event = tts_payload.get("completed_event")
    if isinstance(completed_event, Mapping):
        engine_name = str(completed_event.get("engine", "")).strip()
        if engine_name:
            return engine_name
    return None


def _load_pilot_last_turn_summary(
    pilot_status: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(pilot_status, Mapping):
        return None
    turn_json = _nested_get(pilot_status, "paths", "last_turn_json")
    if not isinstance(turn_json, str) or not turn_json.strip():
        return None
    payload, _load_error = load_json_object(Path(turn_json))
    if payload is None:
        return None
    if str(payload.get("schema_version", "")).strip() != PILOT_TURN_SCHEMA:
        return None
    answer_text = str(payload.get("answer_text", "")).strip()
    return {
        "turn_id": payload.get("turn_id"),
        "status": payload.get("status"),
        "timestamp_utc": payload.get("timestamp_utc"),
        "completed_at_utc": payload.get("completed_at_utc"),
        "degraded_flags": payload.get("degraded_flags", []),
        "degraded_services": payload.get("degraded_services", []),
        "answer_preview": answer_text[:240] if answer_text else "",
        "turn_json": turn_json,
        "screenshot_png": _nested_get(payload, "paths", "screenshot_png"),
        "session_probe_json": _nested_get(payload, "paths", "session_probe_json"),
        "live_hud_state_json": _nested_get(payload, "paths", "live_hud_state_json"),
        "tts_audio_wav": _nested_get(payload, "paths", "tts_audio_wav"),
        "answer_language": payload.get("answer_language"),
        "reply_mode": payload.get("reply_mode"),
        "transcript_quality_status": _nested_get(payload, "transcript_quality", "status"),
        "transcript_quality_reason_codes": _normalize_reason_codes(
            _nested_get(payload, "transcript_quality", "reason_codes")
        ),
        "vision_provider": _nested_get(payload, "vision", "provider"),
        "grounded_reply_provider": _nested_get(payload, "grounded_reply", "provider"),
        "tts_engine": _summarize_tts_engine(_nested_get(payload, "tts")),
        "session_status": _nested_get(payload, "session", "status"),
        "session_window_found": _nested_get(payload, "session", "window_found"),
        "session_atm10_probable": _nested_get(payload, "session", "atm10_probable"),
        "session_foreground": _nested_get(payload, "session", "foreground"),
        "session_process_name": _nested_get(payload, "session", "process_name"),
        "session_window_title": _nested_get(payload, "session", "window_title"),
        "session_reason_codes": _normalize_reason_codes(_nested_get(payload, "session", "reason_codes")),
        "hud_state_status": _nested_get(payload, "hud_state", "status"),
        "hud_line_count": _nested_get(payload, "hud_state", "hud_line_count"),
        "quest_update_count": _nested_get(payload, "hud_state", "quest_update_count"),
        "has_player_state": _nested_get(payload, "hud_state", "has_player_state"),
        "hud_text_preview": _nested_get(payload, "hud_state", "text_preview"),
        "hud_reason_codes": _normalize_reason_codes(_nested_get(payload, "hud_state", "reason_codes")),
    }


def _coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _build_tts_runtime_diagnostics(
    tts_health: Mapping[str, Any] | None,
    last_turn_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = _nested_get(tts_health, "payload")
    payload = payload if isinstance(payload, Mapping) else {}
    preferred_tts_engine_value = payload.get("preferred_tts_engine")
    preferred_tts_engine = (
        str(preferred_tts_engine_value).strip()
        if preferred_tts_engine_value is not None
        else ""
    ) or None
    piper_available = _coerce_optional_bool(payload.get("piper_available"))
    piper_prewarm_ok = _coerce_optional_bool(payload.get("piper_prewarm_ok"))
    base_tts_degraded_reason_value = payload.get("tts_degraded_reason")
    base_tts_degraded_reason = (
        str(base_tts_degraded_reason_value).strip()
        if base_tts_degraded_reason_value is not None
        else ""
    ) or None
    active_tts_engine_last_turn = None
    if isinstance(last_turn_summary, Mapping):
        active_tts_engine_last_turn = str(last_turn_summary.get("tts_engine", "")).strip() or None

    tts_degraded_reason = base_tts_degraded_reason
    if (
        preferred_tts_engine
        and active_tts_engine_last_turn
        and preferred_tts_engine != active_tts_engine_last_turn
    ):
        fallback_reason = (
            f"last_turn_used_{active_tts_engine_last_turn}_instead_of_{preferred_tts_engine}"
        )
        tts_degraded_reason = (
            f"{base_tts_degraded_reason}; {fallback_reason}"
            if base_tts_degraded_reason
            else fallback_reason
        )
    return {
        "preferred_tts_engine": preferred_tts_engine,
        "active_tts_engine_last_turn": active_tts_engine_last_turn,
        "piper_available": piper_available,
        "piper_prewarm_ok": piper_prewarm_ok,
        "tts_degraded_reason": tts_degraded_reason,
    }


def _build_pilot_runtime_summary(
    pilot_status: Mapping[str, Any] | None,
    *,
    pilot_runs_dir: Path | None,
) -> dict[str, Any]:
    if not isinstance(pilot_status, Mapping):
        return {
            "status": "not_available",
            "state": "not_available",
            "last_turn_id": None,
            "degraded_services": [],
            "last_error": None,
            "input_device_index": None,
            "vlm_provider": None,
            "text_provider": None,
            "preferred_tts_engine": None,
            "active_tts_engine_last_turn": None,
            "piper_available": None,
            "piper_prewarm_ok": None,
            "tts_degraded_reason": None,
            "provider_init": {},
            "paths": {
                "pilot_runs_dir": None if pilot_runs_dir is None else str(pilot_runs_dir),
                "latest_status_json": None if pilot_runs_dir is None else str(Path(pilot_runs_dir) / PILOT_RUNTIME_STATUS_FILENAME),
            },
        }
    return {
        "status": pilot_status.get("status"),
        "state": pilot_status.get("state"),
        "last_turn_id": pilot_status.get("last_turn_id"),
        "last_turn_started_at_utc": pilot_status.get("last_turn_started_at_utc"),
        "last_turn_completed_at_utc": pilot_status.get("last_turn_completed_at_utc"),
        "degraded_services": pilot_status.get("degraded_services", []),
        "last_error": pilot_status.get("last_error"),
        "hotkey": pilot_status.get("hotkey"),
        "input_device_index": _nested_get(pilot_status, "effective_config", "input_device_index"),
        "asr_language": _nested_get(pilot_status, "effective_config", "asr_language"),
        "asr_max_new_tokens": _nested_get(pilot_status, "effective_config", "asr_max_new_tokens"),
        "asr_warmup": _nested_get(pilot_status, "effective_config", "asr_warmup"),
        "vlm_provider": _nested_get(pilot_status, "effective_config", "vlm_provider"),
        "text_provider": _nested_get(pilot_status, "effective_config", "text_provider"),
        "pilot_vlm_max_new_tokens": _nested_get(pilot_status, "effective_config", "pilot_vlm_max_new_tokens"),
        "pilot_text_max_new_tokens": _nested_get(pilot_status, "effective_config", "pilot_text_max_new_tokens"),
        "pilot_hybrid_timeout_sec": _nested_get(pilot_status, "effective_config", "pilot_hybrid_timeout_sec"),
        "preferred_tts_engine": None,
        "active_tts_engine_last_turn": None,
        "piper_available": None,
        "piper_prewarm_ok": None,
        "tts_degraded_reason": None,
        "provider_init": (
            dict(pilot_status.get("provider_init", {}))
            if isinstance(pilot_status.get("provider_init"), Mapping)
            else {}
        ),
        "latency_summary": pilot_status.get("latency_summary"),
        "paths": {
            "pilot_runs_dir": None if pilot_runs_dir is None else str(pilot_runs_dir),
            **(
                dict(pilot_status.get("paths", {}))
                if isinstance(pilot_status.get("paths"), Mapping)
                else {}
            ),
        },
    }


def _build_governance_diagnostics(
    governance_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(governance_summary, Mapping):
        return {
            "top_blocker": "none",
            "next_safe_action": None,
        }
    blocking_reason_codes = _normalize_reason_codes(governance_summary.get("blocking_reason_codes"))
    recommended_actions = governance_summary.get("recommended_actions")
    next_safe_action: str | None = None
    if isinstance(recommended_actions, list):
        for item in recommended_actions:
            if not isinstance(item, Mapping):
                continue
            action_key = str(item.get("action_key", "")).strip()
            if action_key:
                next_safe_action = action_key
                break
    return {
        "top_blocker": blocking_reason_codes[0] if blocking_reason_codes else "none",
        "next_safe_action": next_safe_action,
    }


def _attach_governance_diagnostics(
    governance_summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(governance_summary, dict):
        return governance_summary
    enriched = dict(governance_summary)
    enriched["diagnostics"] = _build_governance_diagnostics(governance_summary)
    return enriched


def build_operator_governance_summary(
    *,
    progress_snapshot: dict[str, Any] | None,
    transition_snapshot: dict[str, Any] | None,
    remediation_snapshot: dict[str, Any] | None,
    integrity_snapshot: dict[str, Any] | None,
    operating_cycle_snapshot: dict[str, Any] | None,
) -> dict[str, Any] | None:
    available_sources: list[str] = []
    missing_sources: list[str] = []
    source_paths: dict[str, Any] = {}

    for source_name, snapshot in (
        ("progress", progress_snapshot),
        ("transition", transition_snapshot),
        ("remediation", remediation_snapshot),
        ("integrity", integrity_snapshot),
        ("operating_cycle", operating_cycle_snapshot),
    ):
        if snapshot is None:
            missing_sources.append(source_name)
            continue
        available_sources.append(source_name)
        if source_name == "progress":
            source_paths[source_name] = snapshot.get("source_paths")
            continue
        paths_payload = snapshot.get("paths")
        paths_payload = paths_payload if isinstance(paths_payload, dict) else {}
        source_paths[source_name] = _coalesce(
            paths_payload.get("summary_json"),
            snapshot.get("source_path"),
        )

    if not available_sources:
        return None

    operating_cycle_triage = _nested_get(operating_cycle_snapshot, "triage")
    operating_cycle_triage = operating_cycle_triage if isinstance(operating_cycle_triage, dict) else {}
    operating_cycle_interpretation = _nested_get(operating_cycle_snapshot, "interpretation")
    operating_cycle_interpretation = (
        operating_cycle_interpretation if isinstance(operating_cycle_interpretation, dict) else {}
    )
    transition_recommendation = _nested_get(transition_snapshot, "recommendation")
    transition_recommendation = (
        transition_recommendation if isinstance(transition_recommendation, dict) else {}
    )
    integrity_decision = _nested_get(integrity_snapshot, "decision")
    integrity_decision = integrity_decision if isinstance(integrity_decision, dict) else {}
    remediation_candidate_items = _nested_get(remediation_snapshot, "candidate_items")
    remediation_candidate_items = (
        remediation_candidate_items if isinstance(remediation_candidate_items, list) else []
    )

    degraded_sources = sorted(
        set(_normalize_reason_codes(_nested_get(progress_snapshot, "missing_sources"))) | set(missing_sources)
    )
    recommended_policy = _coalesce(
        transition_recommendation.get("target_critical_policy"),
        _nested_get(progress_snapshot, "target_critical_policy"),
    )
    transition_allow_switch = bool(_nested_get(transition_snapshot, "allow_switch"))
    integrity_status = integrity_decision.get("integrity_status")
    telemetry_repair_required = bool(operating_cycle_interpretation.get("telemetry_repair_required"))
    remediation_backlog_primary = bool(operating_cycle_interpretation.get("remediation_backlog_primary"))
    blocked_manual_gate = bool(operating_cycle_interpretation.get("blocked_manual_gate"))
    candidate_item_count = _coalesce(
        operating_cycle_triage.get("candidate_item_count"),
        len(remediation_candidate_items),
        0,
    )
    synthetic_blocking_reason_codes: list[str] = []
    if telemetry_repair_required or str(integrity_status).strip() == "attention":
        synthetic_blocking_reason_codes.append("telemetry_repair_required")
    if remediation_backlog_primary or int(candidate_item_count) > 0:
        synthetic_blocking_reason_codes.append("remediation_backlog_pending")
    if degraded_sources:
        synthetic_blocking_reason_codes.append("required_sources_not_fresh")

    effective_policy = _coalesce(
        _nested_get(operating_cycle_snapshot, "effective_policy"),
        "fail_nightly"
        if transition_allow_switch and not synthetic_blocking_reason_codes
        else "signal_only",
    )
    promotion_state = _coalesce(
        _nested_get(operating_cycle_snapshot, "promotion_state"),
        (
            "eligible"
            if transition_allow_switch and not synthetic_blocking_reason_codes
            else ("blocked" if synthetic_blocking_reason_codes else "hold")
        ),
    )
    blocking_reason_codes = _unique_strings(
        _nested_get(operating_cycle_snapshot, "blocking_reason_codes"),
        synthetic_blocking_reason_codes,
        transition_recommendation.get("reason_codes"),
        _nested_get(progress_snapshot, "reason_codes"),
        _nested_get(remediation_snapshot, "reason_codes"),
        integrity_decision.get("reason_codes"),
    )
    recommended_actions = _nested_get(operating_cycle_snapshot, "recommended_actions")
    if not isinstance(recommended_actions, list):
        recommended_actions = []
    if not recommended_actions and promotion_state != "eligible":
        recommended_actions = [
            {
                "action_key": "gateway_sla_operating_cycle_smoke",
                "label": "Gateway SLA operating cycle smoke",
                "reason": "Refresh the promoted-policy decision surface after the next nightly evidence update.",
                "surface": "gateway_safe_action",
            }
        ]
    next_review_at_utc = _coalesce(
        _nested_get(operating_cycle_snapshot, "next_review_at_utc"),
        _nested_get(operating_cycle_snapshot, "cycle", "next_accounted_dispatch_at_utc"),
        operating_cycle_triage.get("earliest_go_candidate_at_utc"),
    )
    enforcement_surface = _coalesce(
        _nested_get(operating_cycle_snapshot, "enforcement_surface"),
        "nightly_only",
    )
    profile_scope = _coalesce(
        _nested_get(operating_cycle_snapshot, "profile_scope"),
        "baseline_first",
    )

    decision_status = "hold"
    actionable_message = "Keep signal_only until governance surfaces converge."
    if telemetry_repair_required or str(integrity_status).strip() == "attention":
        decision_status = "repair"
        actionable_message = "Repair telemetry and integrity signals before tightening nightly policy."
    elif transition_allow_switch:
        decision_status = "allow"
        actionable_message = "Operator surfaces indicate fail_nightly is ready on the nightly-only path."
    elif remediation_backlog_primary or int(candidate_item_count) > 0:
        decision_status = "remediate"
        actionable_message = "Work the remediation backlog before switching to a stricter nightly policy."
    elif blocked_manual_gate:
        decision_status = "hold"
        actionable_message = "Wait for the manual gate to clear before the next accounted dispatch."
    actionable_message = _coalesce(
        _nested_get(operating_cycle_snapshot, "actionable_message"),
        actionable_message,
    )

    status = "ok" if not degraded_sources else "degraded"
    if not available_sources:
        status = "not_available"

    summary = {
        "schema_version": GATEWAY_OPERATOR_GOVERNANCE_SCHEMA,
        "status": status,
        "decision_status": decision_status,
        "recommended_policy": recommended_policy,
        "effective_gateway_sla_policy": effective_policy,
        "promotion_state": promotion_state,
        "enforcement_surface": enforcement_surface,
        "blocking_reason_codes": blocking_reason_codes,
        "recommended_actions": recommended_actions,
        "next_review_at_utc": next_review_at_utc,
        "profile_scope": profile_scope,
        "actionable_message": actionable_message,
        "reason_codes": _unique_strings(
            transition_recommendation.get("reason_codes"),
            _nested_get(progress_snapshot, "reason_codes"),
            _nested_get(remediation_snapshot, "reason_codes"),
            integrity_decision.get("reason_codes"),
        ),
        "next_action_hint": operating_cycle_interpretation.get("next_action_hint"),
        "transition_allow_switch": transition_allow_switch,
        "remaining_for_window": _coalesce(
            operating_cycle_triage.get("remaining_for_window"),
            _nested_get(progress_snapshot, "remaining_for_window"),
        ),
        "remaining_for_streak": _coalesce(
            operating_cycle_triage.get("remaining_for_streak"),
            _nested_get(progress_snapshot, "remaining_for_streak"),
        ),
        "candidate_item_count": candidate_item_count,
        "attention_state": operating_cycle_triage.get("attention_state"),
        "integrity_status": integrity_status,
        "operating_mode": _nested_get(operating_cycle_snapshot, "cycle", "operating_mode"),
        "manual_execution_mode": _nested_get(operating_cycle_snapshot, "cycle", "manual_execution_mode"),
        "degraded_sources": degraded_sources,
        "available_sources": available_sources,
        "missing_sources": missing_sources,
        "source_paths": source_paths,
    }
    summary["diagnostics"] = _build_governance_diagnostics(summary)
    return summary


def _is_healthy_stack_service_status(status: str) -> bool:
    return status in {"ok", "running", "ready"}


def _build_stack_service_rollup(
    stack_services: Mapping[str, Any] | None,
) -> tuple[dict[str, int], list[str], str | None]:
    rollup = {
        "total_services": 0,
        "configured_services": 0,
        "healthy_services": 0,
        "attention_services": 0,
        "not_configured_services": 0,
    }
    attention_services: list[str] = []
    primary_message: str | None = None
    if not isinstance(stack_services, Mapping):
        return rollup, attention_services, primary_message

    for raw_service_name, raw_entry in stack_services.items():
        service_name = str(raw_service_name).strip() or "service"
        entry = raw_entry if isinstance(raw_entry, Mapping) else {}
        configured = bool(entry.get("configured"))
        status = str(entry.get("status", "")).strip().lower()
        error = str(entry.get("error", "")).strip()

        rollup["total_services"] += 1
        if configured:
            rollup["configured_services"] += 1
        if not configured or status == "not_configured":
            rollup["not_configured_services"] += 1
            continue
        if _is_healthy_stack_service_status(status):
            rollup["healthy_services"] += 1
            continue

        rollup["attention_services"] += 1
        attention_services.append(service_name)
        if primary_message is None:
            issue = error or f"status={status or 'unknown'}"
            primary_message = f"{service_name}: {issue}"

    return rollup, attention_services, primary_message


def _combo_a_needs_attention(combo_a_summary: Mapping[str, Any] | None) -> bool:
    if not isinstance(combo_a_summary, Mapping):
        return False
    availability_status = str(combo_a_summary.get("availability_status", "")).strip().lower()
    promotion_state = str(combo_a_summary.get("promotion_state", "")).strip().lower()
    if availability_status == "partial":
        return True
    if promotion_state in {"hold", "blocked"} and availability_status != "not_configured":
        return True
    return False


def _build_operator_compact_triage(
    *,
    startup_snapshot: Mapping[str, Any] | None,
    governance_summary: Mapping[str, Any] | None,
    combo_a_summary: Mapping[str, Any] | None,
    stack_services: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(startup_snapshot, Mapping):
        startup_diagnostics = _nested_get(startup_snapshot, "diagnostics")
        startup_diagnostics = startup_diagnostics if isinstance(startup_diagnostics, Mapping) else {}
    else:
        startup_diagnostics = _build_startup_diagnostics(None)
    startup_overall_state = str(startup_diagnostics.get("overall_state", "")).strip().lower() or "unknown"
    startup_primary_issue = _coalesce(startup_diagnostics.get("primary_issue"), None)
    startup_next_step_code = str(startup_diagnostics.get("next_step_code", "")).strip() or "none"
    startup_next_step = startup_diagnostics.get("next_step")

    governance_diagnostics = _nested_get(governance_summary, "diagnostics")
    governance_diagnostics = governance_diagnostics if isinstance(governance_diagnostics, Mapping) else {}
    governance_decision_status = str(
        _coalesce(_nested_get(governance_summary, "decision_status"), "unknown")
    ).strip().lower()
    governance_top_blocker = str(
        _coalesce(governance_diagnostics.get("top_blocker"), "none")
    ).strip().lower() or "none"
    next_safe_action = governance_diagnostics.get("next_safe_action")

    combo_a_availability_status = str(
        _coalesce(_nested_get(combo_a_summary, "availability_status"), "unknown")
    ).strip().lower()
    combo_a_promotion_state_raw = _coalesce(_nested_get(combo_a_summary, "promotion_state"), None)
    combo_a_promotion_state = (
        str(combo_a_promotion_state_raw).strip().lower()
        if combo_a_promotion_state_raw is not None
        else None
    )

    stack_rollup, attention_services, first_service_message = _build_stack_service_rollup(stack_services)

    startup_attention = bool(startup_primary_issue) or startup_overall_state in {
        "degraded",
        "unknown",
        "not_available",
    }
    if startup_overall_state == "stopped" and not startup_primary_issue:
        startup_attention = False

    services_attention = bool(attention_services)
    governance_attention = governance_top_blocker != "none" or governance_decision_status in {
        "repair",
        "remediate",
        "hold",
    }
    combo_a_attention = _combo_a_needs_attention(combo_a_summary)

    primary_surface = "none"
    primary_code = "none"
    primary_message: str | None = None
    next_step_code = "none"
    next_step: str | None = None

    if startup_attention:
        primary_surface = "startup"
        primary_code = (
            startup_next_step_code
            if startup_next_step_code and startup_next_step_code != "none"
            else "startup_attention"
        )
        primary_message = (
            str(startup_primary_issue).strip()
            if startup_primary_issue is not None and str(startup_primary_issue).strip()
            else "Operator startup requires attention."
        )
        next_step_code = startup_next_step_code
        next_step = (
            str(startup_next_step).strip()
            if startup_next_step is not None and str(startup_next_step).strip()
            else None
        )
    elif services_attention:
        primary_surface = "services"
        primary_code = "service_attention"
        primary_message = first_service_message or "One or more configured services require attention."
        first_service_name = attention_services[0]
        next_step_code = "inspect_stack_service"
        next_step = f"Inspect {first_service_name} readiness probe and service configuration."
    elif governance_attention:
        primary_surface = "governance"
        primary_code = governance_top_blocker if governance_top_blocker != "none" else governance_decision_status
        governance_message = _coalesce(_nested_get(governance_summary, "actionable_message"), None)
        primary_message = (
            str(governance_message).strip()
            if governance_message is not None and str(governance_message).strip()
            else "Review the operator governance surface."
        )
        if next_safe_action is not None and str(next_safe_action).strip():
            next_step_code = "run_safe_action"
            next_step = f"Run safe action {str(next_safe_action).strip()} from the gateway operator surface."
        else:
            next_step_code = "review_governance_surface"
            next_step = "Review the operator governance surface and recommended actions."
    elif combo_a_attention:
        primary_surface = "combo_a"
        primary_code = (
            combo_a_promotion_state
            if combo_a_promotion_state is not None and combo_a_promotion_state
            else combo_a_availability_status
        )
        combo_a_message = _coalesce(_nested_get(combo_a_summary, "actionable_message"), None)
        primary_message = (
            str(combo_a_message).strip()
            if combo_a_message is not None and str(combo_a_message).strip()
            else "Review the Combo A promotion surface."
        )
        next_step_code = "review_combo_a"
        next_step = "Review the Combo A promotion surface and live readiness."

    if primary_surface != "none":
        overall_state = "attention"
    elif startup_overall_state == "unknown" and stack_rollup["total_services"] == 0:
        overall_state = "unknown"
    else:
        overall_state = "healthy"

    return {
        "overall_state": overall_state,
        "primary_surface": primary_surface,
        "primary_code": primary_code,
        "primary_message": primary_message,
        "next_step_code": next_step_code,
        "next_step": next_step,
        "next_safe_action": (
            str(next_safe_action).strip()
            if next_safe_action is not None and str(next_safe_action).strip()
            else None
        ),
        "attention_services": attention_services,
        "stack_rollup": stack_rollup,
        "startup_overall_state": startup_overall_state,
        "governance_decision_status": governance_decision_status,
        "governance_top_blocker": governance_top_blocker,
        "combo_a_availability_status": combo_a_availability_status,
        "combo_a_promotion_state": combo_a_promotion_state,
    }


def load_operator_policy_surface_context(
    runs_dir: Path,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    progress_snapshot, progress_warnings = load_fail_nightly_progress_snapshot(runs_dir)
    transition_snapshot, transition_warnings = load_fail_nightly_transition_snapshot(runs_dir)
    remediation_snapshot, remediation_warnings = load_fail_nightly_remediation_snapshot(runs_dir)
    integrity_snapshot, integrity_warnings = load_fail_nightly_integrity_snapshot(runs_dir)
    operating_cycle_snapshot, operating_cycle_warnings = load_operating_cycle_snapshot(runs_dir)
    governance_summary = build_operator_governance_summary(
        progress_snapshot=progress_snapshot,
        transition_snapshot=transition_snapshot,
        remediation_snapshot=remediation_snapshot,
        integrity_snapshot=integrity_snapshot,
        operating_cycle_snapshot=operating_cycle_snapshot,
    )
    return (
        {
            "progress": progress_snapshot,
            "transition": transition_snapshot,
            "remediation": remediation_snapshot,
            "integrity": integrity_snapshot,
            "operating_cycle": operating_cycle_snapshot,
            "governance": governance_summary,
        },
        {
            "progress": progress_warnings,
            "transition": transition_warnings,
            "remediation": remediation_warnings,
            "integrity": integrity_warnings,
            "operating_cycle": operating_cycle_warnings,
        },
    )


def build_metrics_rows(sources: dict[str, Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_name, path in sources.items():
        payload, load_error = load_json_object(path)
        if (
            payload is not None
            and str(payload.get("schema_version", "")).strip() == "cross_service_benchmark_suite_v1"
        ):
            summary_matrix = payload.get("summary_matrix")
            summary_matrix = summary_matrix if isinstance(summary_matrix, list) else []
            if summary_matrix:
                for item in summary_matrix:
                    if not isinstance(item, Mapping):
                        continue
                    row = dict(item)
                    row.setdefault("summary_json", str(path))
                    rows.append(row)
                continue
        row: dict[str, Any] = {
            "source": source_name,
            "summary_json": str(path),
            "status": "missing" if payload is None else str(payload.get("status", "unknown")),
            "details": "-" if load_error is None else load_error,
            "request_count": None,
            "failed_requests_count": None,
            "query_count": None,
            "mean_mrr_at_k": None,
            "results_count": None,
            "profile": None,
            "surface": None,
            "effective_policy": None,
            "promotion_state": None,
        }
        if payload is not None:
            observed = payload.get("observed")
            if isinstance(observed, dict):
                row["results_count"] = observed.get("results_count")
                row["query_count"] = observed.get("query_count")
                row["mean_mrr_at_k"] = observed.get("mean_mrr_at_k")
            row["request_count"] = payload.get("request_count")
            row["failed_requests_count"] = payload.get("failed_requests_count")
            row["profile"] = _coalesce(payload.get("profile"), payload.get("profile_scope"))
            row["surface"] = payload.get("surface")
            row["effective_policy"] = payload.get("effective_policy")
            row["promotion_state"] = payload.get("promotion_state")
        rows.append(row)
    return rows


def build_run_explorer_rows(sources: dict[str, Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_name, path in sources.items():
        payload, load_error = load_json_object(path)
        if (
            payload is not None
            and str(payload.get("schema_version", "")).strip() == "cross_service_benchmark_suite_v1"
        ):
            paths_payload = payload.get("paths")
            paths_payload = paths_payload if isinstance(paths_payload, dict) else {}
            rows.append(
                {
                    "source": source_name,
                    "summary_json": str(path),
                    "status": str(payload.get("status", "unknown")),
                    "scenario": "suite",
                    "run_dir": paths_payload.get("run_dir"),
                    "run_json": paths_payload.get("run_json"),
                    "request_count": len(payload.get("services", {}))
                    if isinstance(payload.get("services"), dict)
                    else None,
                    "failed_requests_count": len(payload.get("degraded_services", []))
                    if isinstance(payload.get("degraded_services"), list)
                    else None,
                    "error": load_error,
                }
            )
            child_runs = paths_payload.get("child_runs")
            child_runs = child_runs if isinstance(child_runs, dict) else {}
            services = payload.get("services")
            services = services if isinstance(services, dict) else {}
            for child_name, child_paths in child_runs.items():
                if not isinstance(child_paths, Mapping):
                    continue
                child_summary = services.get(child_name)
                child_status = (
                    str(child_summary.get("status", "unknown"))
                    if isinstance(child_summary, Mapping)
                    else "unknown"
                )
                rows.append(
                    {
                        "source": f"{source_name}:{child_name}",
                        "summary_json": child_paths.get("summary_json"),
                        "status": child_status,
                        "scenario": "suite_child",
                        "run_dir": child_paths.get("run_dir"),
                        "run_json": child_paths.get("run_json"),
                        "request_count": None,
                        "failed_requests_count": None,
                        "error": None,
                    }
                )
            continue
        row: dict[str, Any] = {
            "source": source_name,
            "summary_json": str(path),
            "status": "missing" if payload is None else str(payload.get("status", "unknown")),
            "scenario": None,
            "run_dir": None,
            "run_json": None,
            "request_count": None,
            "failed_requests_count": None,
            "profile": None,
            "surface": None,
            "effective_policy": None,
            "promotion_state": None,
            "error": load_error,
        }
        if payload is not None:
            paths_payload = payload.get("paths")
            if isinstance(paths_payload, dict):
                row["run_dir"] = paths_payload.get("run_dir")
                row["run_json"] = paths_payload.get("run_json")
            row["scenario"] = payload.get("scenario")
            row["request_count"] = payload.get("request_count")
            row["failed_requests_count"] = payload.get("failed_requests_count")
            row["profile"] = _coalesce(payload.get("profile"), payload.get("profile_scope"))
            row["surface"] = payload.get("surface")
            row["effective_policy"] = payload.get("effective_policy")
            row["promotion_state"] = payload.get("promotion_state")
        rows.append(row)
    return rows


def _history_surface(source: str) -> str:
    if source.startswith("gateway_http_"):
        return "gateway_http"
    if source.startswith("gateway_"):
        return "gateway_local"
    if source.startswith("cross_service_suite"):
        return "cross_service_suite"
    if source == "combo_a_operating_cycle":
        return "combo_a_policy"
    if source in {"retrieve", "eval"}:
        return "retrieval"
    if source == "phase_a":
        return "phase_a"
    return "other"


def _history_scenario(
    source: str,
    run_payload: Mapping[str, Any],
    spec: Mapping[str, str | None],
) -> str | None:
    observed = str(run_payload.get("scenario", "")).strip()
    if observed:
        return observed
    expected = str(spec.get("expected_scenario") or "").strip()
    if expected:
        return expected
    if source.endswith("_combo_a"):
        return "combo_a"
    return None


def _build_history_result_summary(source: str, row: Mapping[str, Any]) -> str:
    status = str(row.get("status", "unknown")).strip() or "unknown"
    request_count = row.get("request_count")
    failed_count = row.get("failed_requests_count")
    results_count = row.get("results_count")
    query_count = row.get("query_count")
    mean_mrr_at_k = row.get("mean_mrr_at_k")
    details = str(row.get("details", "")).strip()

    if source in {
        "gateway_core",
        "gateway_hybrid",
        "gateway_automation",
        "gateway_combo_a",
        "gateway_http_core",
        "gateway_http_hybrid",
        "gateway_http_automation",
        "gateway_http_combo_a",
    }:
        parts: list[str] = []
        if request_count is not None:
            parts.append(f"requests={request_count}")
        if failed_count is not None:
            parts.append(f"failed={failed_count}")
        return ", ".join(parts) if parts else f"status={status}"

    if source == "retrieve":
        return f"results={results_count}" if results_count is not None else f"status={status}"

    if source == "eval":
        parts = []
        if query_count is not None:
            parts.append(f"queries={query_count}")
        if mean_mrr_at_k is not None:
            parts.append(f"mrr@k={mean_mrr_at_k}")
        return ", ".join(parts) if parts else f"status={status}"

    if source in {"cross_service_suite", "cross_service_suite_combo_a"}:
        parts = []
        if details and details != "-":
            parts.append(f"sla={details}")
        if request_count is not None:
            parts.append(f"services={request_count}")
        if failed_count is not None:
            parts.append(f"degraded={failed_count}")
        return ", ".join(parts) if parts else f"status={status}"

    if source == "combo_a_operating_cycle":
        parts = []
        if details and details != "-":
            parts.append(f"policy={details}")
        if failed_count is not None:
            parts.append(f"blockers={failed_count}")
        return ", ".join(parts) if parts else f"status={status}"

    if details and details != "-":
        return details
    return f"status={status}"


def _iter_candidate_run_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    candidates = [
        child
        for child in root.iterdir()
        if child.is_dir() and (child / "run.json").is_file()
    ]
    return sorted(candidates, key=lambda path: path.name, reverse=True)


def _parse_history_row(source: str, run_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    spec = HISTORY_SOURCE_SPECS.get(source)
    if spec is None:
        return None, f"{source}: unsupported history source"

    run_json_path = run_dir / "run.json"
    run_payload, run_error = load_json_object(run_json_path)
    if run_error is not None or run_payload is None:
        return None, f"{source}: invalid run.json at {run_json_path}"

    expected_mode = str(spec["expected_mode"])
    observed_mode = str(run_payload.get("mode", "")).strip()
    if observed_mode != expected_mode:
        return None, (
            f"{source}: mode mismatch for {run_json_path} "
            f"(observed={observed_mode!r}, expected={expected_mode!r})"
        )

    expected_scenario = spec["expected_scenario"]
    if expected_scenario is not None:
        observed_scenario = str(run_payload.get("scenario", "")).strip()
        if observed_scenario != expected_scenario:
            return None, (
                f"{source}: scenario mismatch for {run_json_path} "
                f"(observed={observed_scenario!r}, expected={expected_scenario!r})"
            )

    paths_payload = run_payload.get("paths")
    paths_payload = paths_payload if isinstance(paths_payload, dict) else {}
    summary_json = paths_payload.get("summary_json")
    history_summary_json = paths_payload.get("history_summary_json")
    row: dict[str, Any] = {
        "schema_version": "metrics_history_row_v1",
        "source": source,
        "surface": _history_surface(source),
        "mode": observed_mode,
        "scenario": _history_scenario(source, run_payload, spec),
        "timestamp_utc": run_payload.get("timestamp_utc"),
        "status": str(run_payload.get("status", "unknown")),
        "run_dir": str(run_dir),
        "run_json": str(run_json_path),
        "summary_json": (
            str(history_summary_json)
            if isinstance(history_summary_json, str)
            else (str(summary_json) if isinstance(summary_json, str) else None)
        ),
        "history_summary_json": str(history_summary_json) if isinstance(history_summary_json, str) else None,
        "request_count": run_payload.get("request_count"),
        "failed_requests_count": None,
        "results_count": None,
        "query_count": None,
        "mean_mrr_at_k": None,
        "details": "-",
        "result_summary": None,
    }

    if source in {
        "gateway_core",
        "gateway_hybrid",
        "gateway_automation",
        "gateway_combo_a",
        "gateway_http_core",
        "gateway_http_hybrid",
        "gateway_http_automation",
        "gateway_http_combo_a",
    }:
        result_payload = run_payload.get("result")
        if isinstance(result_payload, dict):
            row["request_count"] = result_payload.get("request_count", row["request_count"])
            row["failed_requests_count"] = result_payload.get("failed_requests_count")
        row["result_summary"] = _build_history_result_summary(source, row)
        return row, None

    if source == "phase_a":
        row["result_summary"] = _build_history_result_summary(source, row)
        return row, None

    if source == "retrieve":
        results_payload, results_error = load_json_object(run_dir / "retrieval_results.json")
        if results_error is not None or results_payload is None:
            return None, f"{source}: missing or invalid retrieval_results.json in {run_dir}"
        results = results_payload.get("results")
        row["results_count"] = len(results) if isinstance(results, list) else results_payload.get("count")
        row["result_summary"] = _build_history_result_summary(source, row)
        return row, None

    if source == "eval":
        eval_payload, eval_error = load_json_object(run_dir / "eval_results.json")
        if eval_error is not None or eval_payload is None:
            return None, f"{source}: missing or invalid eval_results.json in {run_dir}"
        metrics_payload = eval_payload.get("metrics")
        if not isinstance(metrics_payload, dict):
            return None, f"{source}: missing metrics object in eval_results.json for {run_dir}"
        row["query_count"] = metrics_payload.get("query_count")
        row["mean_mrr_at_k"] = metrics_payload.get("mean_mrr_at_k")
        row["result_summary"] = _build_history_result_summary(source, row)
        return row, None

    if source in {"cross_service_suite", "cross_service_suite_combo_a"}:
        summary_path = (
            Path(str(history_summary_json))
            if isinstance(history_summary_json, str)
            else (run_dir / "cross_service_benchmark_suite.json")
        )
        summary_payload, summary_error = load_json_object(summary_path)
        if summary_error is not None or summary_payload is None:
            return None, f"{source}: missing or invalid cross_service_benchmark_suite.json in {run_dir}"
        row["details"] = str(summary_payload.get("overall_sla_status", "-"))
        row["request_count"] = len(summary_payload.get("services", {})) if isinstance(summary_payload.get("services"), dict) else None
        row["failed_requests_count"] = len(summary_payload.get("degraded_services", [])) if isinstance(summary_payload.get("degraded_services"), list) else None
        row["result_summary"] = _build_history_result_summary(source, row)
        return row, None

    if source == "combo_a_operating_cycle":
        summary_path = (
            Path(str(summary_json))
            if isinstance(summary_json, str)
            else (run_dir / "operating_cycle_summary.json")
        )
        summary_payload, summary_error = load_json_object(summary_path)
        if summary_error is not None or summary_payload is None:
            return None, f"{source}: missing or invalid operating_cycle_summary.json in {run_dir}"
        row["details"] = "{effective_policy}/{promotion_state}".format(
            effective_policy=summary_payload.get("effective_policy", "-"),
            promotion_state=summary_payload.get("promotion_state", "-"),
        )
        row["failed_requests_count"] = len(_normalize_reason_codes(summary_payload.get("blocking_reason_codes")))
        row["result_summary"] = _build_history_result_summary(source, row)
        return row, None

    row["result_summary"] = _build_history_result_summary(source, row)
    return row, None


def build_metrics_history_rows(
    runs_dir: Path,
    *,
    selected_sources: list[str] | None = None,
    selected_statuses: list[str] | None = None,
    limit_per_source: int = 10,
    max_candidates_per_source: int = 200,
) -> tuple[list[dict[str, Any]], list[str]]:
    roots = canonical_history_roots(runs_dir)
    source_filter = selected_sources or list(roots.keys())
    status_filter = {value.strip().lower() for value in (selected_statuses or ["ok", "error"])}
    per_source_limit = max(int(limit_per_source), 1)
    candidate_cap = max(int(max_candidates_per_source), 1)

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for source in source_filter:
        root = roots.get(source)
        if root is None:
            warnings.append(f"{source}: unknown source")
            continue
        candidates = _iter_candidate_run_dirs(root)[:candidate_cap]
        source_rows: list[dict[str, Any]] = []
        for run_dir in candidates:
            row, warning = _parse_history_row(source, run_dir)
            if warning is not None:
                warnings.append(warning)
                continue
            if row is None:
                continue
            row_status = str(row.get("status", "unknown")).strip().lower()
            if status_filter and row_status not in status_filter:
                continue
            source_rows.append(row)
            if len(source_rows) >= per_source_limit:
                break
        rows.extend(source_rows)

    rows.sort(key=lambda item: str(item.get("timestamp_utc") or ""), reverse=True)
    return rows, warnings


def build_operator_runs_payload(
    runs_dir: Path,
    *,
    operator_runs_dir: Path | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    effective_operator_runs_dir = Path(operator_runs_dir) if operator_runs_dir is not None else Path(runs_dir)
    startup_status, startup_warnings = load_latest_operator_startup_status(effective_operator_runs_dir)
    startup_status = _attach_startup_diagnostics(startup_status)
    policy_context, policy_warnings = load_operator_policy_surface_context(runs_dir)
    governance_summary = _attach_governance_diagnostics(policy_context["governance"])
    combo_a_operating_cycle, combo_a_operating_cycle_warnings = load_combo_a_operating_cycle_snapshot(runs_dir)
    rows = build_run_explorer_rows(canonical_summary_sources(runs_dir))
    return {
        "schema_version": GATEWAY_OPERATOR_RUNS_SCHEMA,
        "checked_at_utc": _utc_now(),
        "status": "ok",
        "rows": rows[: max(int(limit), 1)],
        "available_sources": list(canonical_summary_sources(runs_dir).keys()),
        "artifact_roots": {
            "runs_dir": str(runs_dir),
            "operator_runs_dir": str(effective_operator_runs_dir),
        },
        "operator_context": {
            "startup": startup_status,
            "governance": governance_summary,
            "operating_cycle": policy_context["operating_cycle"],
            "profiles": {
                "default_profile": DEFAULT_PROFILE,
                "supported_profiles": list(SUPPORTED_PROFILES),
                "combo_a": build_operator_combo_a_profile_summary(
                    combo_a_readiness=None,
                    combo_a_operating_cycle_snapshot=combo_a_operating_cycle,
                ),
            },
        },
        "warnings": {
            "startup": startup_warnings,
            "policy_surface": {
                **policy_warnings,
                "combo_a_operating_cycle": combo_a_operating_cycle_warnings,
            },
        },
    }


def build_operator_history_payload(
    runs_dir: Path,
    *,
    selected_sources: list[str] | None = None,
    selected_statuses: list[str] | None = None,
    limit_per_source: int = 10,
    max_candidates_per_source: int = 200,
) -> dict[str, Any]:
    policy_context, policy_warnings = load_operator_policy_surface_context(runs_dir)
    governance_summary = _attach_governance_diagnostics(policy_context["governance"])
    combo_a_operating_cycle, combo_a_operating_cycle_warnings = load_combo_a_operating_cycle_snapshot(runs_dir)
    rows, warnings = build_metrics_history_rows(
        runs_dir,
        selected_sources=selected_sources,
        selected_statuses=selected_statuses,
        limit_per_source=limit_per_source,
        max_candidates_per_source=max_candidates_per_source,
    )
    return {
        "schema_version": GATEWAY_OPERATOR_HISTORY_SCHEMA,
        "checked_at_utc": _utc_now(),
        "status": "ok",
        "selected_sources": selected_sources or list(canonical_history_roots(runs_dir).keys()),
        "selected_statuses": selected_statuses or ["ok", "error"],
        "limit_per_source": max(int(limit_per_source), 1),
        "rows": rows,
        "warnings": warnings,
        "available_sources": list(canonical_history_roots(runs_dir).keys()),
        "operator_context": {
            "governance": governance_summary,
            "operating_cycle": policy_context["operating_cycle"],
            "profiles": {
                "default_profile": DEFAULT_PROFILE,
                "supported_profiles": list(SUPPORTED_PROFILES),
                "combo_a": build_operator_combo_a_profile_summary(
                    combo_a_readiness=None,
                    combo_a_operating_cycle_snapshot=combo_a_operating_cycle,
                ),
            },
        },
        "operator_warnings": {
            "policy_surface": {
                **policy_warnings,
                "combo_a_operating_cycle": combo_a_operating_cycle_warnings,
            },
        },
    }


def fetch_service_health(
    *,
    service_name: str,
    service_url: str | None,
    timeout_sec: float,
    service_token: str | None = None,
    health_path: str = "/health",
) -> dict[str, Any]:
    if service_url is None or not str(service_url).strip():
        return {
            "service_name": service_name,
            "configured": False,
            "status": "not_configured",
            "url": None,
            "health_path": health_path,
            "payload": None,
            "error": None,
        }

    url = str(service_url).rstrip("/") + health_path
    headers: dict[str, str] = {}
    if service_token:
        headers["X-ATM10-Token"] = service_token
    req = request.Request(url=url, method="GET", headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            body = response.read()
    except url_error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        return {
            "service_name": service_name,
            "configured": True,
            "status": "error",
            "url": str(service_url),
            "health_path": health_path,
            "payload": None,
            "error": f"http {exc.code}: {body.strip() or exc.reason}",
        }
    except Exception as exc:
        return {
            "service_name": service_name,
            "configured": True,
            "status": "error",
            "url": str(service_url),
            "health_path": health_path,
            "payload": None,
            "error": f"health request failed: {exc}",
        }

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        return {
            "service_name": service_name,
            "configured": True,
            "status": "error",
            "url": str(service_url),
            "health_path": health_path,
            "payload": None,
            "error": f"health JSON parse failed: {exc}",
        }
    if not isinstance(payload, dict):
        return {
            "service_name": service_name,
            "configured": True,
            "status": "error",
            "url": str(service_url),
            "health_path": health_path,
            "payload": None,
            "error": "health payload must be object",
        }
    return {
        "service_name": service_name,
        "configured": True,
        "status": str(payload.get("status", "ok")) if payload.get("status") is not None else "ok",
        "url": str(service_url),
        "health_path": health_path,
        "payload": payload,
        "error": None,
    }


def build_operator_product_snapshot(
    *,
    runs_dir: Path,
    gateway_health: dict[str, Any],
    operator_runs_dir: Path | None = None,
    voice_service_url: str | None = None,
    tts_service_url: str | None = None,
    qdrant_url: str | None = None,
    neo4j_url: str | None = None,
    neo4j_database: str = DEFAULT_COMBO_A_NEO4J_DATABASE,
    neo4j_user: str = DEFAULT_COMBO_A_NEO4J_USER,
    health_timeout_sec: float = 1.5,
    service_token: str | None = None,
) -> dict[str, Any]:
    effective_operator_runs_dir = Path(operator_runs_dir) if operator_runs_dir is not None else Path(runs_dir)
    policy_context, policy_warnings = load_operator_policy_surface_context(runs_dir)
    progress_snapshot = policy_context["progress"]
    transition_snapshot = policy_context["transition"]
    remediation_snapshot = policy_context["remediation"]
    integrity_snapshot = policy_context["integrity"]
    operating_cycle_snapshot = policy_context["operating_cycle"]
    combo_a_operating_cycle_snapshot, combo_a_operating_cycle_warnings = load_combo_a_operating_cycle_snapshot(runs_dir)
    pilot_readiness_snapshot, pilot_readiness_warnings = load_pilot_runtime_readiness_snapshot(runs_dir)
    startup_snapshot, startup_warnings = load_latest_operator_startup_status(effective_operator_runs_dir)
    startup_snapshot = _attach_startup_diagnostics(startup_snapshot)
    governance_summary = _attach_governance_diagnostics(policy_context["governance"])
    pilot_runs_dir_value = _nested_get(startup_snapshot, "artifact_roots", "pilot_runtime_runs_dir")
    if not isinstance(pilot_runs_dir_value, str) or not pilot_runs_dir_value.strip():
        pilot_runs_dir_value = _nested_get(startup_snapshot, "session_state", "pilot_runtime", "runs_dir")
    pilot_runs_dir = (
        Path(str(pilot_runs_dir_value))
        if isinstance(pilot_runs_dir_value, str) and pilot_runs_dir_value.strip()
        else effective_operator_runs_dir / "pilot-runtime"
    )
    pilot_status, pilot_warnings = load_latest_pilot_runtime_status(pilot_runs_dir)
    last_turn_summary = _load_pilot_last_turn_summary(pilot_status)

    service_warnings: list[str] = []
    voice_health = fetch_service_health(
        service_name="voice_runtime_service",
        service_url=voice_service_url,
        timeout_sec=health_timeout_sec,
        service_token=service_token,
    )
    tts_health = fetch_service_health(
        service_name="tts_runtime_service",
        service_url=tts_service_url,
        timeout_sec=health_timeout_sec,
        service_token=service_token,
    )
    qdrant_health = probe_qdrant_service(
        qdrant_url=qdrant_url,
        timeout_sec=health_timeout_sec,
    )
    neo4j_health = probe_neo4j_service(
        neo4j_url=neo4j_url,
        neo4j_database=neo4j_database,
        neo4j_user=neo4j_user,
        neo4j_password=None,
        timeout_sec=health_timeout_sec,
    )
    for service_health in (voice_health, tts_health, qdrant_health, neo4j_health):
        if service_health.get("error") is not None:
            service_warnings.append(
                f"{service_health.get('service_name')}: {service_health.get('error')}"
            )
    tts_runtime_diagnostics = _build_tts_runtime_diagnostics(tts_health, last_turn_summary)
    pilot_runtime_summary = _build_pilot_runtime_summary(pilot_status, pilot_runs_dir=pilot_runs_dir)
    pilot_runtime_summary.update(tts_runtime_diagnostics)
    if isinstance(last_turn_summary, dict):
        last_turn_summary.update(
            {
                "preferred_tts_engine": tts_runtime_diagnostics.get("preferred_tts_engine"),
                "active_tts_engine_last_turn": tts_runtime_diagnostics.get("active_tts_engine_last_turn"),
                "piper_available": tts_runtime_diagnostics.get("piper_available"),
                "piper_prewarm_ok": tts_runtime_diagnostics.get("piper_prewarm_ok"),
                "tts_degraded_reason": tts_runtime_diagnostics.get("tts_degraded_reason"),
            }
        )

    combo_a_profile_available = all(
        str(service.get("status", "")).strip() == "ok"
        for service in (voice_health, tts_health, qdrant_health, neo4j_health)
    )
    combo_a_missing_config = [
        service.get("service_name")
        for service in (voice_health, tts_health, qdrant_health, neo4j_health)
        if bool(service.get("configured")) is False
    ]
    combo_a_readiness = {
        "profile": COMBO_A_PROFILE,
        "availability_status": (
            "ready"
            if combo_a_profile_available
            else ("partial" if any(service.get("configured") for service in (voice_health, tts_health, qdrant_health, neo4j_health)) else "not_configured")
        ),
        "available": combo_a_profile_available,
        "missing_config": combo_a_missing_config,
        "warnings": [
            service.get("error")
            for service in (voice_health, tts_health, qdrant_health, neo4j_health)
            if service.get("error")
        ],
        "services": {
            "voice_runtime_service": voice_health,
            "tts_runtime_service": tts_health,
            "qdrant": qdrant_health,
            "neo4j": neo4j_health,
        },
    }
    combo_a_profile_summary = build_operator_combo_a_profile_summary(
        combo_a_readiness=combo_a_readiness,
        combo_a_operating_cycle_snapshot=combo_a_operating_cycle_snapshot,
    )
    stack_services = {
        "gateway_v1_http_service": {
            "service_name": "gateway_v1_http_service",
            "configured": True,
            "status": str(gateway_health.get("status", "unknown")),
            "url": None,
            "health_path": "/healthz",
            "payload": gateway_health,
            "error": None,
        },
        "voice_runtime_service": voice_health,
        "tts_runtime_service": tts_health,
        "qdrant": qdrant_health,
        "neo4j": neo4j_health,
    }
    triage = _build_operator_compact_triage(
        startup_snapshot=startup_snapshot,
        governance_summary=governance_summary,
        combo_a_summary=combo_a_profile_summary,
        stack_services=stack_services,
    )

    return {
        "schema_version": GATEWAY_OPERATOR_STATUS_SCHEMA,
        "checked_at_utc": _utc_now(),
        "status": "ok",
        "gateway": gateway_health,
        "stack_services": stack_services,
        "operator_context": {
            "artifact_roots": {
                "gateway_runs_dir": str(runs_dir),
                "operator_runs_dir": str(effective_operator_runs_dir),
                "pilot_runtime_runs_dir": str(pilot_runs_dir),
            },
            "startup": startup_snapshot,
            "pilot_runtime": pilot_runtime_summary,
            "pilot_readiness": pilot_readiness_snapshot,
            "last_turn_summary": last_turn_summary,
            "governance": governance_summary,
            "triage": triage,
            "profiles": {
                "default_profile": gateway_health.get("supported_profiles", ["baseline_first"])[0]
                if isinstance(gateway_health.get("supported_profiles"), list) and gateway_health.get("supported_profiles")
                else "baseline_first",
                "supported_profiles": gateway_health.get("supported_profiles", ["baseline_first"]),
                "combo_a": combo_a_profile_summary,
            },
        },
        "latest_metrics": {
            "summary_matrix": build_metrics_rows(canonical_summary_sources(runs_dir)),
            "operating_cycle": operating_cycle_snapshot,
            "combo_a_operating_cycle": combo_a_operating_cycle_snapshot,
            "fail_nightly_progress": progress_snapshot,
            "fail_nightly_transition": transition_snapshot,
            "fail_nightly_remediation": remediation_snapshot,
            "fail_nightly_integrity": integrity_snapshot,
        },
        "warnings": {
            "metrics": [
                *policy_warnings["progress"],
                *policy_warnings["transition"],
                *policy_warnings["remediation"],
                *policy_warnings["integrity"],
                *policy_warnings["operating_cycle"],
            ],
            "service_probes": service_warnings,
            "pilot_runtime": pilot_warnings,
            "pilot_readiness": pilot_readiness_warnings,
            "startup": startup_warnings,
            "profile_readiness": combo_a_readiness["warnings"],
            "policy_surface": {
                **policy_warnings,
                "combo_a_operating_cycle": combo_a_operating_cycle_warnings,
            },
            "combo_a_policy_surface": combo_a_operating_cycle_warnings,
        },
    }
