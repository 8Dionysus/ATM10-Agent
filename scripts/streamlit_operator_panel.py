from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as url_error
from urllib import request

try:  # pragma: no cover - import presence is validated via runtime/smoke
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


REPO_ROOT = Path(__file__).resolve().parents[1]

from scripts.operator_product_snapshot import (
    GATEWAY_OPERATOR_HISTORY_SCHEMA,
    GATEWAY_OPERATOR_STATUS_SCHEMA,
    GATEWAY_OPERATOR_RUNS_SCHEMA,
    FAIL_NIGHTLY_INTEGRITY_SOURCE_SPEC,
    FAIL_NIGHTLY_PROGRESS_SOURCE_SPECS,
    FAIL_NIGHTLY_REMEDIATION_SOURCE_SPEC,
    FAIL_NIGHTLY_TRANSITION_SOURCE_SPEC,
    OPERATING_CYCLE_SOURCE_SPEC,
    build_operator_governance_summary as shared_build_operator_governance_summary,
    build_metrics_history_rows as shared_build_metrics_history_rows,
    build_metrics_rows as shared_build_metrics_rows,
    build_run_explorer_rows as shared_build_run_explorer_rows,
    canonical_fail_nightly_integrity_source as shared_canonical_fail_nightly_integrity_source,
    canonical_fail_nightly_progress_sources as shared_canonical_fail_nightly_progress_sources,
    canonical_fail_nightly_remediation_source as shared_canonical_fail_nightly_remediation_source,
    canonical_fail_nightly_transition_source as shared_canonical_fail_nightly_transition_source,
    canonical_history_roots as shared_canonical_history_roots,
    canonical_operating_cycle_source as shared_canonical_operating_cycle_source,
    canonical_summary_sources as shared_canonical_summary_sources,
    load_fail_nightly_integrity_snapshot as shared_load_fail_nightly_integrity_snapshot,
    load_fail_nightly_progress_snapshot as shared_load_fail_nightly_progress_snapshot,
    load_fail_nightly_remediation_snapshot as shared_load_fail_nightly_remediation_snapshot,
    load_fail_nightly_transition_snapshot as shared_load_fail_nightly_transition_snapshot,
    load_json_object as shared_load_json_object,
    load_latest_operator_startup_status as shared_load_latest_operator_startup_status,
    load_operating_cycle_snapshot as shared_load_operating_cycle_snapshot,
)
from scripts.operator_product_safe_actions import (
    GATEWAY_OPERATOR_SAFE_ACTIONS_SCHEMA,
    GATEWAY_OPERATOR_SAFE_ACTION_RUN_SCHEMA,
    append_safe_action_audit as shared_append_safe_action_audit,
    load_safe_action_audit as shared_load_safe_action_audit,
    resolve_safe_action as shared_resolve_safe_action,
    run_safe_action as shared_run_safe_action,
    safe_actions_audit_log_path as shared_safe_actions_audit_log_path,
)

TAB_NAMES = (
    "Stack Health",
    "Run Explorer",
    "Latest Metrics",
    "Safe Actions",
)

MOBILE_LAYOUT_POLICY_SCHEMA = "streamlit_mobile_layout_policy_v1"
MOBILE_LAYOUT_BREAKPOINT_PX_DEFAULT = 768
MOBILE_BASELINE_VIEWPORT = {"width": 390, "height": 844}

SAFE_ACTIONS: dict[str, dict[str, str]] = {
    "gateway_local_core": {
        "script": "scripts/gateway_v1_smoke.py",
        "scenario": "core",
        "runs_subdir": "ui-safe-gateway-core",
        "summary_name": "gateway_smoke_summary.json",
    },
    "gateway_local_hybrid": {
        "script": "scripts/gateway_v1_smoke.py",
        "scenario": "hybrid",
        "runs_subdir": "ui-safe-gateway-hybrid",
        "summary_name": "gateway_smoke_summary.json",
    },
    "gateway_local_automation": {
        "script": "scripts/gateway_v1_smoke.py",
        "scenario": "automation",
        "runs_subdir": "ui-safe-gateway-automation",
        "summary_name": "gateway_smoke_summary.json",
    },
    "gateway_http_core": {
        "script": "scripts/gateway_v1_http_smoke.py",
        "scenario": "core",
        "runs_subdir": "ui-safe-gateway-http-core",
        "summary_name": "gateway_http_smoke_summary.json",
    },
    "gateway_http_hybrid": {
        "script": "scripts/gateway_v1_http_smoke.py",
        "scenario": "hybrid",
        "runs_subdir": "ui-safe-gateway-http-hybrid",
        "summary_name": "gateway_http_smoke_summary.json",
    },
    "gateway_http_automation": {
        "script": "scripts/gateway_v1_http_smoke.py",
        "scenario": "automation",
        "runs_subdir": "ui-safe-gateway-http-automation",
        "summary_name": "gateway_http_smoke_summary.json",
    },
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
}

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


def safe_actions_audit_log_path(runs_dir: Path) -> Path:
    return shared_safe_actions_audit_log_path(runs_dir)


def append_safe_action_audit(runs_dir: Path, entry: dict[str, Any]) -> None:
    shared_append_safe_action_audit(runs_dir, entry)


def load_safe_action_audit(runs_dir: Path, limit: int = 10) -> list[dict[str, Any]]:
    return shared_load_safe_action_audit(runs_dir, limit=limit)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mobile_layout_policy(*, breakpoint_px: int = MOBILE_LAYOUT_BREAKPOINT_PX_DEFAULT) -> dict[str, Any]:
    normalized_breakpoint = max(int(breakpoint_px), 320)
    return {
        "schema_version": MOBILE_LAYOUT_POLICY_SCHEMA,
        "compact_breakpoint_px": normalized_breakpoint,
        "mobile_baseline_viewport": dict(MOBILE_BASELINE_VIEWPORT),
        "compact_fields": [
            "header controls stack in one column",
            "reduced horizontal paddings",
            "dataframes scroll horizontally",
        ],
    }


def build_compact_mobile_css(*, breakpoint_px: int = MOBILE_LAYOUT_BREAKPOINT_PX_DEFAULT) -> str:
    normalized_breakpoint = max(int(breakpoint_px), 320)
    return (
        "<style>\n"
        "@media (max-width: "
        f"{normalized_breakpoint}px"
        ") {\n"
        "  [data-testid=\"stAppViewContainer\"] .main .block-container {\n"
        "    padding-top: 0.75rem;\n"
        "    padding-bottom: 1rem;\n"
        "    padding-left: 0.75rem;\n"
        "    padding-right: 0.75rem;\n"
        "  }\n"
        "  [data-testid=\"stHorizontalBlock\"] {\n"
        "    display: flex;\n"
        "    flex-direction: column;\n"
        "    gap: 0.5rem;\n"
        "  }\n"
        "  [data-testid=\"column\"] {\n"
        "    width: 100% !important;\n"
        "    min-width: 0;\n"
        "  }\n"
        "  [data-testid=\"stDataFrame\"] {\n"
        "    overflow-x: auto;\n"
        "  }\n"
        "}\n"
        "</style>"
    )


def apply_compact_mobile_layout(*, breakpoint_px: int = MOBILE_LAYOUT_BREAKPOINT_PX_DEFAULT) -> None:
    if st is None:
        return
    st.markdown(build_compact_mobile_css(breakpoint_px=breakpoint_px), unsafe_allow_html=True)


def canonical_summary_sources(runs_dir: Path) -> dict[str, Path]:
    base = Path(runs_dir)
    return {
        "phase_a": base / "ci-smoke-phase-a" / "smoke_summary.json",
        "retrieve": base / "ci-smoke-retrieve" / "smoke_summary.json",
        "eval": base / "ci-smoke-eval" / "smoke_summary.json",
        "gateway_core": base / "ci-smoke-gateway-core" / "gateway_smoke_summary.json",
        "gateway_hybrid": base / "ci-smoke-gateway-hybrid" / "gateway_smoke_summary.json",
        "gateway_automation": base / "ci-smoke-gateway-automation" / "gateway_smoke_summary.json",
        "gateway_http_core": base
        / "ci-smoke-gateway-http-core"
        / "gateway_http_smoke_summary.json",
        "gateway_http_hybrid": base
        / "ci-smoke-gateway-http-hybrid"
        / "gateway_http_smoke_summary.json",
        "gateway_http_automation": base
        / "ci-smoke-gateway-http-automation"
        / "gateway_http_smoke_summary.json",
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
    return shared_canonical_history_roots(runs_dir)


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

    return row, None


def build_metrics_history_rows(
    runs_dir: Path,
    *,
    selected_sources: list[str] | None = None,
    selected_statuses: list[str] | None = None,
    limit_per_source: int = 10,
    max_candidates_per_source: int = 200,
) -> tuple[list[dict[str, Any]], list[str]]:
    return shared_build_metrics_history_rows(
        runs_dir,
        selected_sources=selected_sources,
        selected_statuses=selected_statuses,
        limit_per_source=limit_per_source,
        max_candidates_per_source=max_candidates_per_source,
    )


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
    return payload, []


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


canonical_summary_sources = shared_canonical_summary_sources
canonical_fail_nightly_progress_sources = shared_canonical_fail_nightly_progress_sources
canonical_fail_nightly_remediation_source = shared_canonical_fail_nightly_remediation_source
canonical_fail_nightly_transition_source = shared_canonical_fail_nightly_transition_source
canonical_fail_nightly_integrity_source = shared_canonical_fail_nightly_integrity_source
canonical_operating_cycle_source = shared_canonical_operating_cycle_source
load_json_object = shared_load_json_object
load_fail_nightly_progress_snapshot = shared_load_fail_nightly_progress_snapshot
load_fail_nightly_remediation_snapshot = shared_load_fail_nightly_remediation_snapshot
load_fail_nightly_transition_snapshot = shared_load_fail_nightly_transition_snapshot
load_fail_nightly_integrity_snapshot = shared_load_fail_nightly_integrity_snapshot
load_operating_cycle_snapshot = shared_load_operating_cycle_snapshot
load_latest_operator_startup_status = shared_load_latest_operator_startup_status
build_operator_governance_summary = shared_build_operator_governance_summary
build_metrics_rows = shared_build_metrics_rows
build_run_explorer_rows = shared_build_run_explorer_rows
canonical_history_roots = shared_canonical_history_roots
build_metrics_history_rows = shared_build_metrics_history_rows


def fetch_gateway_health(gateway_url: str, timeout_sec: float) -> tuple[dict[str, Any] | None, str | None]:
    url = gateway_url.rstrip("/") + "/healthz"
    req = request.Request(url=url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            body = response.read()
    except Exception as exc:
        return None, f"gateway health request failed: {exc}"
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        return None, f"gateway health JSON parse failed: {exc}"
    if not isinstance(payload, dict):
        return None, "gateway health payload must be object"
    return payload, None


def fetch_gateway_operator_snapshot(
    gateway_url: str,
    timeout_sec: float,
) -> tuple[dict[str, Any] | None, str | None]:
    url = gateway_url.rstrip("/") + "/v1/operator/snapshot"
    req = request.Request(url=url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            body = response.read()
    except Exception as exc:
        return None, f"gateway operator snapshot request failed: {exc}"
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        return None, f"gateway operator snapshot JSON parse failed: {exc}"
    if not isinstance(payload, dict):
        return None, "gateway operator snapshot payload must be object"
    if str(payload.get("schema_version", "")).strip() != GATEWAY_OPERATOR_STATUS_SCHEMA:
        return None, (
            "gateway operator snapshot schema mismatch: "
            f"{payload.get('schema_version')!r} != {GATEWAY_OPERATOR_STATUS_SCHEMA!r}"
        )
    return payload, None


def fetch_gateway_operator_runs(
    gateway_url: str,
    timeout_sec: float,
    *,
    limit: int = 20,
) -> tuple[dict[str, Any] | None, str | None]:
    url = gateway_url.rstrip("/") + f"/v1/operator/runs?limit={max(int(limit), 1)}"
    req = request.Request(url=url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            body = response.read()
    except Exception as exc:
        return None, f"gateway operator runs request failed: {exc}"
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        return None, f"gateway operator runs JSON parse failed: {exc}"
    if not isinstance(payload, dict):
        return None, "gateway operator runs payload must be object"
    if str(payload.get("schema_version", "")).strip() != GATEWAY_OPERATOR_RUNS_SCHEMA:
        return None, (
            "gateway operator runs schema mismatch: "
            f"{payload.get('schema_version')!r} != {GATEWAY_OPERATOR_RUNS_SCHEMA!r}"
        )
    return payload, None


def fetch_gateway_operator_history(
    gateway_url: str,
    timeout_sec: float,
    *,
    selected_sources: list[str] | None = None,
    selected_statuses: list[str] | None = None,
    limit_per_source: int = 10,
) -> tuple[dict[str, Any] | None, str | None]:
    query_parts = [f"limit_per_source={max(int(limit_per_source), 1)}"]
    if selected_sources:
        query_parts.append("source=" + ",".join(selected_sources))
    if selected_statuses:
        query_parts.append("status=" + ",".join(selected_statuses))
    url = gateway_url.rstrip("/") + "/v1/operator/history?" + "&".join(query_parts)
    req = request.Request(url=url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            body = response.read()
    except Exception as exc:
        return None, f"gateway operator history request failed: {exc}"
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        return None, f"gateway operator history JSON parse failed: {exc}"
    if not isinstance(payload, dict):
        return None, "gateway operator history payload must be object"
    if str(payload.get("schema_version", "")).strip() != GATEWAY_OPERATOR_HISTORY_SCHEMA:
        return None, (
            "gateway operator history schema mismatch: "
            f"{payload.get('schema_version')!r} != {GATEWAY_OPERATOR_HISTORY_SCHEMA!r}"
        )
    return payload, None


def fetch_gateway_safe_actions(
    gateway_url: str,
    timeout_sec: float,
    *,
    history_limit: int = 10,
) -> tuple[dict[str, Any] | None, str | None]:
    url = gateway_url.rstrip("/") + f"/v1/operator/safe-actions?history_limit={max(int(history_limit), 1)}"
    req = request.Request(url=url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            body = response.read()
    except Exception as exc:
        return None, f"gateway safe actions request failed: {exc}"
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        return None, f"gateway safe actions JSON parse failed: {exc}"
    if not isinstance(payload, dict):
        return None, "gateway safe actions payload must be object"
    if str(payload.get("schema_version", "")).strip() != GATEWAY_OPERATOR_SAFE_ACTIONS_SCHEMA:
        return None, (
            "gateway safe actions schema mismatch: "
            f"{payload.get('schema_version')!r} != {GATEWAY_OPERATOR_SAFE_ACTIONS_SCHEMA!r}"
        )
    return payload, None


def run_gateway_safe_action(
    gateway_url: str,
    timeout_sec: float,
    *,
    action_key: str,
    confirm: bool,
    action_timeout_sec: float = 300.0,
) -> tuple[dict[str, Any] | None, str | None]:
    url = gateway_url.rstrip("/") + "/v1/operator/safe-actions/run"
    body = json.dumps(
        {
            "action_key": action_key,
            "confirm": bool(confirm),
            "timeout_sec": float(action_timeout_sec),
        }
    ).encode("utf-8")
    req = request.Request(
        url=url,
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            raw_body = response.read()
    except url_error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(error_body)
        except Exception:
            return None, f"gateway safe action request failed: http {exc.code}: {error_body or exc.reason}"
        if isinstance(payload, dict):
            return None, str(payload.get("error") or f"http {exc.code}")
        return None, f"gateway safe action request failed: http {exc.code}"
    except Exception as exc:
        return None, f"gateway safe action request failed: {exc}"
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        return None, f"gateway safe action JSON parse failed: {exc}"
    if not isinstance(payload, dict):
        return None, "gateway safe action payload must be object"
    if str(payload.get("schema_version", "")).strip() != GATEWAY_OPERATOR_SAFE_ACTION_RUN_SCHEMA:
        return None, (
            "gateway safe action schema mismatch: "
            f"{payload.get('schema_version')!r} != {GATEWAY_OPERATOR_SAFE_ACTION_RUN_SCHEMA!r}"
        )
    return payload, None


def _render_snapshot_warnings(title: str, warnings: list[str]) -> None:
    if not warnings:
        return
    sample = "\n".join(f"- {item}" for item in warnings[:5])
    suffix = "" if len(warnings) <= 5 else "\n- ..."
    st.warning(f"{title} ({len(warnings)}):\n{sample}{suffix}")


def _render_operator_startup_section(snapshot: dict[str, Any] | None, warnings: list[str]) -> None:
    _render_snapshot_warnings(
        "Some operator startup artifacts were skipped due to parse/contract issues",
        warnings,
    )
    if snapshot is None:
        st.info(
            "Operator startup artifacts are not available yet. "
            "Launch the canonical stack with `python scripts/start_operator_product.py --runs-dir runs`."
        )
        return

    if str(snapshot.get("status")) == "error":
        st.error(
            "Latest operator startup run ended with status=error.\n"
            f"{_coalesce(snapshot.get('error'), 'See launcher artifacts for details.')}"
        )
    elif str(snapshot.get("status")) == "stopped":
        st.info("Latest operator startup run is stopped; the session artifact is still available for review.")
    else:
        st.success("Latest operator startup artifact loaded.")

    last_checkpoint = snapshot.get("last_checkpoint")
    last_checkpoint = last_checkpoint if isinstance(last_checkpoint, dict) else {}
    startup_row = {
        "status": snapshot.get("status"),
        "profile": snapshot.get("profile"),
        "gateway_url": snapshot.get("gateway_url"),
        "streamlit_url": snapshot.get("streamlit_url"),
        "checkpoint_count": snapshot.get("checkpoint_count"),
        "last_stage": last_checkpoint.get("stage"),
        "last_stage_status": last_checkpoint.get("status"),
        "last_stage_message": last_checkpoint.get("message"),
    }
    st.dataframe([startup_row], width="stretch")

    session_state = snapshot.get("session_state")
    session_state = session_state if isinstance(session_state, dict) else {}
    if session_state:
        service_order = ("gateway", "streamlit", "voice_runtime_service", "tts_runtime_service")
        service_rows: list[dict[str, Any]] = []
        for service_name in service_order:
            entry = session_state.get(service_name)
            if not isinstance(entry, dict):
                continue
            last_probe = entry.get("last_probe")
            last_probe = last_probe if isinstance(last_probe, dict) else {}
            service_rows.append(
                {
                    "service_name": service_name,
                    "managed": entry.get("managed"),
                    "status": entry.get("status"),
                    "effective_url": entry.get("effective_url"),
                    "pid": entry.get("pid"),
                    "last_probe_status": last_probe.get("status"),
                    "error": _coalesce(entry.get("error"), last_probe.get("error")),
                    "log_path": entry.get("log_path"),
                }
            )
        if service_rows:
            st.caption("Operator session state")
            st.dataframe(service_rows, width="stretch")

    st.caption("Startup artifacts")
    st.json(snapshot.get("paths"))


def _render_operator_governance_section(summary: dict[str, Any] | None) -> None:
    if summary is None:
        st.info(
            "Governance decision surface is not available yet. "
            "Run `python scripts/run_gateway_sla_operating_cycle.py --runs-dir runs` to populate it."
        )
        return

    decision_status = str(summary.get("decision_status", "")).strip()
    actionable_message = _coalesce(summary.get("actionable_message"), "No operator guidance available yet.")
    if decision_status == "allow":
        st.success(actionable_message)
    elif decision_status in {"repair", "remediate"}:
        st.warning(actionable_message)
    else:
        st.info(actionable_message)

    governance_row = {
        "status": summary.get("status"),
        "decision_status": summary.get("decision_status"),
        "recommended_policy": summary.get("recommended_policy"),
        "next_action_hint": summary.get("next_action_hint"),
        "transition_allow_switch": summary.get("transition_allow_switch"),
        "remaining_for_window": summary.get("remaining_for_window"),
        "remaining_for_streak": summary.get("remaining_for_streak"),
        "candidate_item_count": summary.get("candidate_item_count"),
        "integrity_status": summary.get("integrity_status"),
        "attention_state": summary.get("attention_state"),
        "degraded_sources": ", ".join(_normalize_reason_codes(summary.get("degraded_sources"))),
    }
    st.dataframe([governance_row], width="stretch")
    reason_codes = _normalize_reason_codes(summary.get("reason_codes"))
    if reason_codes:
        st.caption("Governance reason codes")
        st.dataframe([{"reason_codes": ", ".join(reason_codes)}], width="stretch")
    st.caption("Governance source paths")
    st.json(summary.get("source_paths"))


def _render_operating_cycle_section(snapshot: dict[str, Any] | None, warnings: list[str]) -> None:
    _render_snapshot_warnings(
        "Some G2 operating cycle artifacts were skipped due to parse/contract issues",
        warnings,
    )
    if snapshot is None:
        st.info("not available yet")
        return

    cycle = snapshot.get("cycle")
    cycle = cycle if isinstance(cycle, dict) else {}
    triage = snapshot.get("triage")
    triage = triage if isinstance(triage, dict) else {}
    interpretation = snapshot.get("interpretation")
    interpretation = interpretation if isinstance(interpretation, dict) else {}
    operating_cycle_row = {
        "status": snapshot.get("status"),
        "cycle_source": cycle.get("source"),
        "operating_mode": cycle.get("operating_mode"),
        "used_manual_fallback": cycle.get("used_manual_fallback"),
        "manual_execution_mode": cycle.get("manual_execution_mode"),
        "manual_decision_status": cycle.get("manual_decision_status"),
        "readiness_status": triage.get("readiness_status"),
        "governance_decision_status": triage.get("governance_decision_status"),
        "progress_decision_status": triage.get("progress_decision_status"),
        "remaining_for_window": triage.get("remaining_for_window"),
        "remaining_for_streak": triage.get("remaining_for_streak"),
        "transition_allow_switch": triage.get("transition_allow_switch"),
        "candidate_item_count": triage.get("candidate_item_count"),
        "integrity_status": triage.get("integrity_status"),
        "attention_state": triage.get("attention_state"),
        "earliest_go_candidate_at_utc": triage.get("earliest_go_candidate_at_utc"),
        "next_accounted_dispatch_at_utc": triage.get("next_accounted_dispatch_at_utc"),
        "next_action_hint": interpretation.get("next_action_hint"),
    }
    st.dataframe([operating_cycle_row], width="stretch")
    candidate_item_ids = _normalize_reason_codes(triage.get("candidate_item_ids"))
    if candidate_item_ids:
        st.caption("Operating cycle candidate backlog")
        st.dataframe(
            [{"candidate_item_ids": ", ".join(candidate_item_ids)}],
            width="stretch",
        )
    invalid_counts = triage.get("invalid_counts")
    invalid_counts = invalid_counts if isinstance(invalid_counts, dict) else {}
    if invalid_counts:
        st.caption("Operating cycle invalid counts")
        st.json(invalid_counts)
    operating_cycle_paths = snapshot.get("paths")
    operating_cycle_paths = operating_cycle_paths if isinstance(operating_cycle_paths, dict) else {}
    st.caption("Operating cycle artifacts")
    st.json(
        {
            "checked_at_utc": snapshot.get("checked_at_utc"),
            "summary_json": operating_cycle_paths.get("summary_json"),
            "brief_md": _coalesce(operating_cycle_paths.get("brief_md"), "not available yet"),
        }
    )


def _render_fail_nightly_progress_section(snapshot: dict[str, Any] | None, warnings: list[str]) -> None:
    _render_snapshot_warnings(
        "Some fail_nightly progress artifacts were skipped due to parse/contract issues",
        warnings,
    )
    if snapshot is None:
        st.info("not available yet")
        return

    progress_row = {
        "readiness_status": snapshot.get("readiness_status"),
        "latest_ready_streak": snapshot.get("latest_ready_streak"),
        "decision_status": snapshot.get("decision_status"),
        "remaining_for_window": snapshot.get("remaining_for_window"),
        "remaining_for_streak": snapshot.get("remaining_for_streak"),
        "target_critical_policy": snapshot.get("target_critical_policy"),
        "reason_codes": ", ".join(snapshot.get("reason_codes") or []),
        "available_sources": ", ".join(snapshot.get("available_sources") or []),
        "missing_sources": ", ".join(snapshot.get("missing_sources") or []),
    }
    st.dataframe([progress_row], width="stretch")
    st.caption("Progress source paths")
    st.json(snapshot.get("source_paths"))


def _render_fail_nightly_transition_section(snapshot: dict[str, Any] | None, warnings: list[str]) -> None:
    _render_snapshot_warnings(
        "Some fail_nightly transition artifacts were skipped due to parse/contract issues",
        warnings,
    )
    if snapshot is None:
        st.info("not available yet")
        return

    transition_row = {
        "status": snapshot.get("status"),
        "decision_status": snapshot.get("decision_status"),
        "allow_switch": snapshot.get("allow_switch"),
        "recommended_policy": _nested_get(snapshot, "recommendation", "target_critical_policy"),
        "switch_surface": _nested_get(snapshot, "recommendation", "switch_surface"),
        "reason_codes": ", ".join(_normalize_reason_codes(_nested_get(snapshot, "recommendation", "reason_codes"))),
        "remaining_for_window": _nested_get(snapshot, "observed", "progress", "remaining_for_window"),
        "remaining_for_streak": _nested_get(snapshot, "observed", "progress", "remaining_for_streak"),
    }
    st.dataframe([transition_row], width="stretch")
    st.caption("Transition artifact")
    st.json(snapshot.get("paths"))


def _render_fail_nightly_remediation_section(snapshot: dict[str, Any] | None, warnings: list[str]) -> None:
    _render_snapshot_warnings(
        "Some fail_nightly remediation artifacts were skipped due to parse/contract issues",
        warnings,
    )
    if snapshot is None:
        st.info("not available yet")
        return

    observed = snapshot.get("observed")
    observed = observed if isinstance(observed, dict) else {}
    candidate_items = snapshot.get("candidate_items")
    candidate_items = candidate_items if isinstance(candidate_items, list) else []
    candidate_ids = [
        str(item.get("id"))
        for item in candidate_items
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    ]
    remediation_row = {
        "status": snapshot.get("status"),
        "policy": snapshot.get("policy"),
        "readiness_status": observed.get("readiness_status"),
        "governance_decision_status": observed.get("governance_decision_status"),
        "progress_decision_status": observed.get("progress_decision_status"),
        "transition_allow_switch": observed.get("transition_allow_switch"),
        "remaining_for_window": observed.get("remaining_for_window"),
        "remaining_for_streak": observed.get("remaining_for_streak"),
        "attention_state": observed.get("attention_state"),
        "candidate_item_count": len(candidate_items),
        "candidate_item_ids": ", ".join(candidate_ids),
        "reason_codes": ", ".join(_normalize_reason_codes(snapshot.get("reason_codes"))),
    }
    st.dataframe([remediation_row], width="stretch")
    if candidate_items:
        candidate_rows = []
        for item in candidate_items:
            if not isinstance(item, dict):
                continue
            candidate_rows.append(
                {
                    "id": item.get("id"),
                    "priority": item.get("priority"),
                    "summary": item.get("summary"),
                    "source_refs": ", ".join(_normalize_reason_codes(item.get("source_refs"))),
                }
            )
        if candidate_rows:
            st.caption("Remediation candidate backlog")
            st.dataframe(candidate_rows, width="stretch")
    else:
        st.caption("Remediation backlog not required.")
    st.caption("Remediation artifact")
    st.json(
        {
            "checked_at_utc": snapshot.get("checked_at_utc"),
            "summary_json": _coalesce(
                _nested_get(snapshot, "paths", "summary_json"),
                "not available yet",
            ),
        }
    )


def _render_fail_nightly_integrity_section(snapshot: dict[str, Any] | None, warnings: list[str]) -> None:
    _render_snapshot_warnings(
        "Some fail_nightly integrity artifacts were skipped due to parse/contract issues",
        warnings,
    )
    if snapshot is None:
        st.info("not available yet")
        return

    observed = snapshot.get("observed")
    observed = observed if isinstance(observed, dict) else {}
    decision = snapshot.get("decision")
    decision = decision if isinstance(decision, dict) else {}
    invalid_counts = observed.get("invalid_counts")
    invalid_counts = invalid_counts if isinstance(invalid_counts, dict) else {}
    utc_guardrail = observed.get("utc_guardrail")
    utc_guardrail = utc_guardrail if isinstance(utc_guardrail, dict) else {}
    integrity_row = {
        "status": snapshot.get("status"),
        "integrity_status": decision.get("integrity_status"),
        "telemetry_ok": observed.get("telemetry_ok"),
        "dual_write_ok": observed.get("dual_write_ok"),
        "anti_double_count_ok": observed.get("anti_double_count_ok"),
        "utc_guardrail_status": observed.get("utc_guardrail_status"),
        "governance_invalid": invalid_counts.get("governance"),
        "progress_readiness_invalid": invalid_counts.get("progress_readiness"),
        "progress_governance_invalid": invalid_counts.get("progress_governance"),
        "transition_aggregated_invalid": invalid_counts.get("transition_aggregated"),
        "reason_codes": ", ".join(_normalize_reason_codes(decision.get("reason_codes"))),
    }
    st.dataframe([integrity_row], width="stretch")
    st.caption("Integrity UTC guardrail")
    st.json(utc_guardrail)
    st.caption("Integrity artifact")
    st.json(
        {
            "checked_at_utc": snapshot.get("checked_at_utc"),
            "summary_json": _coalesce(
                _nested_get(snapshot, "paths", "summary_json"),
                "not available yet",
            ),
        }
    )


def build_metrics_rows(sources: dict[str, Path]) -> list[dict[str, Any]]:
    return shared_build_metrics_rows(sources)


def build_run_explorer_rows(sources: dict[str, Path]) -> list[dict[str, Any]]:
    return shared_build_run_explorer_rows(sources)


def resolve_safe_action(action_key: str, runs_dir: Path) -> tuple[list[str], Path]:
    command, _action_runs_dir, summary_path = shared_resolve_safe_action(action_key, runs_dir)
    return command, summary_path


def run_safe_action(action_key: str, runs_dir: Path, *, timeout_sec: float = 300.0) -> dict[str, Any]:
    return shared_run_safe_action(action_key, runs_dir, timeout_sec=timeout_sec)


def parse_panel_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Streamlit operator panel v0.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Base runs directory.")
    parser.add_argument(
        "--operator-runs-dir",
        type=Path,
        default=None,
        help="Operator artifact base directory used to resolve launcher/session artifacts (default: --runs-dir).",
    )
    parser.add_argument(
        "--gateway-url",
        default="http://127.0.0.1:8770",
        help="Gateway HTTP base URL (default: http://127.0.0.1:8770).",
    )
    parser.add_argument(
        "--gateway-timeout-sec",
        type=float,
        default=3.0,
        help="Gateway health timeout in seconds (default: 3.0).",
    )
    parser.add_argument(
        "--compact-breakpoint-px",
        type=int,
        default=MOBILE_LAYOUT_BREAKPOINT_PX_DEFAULT,
        help=f"Compact mobile breakpoint in px (default: {MOBILE_LAYOUT_BREAKPOINT_PX_DEFAULT}).",
    )
    args, _unknown = parser.parse_known_args(argv)
    args.operator_runs_dir = Path(args.operator_runs_dir) if args.operator_runs_dir is not None else Path(args.runs_dir)
    return args


def _render_stack_health_tab(
    *,
    health_payload: dict[str, Any] | None,
    health_error: str | None,
    operator_snapshot_payload: dict[str, Any] | None,
    operator_snapshot_error: str | None,
    operator_startup_payload: dict[str, Any] | None,
    operator_startup_warnings: list[str],
) -> None:
    if health_error is not None:
        st.error(health_error)
        return
    if health_payload is None:
        st.error("gateway health payload is not available")
        return

    if operator_snapshot_payload is not None:
        st.success("Gateway operator snapshot loaded.")
        stack_services = operator_snapshot_payload.get("stack_services")
        stack_services = stack_services if isinstance(stack_services, dict) else {}
        service_rows: list[dict[str, Any]] = []
        for service_name, payload in stack_services.items():
            payload = payload if isinstance(payload, dict) else {}
            service_health = payload.get("payload")
            service_health = service_health if isinstance(service_health, dict) else {}
            service_rows.append(
                {
                    "service_name": service_name,
                    "configured": payload.get("configured"),
                    "status": payload.get("status"),
                    "url": payload.get("url"),
                    "api_docs_exposed": service_health.get("api_docs_exposed"),
                    "auth_enabled": service_health.get("auth_enabled"),
                    "error": payload.get("error"),
                }
            )
        if service_rows:
            st.subheader("Stack services")
            st.dataframe(service_rows, width="stretch")
        warning_payload = operator_snapshot_payload.get("warnings")
        warning_payload = warning_payload if isinstance(warning_payload, dict) else {}
        _render_snapshot_warnings(
            "Some downstream service probes returned errors",
            [str(item) for item in warning_payload.get("service_probes", []) if str(item).strip()],
        )
    else:
        st.success("Gateway transport health loaded.")
        if operator_snapshot_error is not None:
            st.info(
                "Gateway operator snapshot unavailable; using direct gateway health only.\n"
                f"{operator_snapshot_error}"
            )

    st.json(health_payload)
    policy = health_payload.get("policy") if isinstance(health_payload, dict) else None
    if isinstance(policy, dict):
        st.subheader("Gateway policy snapshot")
        st.json(policy)

    st.subheader("Operator startup session")
    _render_operator_startup_section(operator_startup_payload, operator_startup_warnings)


def _render_run_explorer_tab(
    *,
    gateway_url: str,
    gateway_timeout_sec: float,
    sources: dict[str, Path],
) -> None:
    runs_payload, runs_error = fetch_gateway_operator_runs(
        gateway_url,
        gateway_timeout_sec,
        limit=20,
    )
    if runs_payload is not None:
        rows = runs_payload.get("rows")
        rows = rows if isinstance(rows, list) else []
        st.caption("Data source: gateway operator runs")
    else:
        rows = build_run_explorer_rows(sources)
        st.caption(
            "Data source: local contract fallback"
            if runs_error is not None
            else "Data source: local contract files"
        )
        if runs_error is not None:
            st.info(f"Gateway operator runs unavailable; using local fallback.\n{runs_error}")
    st.dataframe(rows, width="stretch")
    st.subheader("Artifact paths")
    for row in rows:
        st.code(
            "\n".join(
                [
                    f"source={row['source']}",
                    f"summary_json={row['summary_json']}",
                    f"run_dir={row.get('run_dir')}",
                    f"run_json={row.get('run_json')}",
                ]
            )
        )


def _render_latest_metrics_tab(
    runs_dir: Path,
    sources: dict[str, Path],
    *,
    gateway_url: str,
    gateway_timeout_sec: float,
    operator_snapshot_payload: dict[str, Any] | None,
    operator_snapshot_error: str | None,
) -> None:
    latest_metrics_payload = (
        operator_snapshot_payload.get("latest_metrics")
        if isinstance(operator_snapshot_payload, dict)
        else None
    )
    latest_metrics_payload = latest_metrics_payload if isinstance(latest_metrics_payload, dict) else None
    warning_payload = (
        operator_snapshot_payload.get("warnings")
        if isinstance(operator_snapshot_payload, dict)
        else None
    )
    warning_payload = warning_payload if isinstance(warning_payload, dict) else {}
    governance_summary = (
        _nested_get(operator_snapshot_payload, "operator_context", "governance")
        if isinstance(operator_snapshot_payload, dict)
        else None
    )
    governance_summary = governance_summary if isinstance(governance_summary, dict) else None
    if latest_metrics_payload is not None:
        rows = latest_metrics_payload.get("summary_matrix")
        rows = rows if isinstance(rows, list) else []
        st.caption("Data source: gateway operator snapshot")
    else:
        rows = build_metrics_rows(sources)
        st.caption(
            "Data source: local contract fallback"
            if operator_snapshot_error is not None
            else "Data source: local contract files"
        )
    if governance_summary is None:
        local_progress_snapshot, _ = load_fail_nightly_progress_snapshot(runs_dir)
        local_transition_snapshot, _ = load_fail_nightly_transition_snapshot(runs_dir)
        local_remediation_snapshot, _ = load_fail_nightly_remediation_snapshot(runs_dir)
        local_integrity_snapshot, _ = load_fail_nightly_integrity_snapshot(runs_dir)
        local_operating_cycle_snapshot, _ = load_operating_cycle_snapshot(runs_dir)
        governance_summary = build_operator_governance_summary(
            progress_snapshot=local_progress_snapshot,
            transition_snapshot=local_transition_snapshot,
            remediation_snapshot=local_remediation_snapshot,
            integrity_snapshot=local_integrity_snapshot,
            operating_cycle_snapshot=local_operating_cycle_snapshot,
        )
    st.subheader("Operator governance")
    _render_operator_governance_section(governance_summary)
    st.subheader("Latest summary matrix")
    st.dataframe(rows, width="stretch")

    st.subheader("G2 operating cycle")
    operating_cycle_snapshot = (
        latest_metrics_payload.get("operating_cycle") if latest_metrics_payload is not None else None
    )
    operating_cycle_snapshot = operating_cycle_snapshot if isinstance(operating_cycle_snapshot, dict) else None
    operating_cycle_warnings = [str(item) for item in warning_payload.get("metrics", []) if "operating_cycle" in str(item)]
    if operating_cycle_snapshot is None and latest_metrics_payload is None:
        operating_cycle_snapshot, operating_cycle_warnings = load_operating_cycle_snapshot(runs_dir)
    _render_operating_cycle_section(operating_cycle_snapshot, operating_cycle_warnings)

    st.subheader("Gateway fail_nightly progress")
    progress_snapshot = (
        latest_metrics_payload.get("fail_nightly_progress") if latest_metrics_payload is not None else None
    )
    progress_snapshot = progress_snapshot if isinstance(progress_snapshot, dict) else None
    progress_warnings = [str(item) for item in warning_payload.get("metrics", []) if "progress" in str(item)]
    if progress_snapshot is None and latest_metrics_payload is None:
        progress_snapshot, progress_warnings = load_fail_nightly_progress_snapshot(runs_dir)
    _render_fail_nightly_progress_section(progress_snapshot, progress_warnings)

    st.subheader("Gateway fail_nightly transition")
    transition_snapshot = (
        latest_metrics_payload.get("fail_nightly_transition") if latest_metrics_payload is not None else None
    )
    transition_snapshot = transition_snapshot if isinstance(transition_snapshot, dict) else None
    transition_warnings = [str(item) for item in warning_payload.get("metrics", []) if "transition" in str(item)]
    if transition_snapshot is None and latest_metrics_payload is None:
        transition_snapshot, transition_warnings = load_fail_nightly_transition_snapshot(runs_dir)
    _render_fail_nightly_transition_section(transition_snapshot, transition_warnings)

    st.subheader("Gateway fail_nightly remediation")
    remediation_snapshot = (
        latest_metrics_payload.get("fail_nightly_remediation") if latest_metrics_payload is not None else None
    )
    remediation_snapshot = remediation_snapshot if isinstance(remediation_snapshot, dict) else None
    remediation_warnings = [str(item) for item in warning_payload.get("metrics", []) if "remediation" in str(item)]
    if remediation_snapshot is None and latest_metrics_payload is None:
        remediation_snapshot, remediation_warnings = load_fail_nightly_remediation_snapshot(runs_dir)
    _render_fail_nightly_remediation_section(remediation_snapshot, remediation_warnings)

    st.subheader("Gateway fail_nightly integrity")
    integrity_snapshot = (
        latest_metrics_payload.get("fail_nightly_integrity") if latest_metrics_payload is not None else None
    )
    integrity_snapshot = integrity_snapshot if isinstance(integrity_snapshot, dict) else None
    integrity_warnings = [str(item) for item in warning_payload.get("metrics", []) if "integrity" in str(item)]
    if integrity_snapshot is None and latest_metrics_payload is None:
        integrity_snapshot, integrity_warnings = load_fail_nightly_integrity_snapshot(runs_dir)
    _render_fail_nightly_integrity_section(integrity_snapshot, integrity_warnings)

    st.subheader("Historical snapshots")
    history_roots = canonical_history_roots(runs_dir)
    source_options = list(history_roots.keys())
    selected_sources = st.multiselect(
        "History sources",
        source_options,
        default=source_options,
    )
    status_options = ["ok", "error"]
    selected_statuses = st.multiselect(
        "History statuses",
        status_options,
        default=status_options,
    )
    limit_per_source = int(
        st.number_input(
            "History limit per source",
            min_value=1,
            max_value=100,
            value=10,
            step=1,
        )
    )
    history_rows: list[dict[str, Any]] = []
    history_warnings: list[str] = []
    history_payload, history_error = fetch_gateway_operator_history(
        gateway_url,
        gateway_timeout_sec,
        selected_sources=selected_sources,
        selected_statuses=selected_statuses,
        limit_per_source=limit_per_source,
    )
    if history_payload is not None:
        history_rows = history_payload.get("rows")
        history_rows = history_rows if isinstance(history_rows, list) else []
        history_warnings = [str(item) for item in history_payload.get("warnings", []) if str(item).strip()]
        st.caption("History source: gateway operator history")
    else:
        history_rows, history_warnings = build_metrics_history_rows(
            runs_dir,
            selected_sources=selected_sources,
            selected_statuses=selected_statuses,
            limit_per_source=limit_per_source,
            max_candidates_per_source=200,
        )
        st.caption("History source: local contract fallback")
        if history_error is not None:
            st.info(f"Gateway operator history unavailable; using local fallback.\n{history_error}")
    if history_warnings:
        sample = "\n".join(f"- {item}" for item in history_warnings[:5])
        suffix = "" if len(history_warnings) <= 5 else "\n- ..."
        st.warning(
            "Some historical runs were skipped due to parse/contract issues "
            f"({len(history_warnings)}):\n{sample}{suffix}"
        )
    if not history_rows:
        st.info("not available yet")
        return
    st.dataframe(history_rows, width="stretch")


def _render_safe_actions_tab(*, gateway_url: str, gateway_timeout_sec: float) -> None:
    safe_actions_payload, safe_actions_error = fetch_gateway_safe_actions(
        gateway_url,
        gateway_timeout_sec,
        history_limit=10,
    )
    if safe_actions_payload is None:
        st.warning(
            "Safe Actions require a reachable gateway operator API. "
            f"Gateway is unavailable right now.\n{safe_actions_error}"
        )
        return

    catalog = safe_actions_payload.get("catalog")
    catalog = catalog if isinstance(catalog, list) else []
    if not catalog:
        st.info("not available yet")
        return

    action_labels = {
        str(item.get("label") or item.get("action_key")): str(item.get("action_key"))
        for item in catalog
        if isinstance(item, dict) and str(item.get("action_key", "")).strip()
    }
    selected_label = st.selectbox("Safe action", list(action_labels.keys()))
    confirm = st.checkbox("I understand this stays smoke-only and goes through the gateway.")
    if st.button("Execute safe action", disabled=not confirm):
        selected_key = action_labels[selected_label]
        result, run_error = run_gateway_safe_action(
            gateway_url,
            gateway_timeout_sec,
            action_key=selected_key,
            confirm=True,
        )
        if run_error is not None:
            st.error(run_error)
        else:
            if str(result.get("status")) == "ok":
                st.success("Safe action finished with status=ok.")
            else:
                st.error("Safe action finished with status=error.")
            st.json(result)
        safe_actions_payload, _refresh_error = fetch_gateway_safe_actions(
            gateway_url,
            gateway_timeout_sec,
            history_limit=10,
        )

    audit_rows = safe_actions_payload.get("recent_runs") if isinstance(safe_actions_payload, dict) else None
    audit_rows = audit_rows if isinstance(audit_rows, list) else []
    st.subheader("Last safe action")
    if not audit_rows:
        st.info("not available yet")
    else:
        last = audit_rows[0]
        st.json(
            {
                "timestamp_utc": last.get("timestamp_utc"),
                "action_key": last.get("action_key"),
                "exit_code": last.get("exit_code"),
                "status": last.get("status"),
                "summary_json": last.get("summary_json"),
                "error": last.get("error"),
            }
        )
    st.subheader("Recent safe actions")
    if not audit_rows:
        st.info("not available yet")
    else:
        st.dataframe(audit_rows, width="stretch")


def render_panel(args: argparse.Namespace) -> None:
    if st is None:
        raise RuntimeError("streamlit is required. Install dependency and re-run.")

    st.set_page_config(page_title="ATM10 Operator Panel", layout="wide")
    apply_compact_mobile_layout(breakpoint_px=args.compact_breakpoint_px)
    st.title("ATM10 Operator Panel v0")

    if "runs_dir" not in st.session_state:
        st.session_state["runs_dir"] = str(args.runs_dir)
    if "gateway_url" not in st.session_state:
        st.session_state["gateway_url"] = args.gateway_url
    if "operator_runs_dir" not in st.session_state:
        st.session_state["operator_runs_dir"] = str(args.operator_runs_dir)
    if "last_refreshed_utc" not in st.session_state:
        st.session_state["last_refreshed_utc"] = _utc_now()

    col1, col2, col3 = st.columns([2, 3, 1])
    with col1:
        runs_dir_raw = st.text_input("runs_dir", value=st.session_state["runs_dir"])
    with col2:
        gateway_url = st.text_input("gateway_url", value=st.session_state["gateway_url"])
    with col3:
        if st.button("Refresh"):
            st.session_state["last_refreshed_utc"] = _utc_now()

    st.session_state["runs_dir"] = runs_dir_raw
    st.session_state["gateway_url"] = gateway_url
    st.caption(f"last_refreshed_utc: {st.session_state['last_refreshed_utc']}")

    runs_dir = Path(st.session_state["runs_dir"])
    operator_runs_dir = Path(st.session_state["operator_runs_dir"])
    sources = canonical_summary_sources(runs_dir)
    operator_snapshot_payload, operator_snapshot_error = fetch_gateway_operator_snapshot(
        gateway_url, args.gateway_timeout_sec
    )
    operator_startup_payload = (
        _nested_get(operator_snapshot_payload, "operator_context", "startup")
        if isinstance(operator_snapshot_payload, dict)
        else None
    )
    operator_startup_payload = operator_startup_payload if isinstance(operator_startup_payload, dict) else None
    operator_startup_warnings = [
        str(item)
        for item in _normalize_reason_codes(_nested_get(operator_snapshot_payload, "warnings", "startup"))
    ]
    if operator_startup_payload is None:
        operator_startup_payload, operator_startup_warnings = load_latest_operator_startup_status(operator_runs_dir)
    if operator_snapshot_payload is not None and isinstance(operator_snapshot_payload.get("gateway"), dict):
        health_payload = operator_snapshot_payload.get("gateway")
        health_error = None
    else:
        health_payload, health_error = fetch_gateway_health(gateway_url, args.gateway_timeout_sec)
    tabs = st.tabs(list(TAB_NAMES))

    with tabs[0]:
        _render_stack_health_tab(
            health_payload=health_payload if isinstance(health_payload, dict) else None,
            health_error=health_error,
            operator_snapshot_payload=operator_snapshot_payload,
            operator_snapshot_error=operator_snapshot_error,
            operator_startup_payload=operator_startup_payload,
            operator_startup_warnings=operator_startup_warnings,
        )
    with tabs[1]:
        _render_run_explorer_tab(
            gateway_url=gateway_url,
            gateway_timeout_sec=args.gateway_timeout_sec,
            sources=sources,
        )
    with tabs[2]:
        _render_latest_metrics_tab(
            runs_dir,
            sources,
            gateway_url=gateway_url,
            gateway_timeout_sec=args.gateway_timeout_sec,
            operator_snapshot_payload=operator_snapshot_payload,
            operator_snapshot_error=operator_snapshot_error,
        )
    with tabs[3]:
        _render_safe_actions_tab(
            gateway_url=gateway_url,
            gateway_timeout_sec=args.gateway_timeout_sec,
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_panel_args(argv)
    render_panel(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
