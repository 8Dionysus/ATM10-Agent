from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib import error as url_error
from urllib import request

GATEWAY_OPERATOR_STATUS_SCHEMA = "gateway_operator_status_v1"
GATEWAY_OPERATOR_RUNS_SCHEMA = "gateway_operator_runs_v1"
GATEWAY_OPERATOR_HISTORY_SCHEMA = "gateway_operator_history_v1"
GATEWAY_OPERATOR_GOVERNANCE_SCHEMA = "gateway_operator_governance_summary_v1"
OPERATOR_PRODUCT_STARTUP_SCHEMA = "operator_product_startup_v1"

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
    "cross_service_suite": {
        "root_subdir": "ci-smoke-cross-service-suite",
        "expected_mode": "cross_service_benchmark_suite",
        "expected_scenario": None,
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
        "gateway_http_core": base / "ci-smoke-gateway-http-core" / "gateway_http_smoke_summary.json",
        "gateway_http_hybrid": base / "ci-smoke-gateway-http-hybrid" / "gateway_http_smoke_summary.json",
        "gateway_http_automation": base / "ci-smoke-gateway-http-automation" / "gateway_http_smoke_summary.json",
        "cross_service_suite": base / "ci-smoke-cross-service-suite" / "cross_service_benchmark_suite.json",
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
        "cycle": cycle,
        "triage": triage,
        "interpretation": interpretation,
        "paths": {
            "summary_json": _coalesce(paths_payload.get("summary_json"), str(path)),
            "brief_md": paths_payload.get("brief_md"),
        },
        "source_path": str(path),
    }
    return snapshot, []


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
            },
        }
        return summary, warnings
    return None, warnings


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

    status = "ok" if not degraded_sources else "degraded"
    if not available_sources:
        status = "not_available"

    return {
        "schema_version": GATEWAY_OPERATOR_GOVERNANCE_SCHEMA,
        "status": status,
        "decision_status": decision_status,
        "recommended_policy": recommended_policy,
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
        }
        if payload is not None:
            observed = payload.get("observed")
            if isinstance(observed, dict):
                row["results_count"] = observed.get("results_count")
                row["query_count"] = observed.get("query_count")
                row["mean_mrr_at_k"] = observed.get("mean_mrr_at_k")
            row["request_count"] = payload.get("request_count")
            row["failed_requests_count"] = payload.get("failed_requests_count")
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
        rows.append(row)
    return rows


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
    row: dict[str, Any] = {
        "schema_version": "metrics_history_row_v1",
        "source": source,
        "timestamp_utc": run_payload.get("timestamp_utc"),
        "status": str(run_payload.get("status", "unknown")),
        "run_dir": str(run_dir),
        "run_json": str(run_json_path),
        "summary_json": str(summary_json) if isinstance(summary_json, str) else None,
        "request_count": run_payload.get("request_count"),
        "failed_requests_count": None,
        "results_count": None,
        "query_count": None,
        "mean_mrr_at_k": None,
        "details": "-",
    }

    if source in {
        "gateway_core",
        "gateway_hybrid",
        "gateway_automation",
        "gateway_http_core",
        "gateway_http_hybrid",
        "gateway_http_automation",
    }:
        result_payload = run_payload.get("result")
        if isinstance(result_payload, dict):
            row["request_count"] = result_payload.get("request_count", row["request_count"])
            row["failed_requests_count"] = result_payload.get("failed_requests_count")
        return row, None

    if source == "phase_a":
        return row, None

    if source == "retrieve":
        results_payload, results_error = load_json_object(run_dir / "retrieval_results.json")
        if results_error is not None or results_payload is None:
            return None, f"{source}: missing or invalid retrieval_results.json in {run_dir}"
        results = results_payload.get("results")
        row["results_count"] = len(results) if isinstance(results, list) else results_payload.get("count")
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
        return row, None

    if source == "cross_service_suite":
        summary_path = Path(str(summary_json)) if isinstance(summary_json, str) else (run_dir / "cross_service_benchmark_suite.json")
        summary_payload, summary_error = load_json_object(summary_path)
        if summary_error is not None or summary_payload is None:
            return None, f"{source}: missing or invalid cross_service_benchmark_suite.json in {run_dir}"
        row["details"] = str(summary_payload.get("overall_sla_status", "-"))
        row["request_count"] = len(summary_payload.get("services", {})) if isinstance(summary_payload.get("services"), dict) else None
        row["failed_requests_count"] = len(summary_payload.get("degraded_services", [])) if isinstance(summary_payload.get("degraded_services"), list) else None
        return row, None

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
        },
        "warnings": {
            "startup": startup_warnings,
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
    health_timeout_sec: float = 1.5,
    service_token: str | None = None,
) -> dict[str, Any]:
    effective_operator_runs_dir = Path(operator_runs_dir) if operator_runs_dir is not None else Path(runs_dir)
    progress_snapshot, progress_warnings = load_fail_nightly_progress_snapshot(runs_dir)
    transition_snapshot, transition_warnings = load_fail_nightly_transition_snapshot(runs_dir)
    remediation_snapshot, remediation_warnings = load_fail_nightly_remediation_snapshot(runs_dir)
    integrity_snapshot, integrity_warnings = load_fail_nightly_integrity_snapshot(runs_dir)
    operating_cycle_snapshot, operating_cycle_warnings = load_operating_cycle_snapshot(runs_dir)
    startup_snapshot, startup_warnings = load_latest_operator_startup_status(effective_operator_runs_dir)
    governance_summary = build_operator_governance_summary(
        progress_snapshot=progress_snapshot,
        transition_snapshot=transition_snapshot,
        remediation_snapshot=remediation_snapshot,
        integrity_snapshot=integrity_snapshot,
        operating_cycle_snapshot=operating_cycle_snapshot,
    )

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
    for service_health in (voice_health, tts_health):
        if service_health.get("error") is not None:
            service_warnings.append(
                f"{service_health.get('service_name')}: {service_health.get('error')}"
            )

    return {
        "schema_version": GATEWAY_OPERATOR_STATUS_SCHEMA,
        "checked_at_utc": _utc_now(),
        "status": "ok",
        "gateway": gateway_health,
        "stack_services": {
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
        },
        "operator_context": {
            "artifact_roots": {
                "gateway_runs_dir": str(runs_dir),
                "operator_runs_dir": str(effective_operator_runs_dir),
            },
            "startup": startup_snapshot,
            "governance": governance_summary,
        },
        "latest_metrics": {
            "summary_matrix": build_metrics_rows(canonical_summary_sources(runs_dir)),
            "operating_cycle": operating_cycle_snapshot,
            "fail_nightly_progress": progress_snapshot,
            "fail_nightly_transition": transition_snapshot,
            "fail_nightly_remediation": remediation_snapshot,
            "fail_nightly_integrity": integrity_snapshot,
        },
        "warnings": {
            "metrics": [
                *progress_warnings,
                *transition_warnings,
                *remediation_warnings,
                *integrity_warnings,
                *operating_cycle_warnings,
            ],
            "service_probes": service_warnings,
            "startup": startup_warnings,
        },
    }
