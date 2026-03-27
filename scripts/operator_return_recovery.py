from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

GATEWAY_OPERATOR_RETURN_EVENT_SCHEMA = "gateway_operator_return_event_v1"
GATEWAY_OPERATOR_RETURN_SUMMARY_SCHEMA = "gateway_operator_return_summary_v1"
OPERATOR_RETURN_REASON_CATALOG_SCHEMA = "operator_return_reason_catalog_v1"

SAFE_STOP_AFTER_DEFAULT = 2

ALLOWED_RETURN_SAFE_ACTIONS = (
    "gateway_local_core",
    "gateway_http_core",
    "gateway_http_combo_a",
    "cross_service_suite_smoke",
    "cross_service_suite_combo_a_smoke",
    "gateway_sla_operating_cycle_smoke",
    "combo_a_operating_cycle_smoke",
)

RETURN_REASON_CATALOG: dict[str, dict[str, Any]] = {
    "startup_checkpoint_failed": {
        "surface": "startup",
        "default_return_mode": "restart_surface",
        "default_severity": "degraded",
        "recommended_safe_actions": ["gateway_http_core"],
        "triage_hint": "Review the latest startup checkpoint and restart the operator surface from the launcher.",
    },
    "gateway_snapshot_not_ready": {
        "surface": "gateway",
        "default_return_mode": "reprobe",
        "default_severity": "attention",
        "recommended_safe_actions": ["gateway_http_core", "gateway_local_core"],
        "triage_hint": "Re-probe the gateway operator snapshot and inspect the latest startup and gateway artifacts.",
    },
    "service_probe_attention": {
        "surface": "services",
        "default_return_mode": "reprobe",
        "default_severity": "attention",
        "recommended_safe_actions": ["gateway_http_core"],
        "triage_hint": "Re-probe the affected runtime service and inspect the managed service log before continuing.",
    },
    "combo_a_not_ready": {
        "surface": "combo_a",
        "default_return_mode": "rerun_smoke",
        "default_severity": "attention",
        "recommended_safe_actions": ["gateway_http_combo_a", "combo_a_operating_cycle_smoke"],
        "triage_hint": "Refresh Combo A evidence with the existing smoke-only operator actions.",
    },
    "pilot_grounding_degraded": {
        "surface": "pilot_runtime",
        "default_return_mode": "reground",
        "default_severity": "degraded",
        "recommended_safe_actions": ["gateway_http_combo_a", "cross_service_suite_combo_a_smoke"],
        "triage_hint": "Reground the pilot against the latest pilot turn and Combo A smoke evidence before trusting the next reply.",
    },
    "pilot_transcript_low_signal": {
        "surface": "last_turn",
        "default_return_mode": "reground",
        "default_severity": "attention",
        "recommended_safe_actions": ["cross_service_suite_combo_a_smoke"],
        "triage_hint": "Use the latest pilot turn and smoke evidence to recover from low-signal pilot grounding.",
    },
    "safe_action_repeat_failure": {
        "surface": "safe_actions",
        "default_return_mode": "reroute_operator",
        "default_severity": "critical",
        "recommended_safe_actions": ["gateway_sla_operating_cycle_smoke"],
        "triage_hint": "Stop repeating the same safe action and reroute the operator through the governance surface.",
    },
    "streamlit_surface_unavailable": {
        "surface": "streamlit",
        "default_return_mode": "restart_surface",
        "default_severity": "attention",
        "recommended_safe_actions": ["gateway_http_core"],
        "triage_hint": "Restart the Streamlit operator surface and inspect the launcher logs before resuming.",
    },
    "pilot_runtime_not_ready": {
        "surface": "pilot_runtime",
        "default_return_mode": "restart_surface",
        "default_severity": "degraded",
        "recommended_safe_actions": ["gateway_http_combo_a", "cross_service_suite_combo_a_smoke"],
        "triage_hint": "Restart the pilot runtime surface and verify the latest pilot runtime status before resuming.",
    },
    "pilot_runtime_exited": {
        "surface": "pilot_runtime",
        "default_return_mode": "safe_stop",
        "default_severity": "critical",
        "recommended_safe_actions": ["gateway_http_combo_a", "cross_service_suite_combo_a_smoke"],
        "triage_hint": "The managed pilot runtime exited unexpectedly. Stop and reground from the latest pilot artifacts.",
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc_timestamp(raw_value: Any) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "file not found"
    except json.JSONDecodeError as exc:
        return None, f"failed to parse JSON: {exc}"
    except Exception as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "JSON root must be object"
    return payload, None


def return_paths(root: Path) -> dict[str, str]:
    base = Path(root) / "return"
    return {
        "latest_return_event_json": str(base / "latest_return_event.json"),
        "return_events_jsonl": str(base / "return_events.jsonl"),
    }


def compose_anchor_ref(
    *,
    artifact_kind: str,
    ref: str,
    label: str | None = None,
    required: bool = True,
    ref_type: str = "path",
) -> dict[str, Any]:
    payload = {
        "artifact_kind": str(artifact_kind).strip(),
        "ref": str(ref).strip(),
        "ref_type": str(ref_type).strip() or "path",
        "required": bool(required),
    }
    if label is not None and str(label).strip():
        payload["label"] = str(label).strip()
    return payload


def existing_anchor_refs(anchor_refs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in anchor_refs:
        if not isinstance(item, Mapping):
            continue
        ref = str(item.get("ref", "")).strip()
        if not ref:
            continue
        ref_type = str(item.get("ref_type", "path")).strip().lower() or "path"
        if ref_type == "path" and not Path(ref).exists():
            continue
        normalized.append(
            compose_anchor_ref(
                artifact_kind=str(item.get("artifact_kind", "")).strip() or "artifact",
                ref=ref,
                label=str(item.get("label", "")).strip() or None,
                required=bool(item.get("required", True)),
                ref_type=ref_type,
            )
        )
    return normalized


def build_reason_catalog_payload() -> dict[str, Any]:
    return {
        "schema_version": OPERATOR_RETURN_REASON_CATALOG_SCHEMA,
        "generated_at_utc": _utc_now(),
        "safe_stop_after_default": SAFE_STOP_AFTER_DEFAULT,
        "allowed_safe_actions": list(ALLOWED_RETURN_SAFE_ACTIONS),
        "reasons": [
            {
                "reason_code": reason_code,
                "surface": definition["surface"],
                "default_return_mode": definition["default_return_mode"],
                "default_severity": definition["default_severity"],
                "recommended_safe_actions": list(definition["recommended_safe_actions"]),
                "triage_hint": definition["triage_hint"],
            }
            for reason_code, definition in sorted(RETURN_REASON_CATALOG.items())
        ],
    }


def recommended_safe_actions_for_reason(reason_code: str) -> list[str]:
    definition = RETURN_REASON_CATALOG.get(str(reason_code).strip())
    if definition is None:
        return []
    return [
        action_key
        for action_key in definition.get("recommended_safe_actions", [])
        if isinstance(action_key, str) and action_key in ALLOWED_RETURN_SAFE_ACTIONS
    ]


def reset_return_loop_state(
    *,
    suppress_first_occurrence: bool,
    safe_stop_after: int = SAFE_STOP_AFTER_DEFAULT,
) -> dict[str, Any]:
    return {
        "last_reason_code": None,
        "occurrence_count": 0,
        "emitted_count": 0,
        "safe_stop_after": int(max(safe_stop_after, 1)),
        "suppress_first_occurrence": bool(suppress_first_occurrence),
    }


def advance_return_loop_state(
    loop_state: Mapping[str, Any] | None,
    *,
    reason_code: str,
    suppress_first_occurrence: bool,
    safe_stop_after: int = SAFE_STOP_AFTER_DEFAULT,
) -> tuple[dict[str, Any], bool, int, str]:
    previous = dict(loop_state or {})
    previous_reason = str(previous.get("last_reason_code", "")).strip()
    previous_count = int(previous.get("occurrence_count") or 0)
    occurrence_count = previous_count + 1 if previous_reason == reason_code else 1
    emission_offset = 1 if suppress_first_occurrence else 0
    emitted_count = max(0, occurrence_count - emission_offset)
    should_emit = emitted_count > 0
    normalized_safe_stop_after = int(max(safe_stop_after, 1))
    event_status = "safe_stop" if should_emit and emitted_count >= normalized_safe_stop_after else "open"
    return {
        "last_reason_code": reason_code,
        "occurrence_count": occurrence_count,
        "emitted_count": emitted_count,
        "safe_stop_after": normalized_safe_stop_after,
        "suppress_first_occurrence": bool(suppress_first_occurrence),
    }, should_emit, emitted_count, event_status


def build_return_event(
    *,
    reason_code: str,
    anchor_refs: Sequence[Mapping[str, Any]],
    status: str,
    loop_count: int,
    safe_stop_after: int,
    surface: str | None = None,
    severity: str | None = None,
    return_mode: str | None = None,
    operator_visible: bool = True,
    recommended_safe_actions: Sequence[str] | None = None,
    triage_hint: str | None = None,
    details: Mapping[str, Any] | None = None,
    timestamp_utc: str | None = None,
) -> dict[str, Any]:
    definition = RETURN_REASON_CATALOG.get(str(reason_code).strip(), {})
    safe_actions = (
        list(recommended_safe_actions)
        if recommended_safe_actions is not None
        else recommended_safe_actions_for_reason(reason_code)
    )
    return {
        "schema_version": GATEWAY_OPERATOR_RETURN_EVENT_SCHEMA,
        "event_id": f"return-{uuid4().hex[:12]}",
        "timestamp_utc": timestamp_utc or _utc_now(),
        "status": str(status).strip(),
        "surface": str(surface or definition.get("surface") or "startup").strip(),
        "reason_code": str(reason_code).strip(),
        "severity": str(severity or definition.get("default_severity") or "attention").strip(),
        "return_mode": str(return_mode or definition.get("default_return_mode") or "reprobe").strip(),
        "operator_visible": bool(operator_visible),
        "anchor_refs": existing_anchor_refs(anchor_refs),
        "recommended_safe_actions": [
            action_key for action_key in safe_actions if action_key in ALLOWED_RETURN_SAFE_ACTIONS
        ],
        "triage_hint": str(triage_hint or definition.get("triage_hint") or "").strip() or None,
        "loop_count": int(max(loop_count, 0)),
        "safe_stop_after": int(max(safe_stop_after, 1)),
        "details": dict(details or {}),
    }


def append_return_event(root: Path, event_payload: Mapping[str, Any]) -> dict[str, str]:
    paths = return_paths(root)
    latest_event_path = Path(paths["latest_return_event_json"])
    events_log_path = Path(paths["return_events_jsonl"])
    normalized_payload = dict(event_payload)
    _write_json(latest_event_path, normalized_payload)
    _append_jsonl(events_log_path, normalized_payload)
    return paths


def _iter_operator_startup_run_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        [
            path
            for path in root.iterdir()
            if path.is_dir() and "-start-operator-product" in path.name
        ],
        reverse=True,
    )


def _resolve_startup_return_surface(operator_runs_dir: Path) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    for run_dir in _iter_operator_startup_run_dirs(Path(operator_runs_dir)):
        run_payload, load_error = load_json_object(run_dir / "run.json")
        if run_payload is None or load_error is not None:
            continue
        event_payload = run_payload.get("last_return_event")
        if not isinstance(event_payload, dict):
            continue
        paths_payload = return_paths(run_dir)
        return dict(event_payload), paths_payload
    return None, None


def resolve_pilot_runs_dir(operator_runs_dir: Path) -> Path:
    for run_dir in _iter_operator_startup_run_dirs(Path(operator_runs_dir)):
        run_payload, load_error = load_json_object(run_dir / "run.json")
        if run_payload is None or load_error is not None:
            continue
        pilot_runs_dir = (
            run_payload.get("artifact_roots", {})
            if isinstance(run_payload.get("artifact_roots"), Mapping)
            else {}
        )
        value = str(pilot_runs_dir.get("pilot_runtime_runs_dir", "")).strip()
        if value:
            return Path(value)
    return Path(operator_runs_dir) / "pilot-runtime"


def _resolve_pilot_return_surface(pilot_runs_dir: Path) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    status_payload, load_error = load_json_object(Path(pilot_runs_dir) / "pilot_runtime_status_latest.json")
    if status_payload is None or load_error is not None:
        return None, None
    event_payload = status_payload.get("last_return_event")
    if not isinstance(event_payload, dict):
        return None, None
    return dict(event_payload), return_paths(pilot_runs_dir)


def load_returning_surface(
    *,
    operator_runs_dir: Path,
    pilot_runs_dir: Path | None = None,
) -> dict[str, Any] | None:
    effective_operator_runs_dir = Path(operator_runs_dir)
    effective_pilot_runs_dir = Path(pilot_runs_dir) if pilot_runs_dir is not None else resolve_pilot_runs_dir(
        effective_operator_runs_dir
    )
    surfaces: list[dict[str, Any]] = []
    startup_event, startup_paths = _resolve_startup_return_surface(effective_operator_runs_dir)
    if startup_event is not None and startup_paths is not None:
        surfaces.append({"source": "startup", "event": startup_event, "paths": startup_paths})
    pilot_event, pilot_paths = _resolve_pilot_return_surface(effective_pilot_runs_dir)
    if pilot_event is not None and pilot_paths is not None:
        surfaces.append({"source": "pilot_runtime", "event": pilot_event, "paths": pilot_paths})
    return build_return_summary(surfaces)


def build_return_summary(surfaces: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    normalized_surfaces: list[dict[str, Any]] = []
    for item in surfaces:
        if not isinstance(item, Mapping):
            continue
        event_payload = item.get("event")
        paths_payload = item.get("paths")
        if not isinstance(event_payload, Mapping) or not isinstance(paths_payload, Mapping):
            continue
        normalized_surfaces.append(
            {
                "source": str(item.get("source", "")).strip() or "unknown",
                "event": dict(event_payload),
                "paths": {
                    "latest_return_event_json": str(paths_payload.get("latest_return_event_json", "")).strip() or None,
                    "return_events_jsonl": str(paths_payload.get("return_events_jsonl", "")).strip() or None,
                },
                "timestamp": _parse_utc_timestamp(event_payload.get("timestamp_utc")),
            }
        )
    if not normalized_surfaces:
        return None

    normalized_surfaces.sort(
        key=lambda item: item.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    active_surfaces = [
        item
        for item in normalized_surfaces
        if str(item["event"].get("status", "")).strip() in {"open", "safe_stop"}
    ]
    if not active_surfaces:
        return None

    latest = active_surfaces[0]
    latest_event = dict(latest["event"])
    latest_status = str(latest_event.get("status", "")).strip()
    latest_severity = str(latest_event.get("severity", "")).strip()
    if latest_status == "safe_stop":
        summary_status = "safe_stop"
    elif latest_severity in {"degraded", "critical"}:
        summary_status = "degraded"
    else:
        summary_status = "attention"

    recommended_safe_actions: list[str] = []
    recent_reason_codes: list[str] = []
    for item in active_surfaces:
        reason_code = str(item["event"].get("reason_code", "")).strip()
        if reason_code and reason_code not in recent_reason_codes:
            recent_reason_codes.append(reason_code)
        for action_key in item["event"].get("recommended_safe_actions", []):
            if action_key in ALLOWED_RETURN_SAFE_ACTIONS and action_key not in recommended_safe_actions:
                recommended_safe_actions.append(action_key)

    triage_hint = str(latest_event.get("triage_hint", "")).strip()
    if recommended_safe_actions:
        next_step_code = "run_safe_action"
        next_step = triage_hint or f"Run safe action {recommended_safe_actions[0]} from the gateway operator surface."
    elif latest_status == "safe_stop":
        next_step_code = "safe_stop"
        next_step = triage_hint or "Safe stop reached. Inspect the latest anchors before resuming."
    else:
        next_step_code = "inspect_anchor"
        next_step = triage_hint or "Inspect the latest recovery anchors before resuming."

    latest_event["recommended_safe_actions"] = [
        action_key
        for action_key in latest_event.get("recommended_safe_actions", [])
        if action_key in ALLOWED_RETURN_SAFE_ACTIONS
    ]
    return {
        "schema_version": GATEWAY_OPERATOR_RETURN_SUMMARY_SCHEMA,
        "status": summary_status,
        "open_event_count": len(active_surfaces),
        "latest_event": latest_event,
        "recommended_safe_actions": recommended_safe_actions,
        "recent_reason_codes": recent_reason_codes,
        "next_step_code": next_step_code,
        "next_step": next_step,
        "paths": latest["paths"],
        "warnings": [],
    }
