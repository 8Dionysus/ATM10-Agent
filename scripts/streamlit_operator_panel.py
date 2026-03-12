from __future__ import annotations

import argparse
import json
import subprocess
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


def safe_actions_audit_log_path(runs_dir: Path) -> Path:
    return Path(runs_dir) / "ui-safe-actions" / "safe_actions_audit.jsonl"


def append_safe_action_audit(runs_dir: Path, entry: dict[str, Any]) -> None:
    path = safe_actions_audit_log_path(runs_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp_utc": entry.get("timestamp_utc") or _utc_now(),
        "action_key": entry.get("action_key"),
        "command": entry.get("command"),
        "exit_code": entry.get("exit_code"),
        "status": entry.get("status"),
        "summary_json": entry.get("summary_json"),
        "summary_status": entry.get("summary_status"),
        "error": entry.get("error"),
        "ok": bool(entry.get("ok", False)),
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_safe_action_audit(runs_dir: Path, limit: int = 10) -> list[dict[str, Any]]:
    path = safe_actions_audit_log_path(runs_dir)
    if limit <= 0:
        return []
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return [
            {
                "timestamp_utc": _utc_now(),
                "action_key": "audit_read_error",
                "command": None,
                "exit_code": None,
                "status": "error",
                "summary_json": str(path),
                "summary_status": None,
                "error": f"failed to read audit log: {exc}",
                "ok": False,
            }
        ]

    for line_idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            entries.append(
                {
                    "timestamp_utc": _utc_now(),
                    "action_key": "invalid_audit_entry",
                    "command": None,
                    "exit_code": None,
                    "status": "error",
                    "summary_json": str(path),
                    "summary_status": None,
                    "error": f"invalid audit entry at line {line_idx}",
                    "ok": False,
                }
            )
            continue
        if not isinstance(payload, dict):
            entries.append(
                {
                    "timestamp_utc": _utc_now(),
                    "action_key": "invalid_audit_entry",
                    "command": None,
                    "exit_code": None,
                    "status": "error",
                    "summary_json": str(path),
                    "summary_status": None,
                    "error": f"invalid audit entry at line {line_idx}",
                    "ok": False,
                }
            )
            continue
        entries.append(
            {
                "timestamp_utc": payload.get("timestamp_utc"),
                "action_key": payload.get("action_key"),
                "command": payload.get("command"),
                "exit_code": payload.get("exit_code"),
                "status": payload.get("status"),
                "summary_json": payload.get("summary_json"),
                "summary_status": payload.get("summary_status"),
                "error": payload.get("error"),
                "ok": bool(payload.get("ok", False)),
            }
        )
    return list(reversed(entries))[:limit]


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
        "gateway_automation": base / "ci-smoke-gateway-automation" / "gateway_smoke_summary.json",
        "gateway_http_core": base
        / "ci-smoke-gateway-http-core"
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


def canonical_history_roots(runs_dir: Path) -> dict[str, Path]:
    base = Path(runs_dir)
    return {
        source: base / str(spec["root_subdir"])
        for source, spec in HISTORY_SOURCE_SPECS.items()
    }


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

    if source in {"gateway_core", "gateway_automation", "gateway_http_core", "gateway_http_automation"}:
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


def build_metrics_rows(sources: dict[str, Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_name, path in sources.items():
        payload, load_error = load_json_object(path)
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


def resolve_safe_action(action_key: str, runs_dir: Path) -> tuple[list[str], Path]:
    config = SAFE_ACTIONS.get(action_key)
    if config is None:
        raise ValueError(f"unsupported safe action: {action_key!r}")
    action_runs_dir = Path(runs_dir) / config["runs_subdir"]
    summary_path = action_runs_dir / config["summary_name"]
    command = [
        sys.executable,
        config["script"],
        "--scenario",
        config["scenario"],
        "--runs-dir",
        str(action_runs_dir),
        "--summary-json",
        str(summary_path),
    ]
    return command, summary_path


def run_safe_action(action_key: str, runs_dir: Path, *, timeout_sec: float = 300.0) -> dict[str, Any]:
    command, summary_path = resolve_safe_action(action_key, runs_dir)
    command_text = " ".join(command)
    started_at_utc = _utc_now()
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "timestamp_utc": started_at_utc,
            "action_key": action_key,
            "command": command_text,
            "exit_code": 2,
            "status": "error",
            "ok": False,
            "summary_json": str(summary_path),
            "error": f"safe action timeout: {exc}",
            "stdout": "",
            "stderr": "",
        }
    summary_payload, load_error = load_json_object(summary_path)
    summary_status = None if summary_payload is None else str(summary_payload.get("status"))
    ok = completed.returncode == 0 and summary_status == "ok" and load_error is None
    return {
        "timestamp_utc": started_at_utc,
        "action_key": action_key,
        "command": command_text,
        "exit_code": int(completed.returncode),
        "status": "ok" if ok else "error",
        "ok": ok,
        "summary_json": str(summary_path),
        "summary_status": summary_status,
        "error": load_error,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def parse_panel_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Streamlit operator panel v0.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Base runs directory.")
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
    return args


def _render_stack_health_tab(gateway_url: str, gateway_timeout_sec: float) -> None:
    health_payload, health_error = fetch_gateway_health(gateway_url, gateway_timeout_sec)
    if health_error is not None:
        st.error(health_error)
        return
    st.success("Gateway transport health loaded.")
    st.json(health_payload)
    policy = health_payload.get("policy") if isinstance(health_payload, dict) else None
    if isinstance(policy, dict):
        st.subheader("Gateway policy snapshot")
        st.json(policy)


def _render_run_explorer_tab(sources: dict[str, Path]) -> None:
    rows = build_run_explorer_rows(sources)
    st.dataframe(rows, use_container_width=True)
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


def _render_latest_metrics_tab(runs_dir: Path, sources: dict[str, Path]) -> None:
    rows = build_metrics_rows(sources)
    st.subheader("Latest summary matrix")
    st.dataframe(rows, use_container_width=True)

    st.subheader("Gateway fail_nightly progress")
    progress_snapshot, progress_warnings = load_fail_nightly_progress_snapshot(runs_dir)
    if progress_warnings:
        sample = "\n".join(f"- {item}" for item in progress_warnings[:5])
        suffix = "" if len(progress_warnings) <= 5 else "\n- ..."
        st.warning(
            "Some fail_nightly progress artifacts were skipped due to parse/contract issues "
            f"({len(progress_warnings)}):\n{sample}{suffix}"
        )
    if progress_snapshot is None:
        st.info("not available yet")
    else:
        progress_row = {
            "readiness_status": progress_snapshot.get("readiness_status"),
            "latest_ready_streak": progress_snapshot.get("latest_ready_streak"),
            "decision_status": progress_snapshot.get("decision_status"),
            "remaining_for_window": progress_snapshot.get("remaining_for_window"),
            "remaining_for_streak": progress_snapshot.get("remaining_for_streak"),
            "target_critical_policy": progress_snapshot.get("target_critical_policy"),
            "reason_codes": ", ".join(progress_snapshot.get("reason_codes") or []),
            "available_sources": ", ".join(progress_snapshot.get("available_sources") or []),
            "missing_sources": ", ".join(progress_snapshot.get("missing_sources") or []),
        }
        st.dataframe([progress_row], use_container_width=True)
        st.caption("Progress source paths")
        st.json(progress_snapshot.get("source_paths"))

    st.subheader("Gateway fail_nightly remediation")
    remediation_snapshot, remediation_warnings = load_fail_nightly_remediation_snapshot(runs_dir)
    if remediation_warnings:
        sample = "\n".join(f"- {item}" for item in remediation_warnings[:5])
        suffix = "" if len(remediation_warnings) <= 5 else "\n- ..."
        st.warning(
            "Some fail_nightly remediation artifacts were skipped due to parse/contract issues "
            f"({len(remediation_warnings)}):\n{sample}{suffix}"
        )
    if remediation_snapshot is None:
        st.info("not available yet")
    else:
        observed = remediation_snapshot.get("observed")
        observed = observed if isinstance(observed, dict) else {}
        candidate_items = remediation_snapshot.get("candidate_items")
        candidate_items = candidate_items if isinstance(candidate_items, list) else []
        candidate_ids = [
            str(item.get("id"))
            for item in candidate_items
            if isinstance(item, dict) and str(item.get("id", "")).strip()
        ]
        remediation_row = {
            "status": remediation_snapshot.get("status"),
            "policy": remediation_snapshot.get("policy"),
            "readiness_status": observed.get("readiness_status"),
            "governance_decision_status": observed.get("governance_decision_status"),
            "progress_decision_status": observed.get("progress_decision_status"),
            "transition_allow_switch": observed.get("transition_allow_switch"),
            "remaining_for_window": observed.get("remaining_for_window"),
            "remaining_for_streak": observed.get("remaining_for_streak"),
            "attention_state": observed.get("attention_state"),
            "candidate_item_count": len(candidate_items),
            "candidate_item_ids": ", ".join(candidate_ids),
            "reason_codes": ", ".join(_normalize_reason_codes(remediation_snapshot.get("reason_codes"))),
        }
        st.dataframe([remediation_row], use_container_width=True)
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
                st.dataframe(candidate_rows, use_container_width=True)
        else:
            st.caption("Remediation backlog not required.")
        st.caption("Remediation artifact")
        st.json(
            {
                "checked_at_utc": remediation_snapshot.get("checked_at_utc"),
                "summary_json": _coalesce(
                    _nested_get(remediation_snapshot, "paths", "summary_json"),
                    str(canonical_fail_nightly_remediation_source(runs_dir)),
                ),
            }
        )

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
    history_rows, history_warnings = build_metrics_history_rows(
        runs_dir,
        selected_sources=selected_sources,
        selected_statuses=selected_statuses,
        limit_per_source=limit_per_source,
        max_candidates_per_source=200,
    )
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
    st.dataframe(history_rows, use_container_width=True)


def _render_safe_actions_tab(runs_dir: Path) -> None:
    action_labels = {
        "Gateway local smoke core": "gateway_local_core",
        "Gateway local smoke automation": "gateway_local_automation",
        "Gateway HTTP smoke core": "gateway_http_core",
        "Gateway HTTP smoke automation": "gateway_http_automation",
    }
    selected_label = st.selectbox("Safe action", list(action_labels.keys()))
    action_runs_dir_raw = st.text_input("Action runs_dir", value=str(runs_dir))
    if st.button("Execute safe action"):
        selected_key = action_labels[selected_label]
        result = run_safe_action(selected_key, Path(action_runs_dir_raw))
        append_safe_action_audit(Path(action_runs_dir_raw), result)
        if result["ok"]:
            st.success("Safe action finished with status=ok.")
        else:
            st.error("Safe action finished with status=error.")
        st.json(result)

    audit_rows = load_safe_action_audit(Path(action_runs_dir_raw), limit=10)
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
        st.dataframe(audit_rows, use_container_width=True)


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
    sources = canonical_summary_sources(runs_dir)
    tabs = st.tabs(list(TAB_NAMES))

    with tabs[0]:
        _render_stack_health_tab(gateway_url, args.gateway_timeout_sec)
    with tabs[1]:
        _render_run_explorer_tab(sources)
    with tabs[2]:
        _render_latest_metrics_tab(runs_dir, sources)
    with tabs[3]:
        _render_safe_actions_tab(runs_dir)


def main(argv: list[str] | None = None) -> int:
    args = parse_panel_args(argv)
    render_panel(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
