from __future__ import annotations

from typing import Any, Mapping

from src.agent_core.host_profiles import DEFAULT_HOST_PROFILE_ID, host_profile_payload

HOST_READINESS_EVALUATION_SCHEMA = "host_readiness_evaluation_v1"
PRODUCT_EDGE_SCOPE = "product_edge"
DEV_COMPANION_SCOPE = "dev_companion"
_READINESS_SCOPES = (PRODUCT_EDGE_SCOPE, DEV_COMPANION_SCOPE)
_ALLOWED_DEV_COMPANION_WARNING_CODES = {
    "window_identity_unavailable",
    "manual_capture_source_required",
}


def list_readiness_scopes() -> tuple[str, ...]:
    """Return known readiness policy scopes.

    `product_edge` is the strict Windows/ATM10 acceptance posture.
    `dev_companion` is the preliminary Fedora/Linux companion posture.
    """

    return _READINESS_SCOPES


def normalize_readiness_scope(scope: str | None) -> str:
    resolved = str(scope or PRODUCT_EDGE_SCOPE).strip().lower() or PRODUCT_EDGE_SCOPE
    if resolved not in _READINESS_SCOPES:
        available = ", ".join(_READINESS_SCOPES)
        raise KeyError(f"unknown readiness_scope={resolved!r}; expected one of: {available}")
    return resolved


def _reason_codes(payload: Mapping[str, Any]) -> list[str]:
    value = payload.get("reason_codes")
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _capture_bbox_is_valid(value: Any) -> bool:
    if not isinstance(value, list | tuple):
        return False
    if len(value) != 4:
        return False
    try:
        [int(item) for item in value]
    except Exception:
        return False
    return True


def _capture_target_kind(payload: Mapping[str, Any]) -> str:
    return str(payload.get("capture_target_kind") or "unknown").strip().lower() or "unknown"


def _base_payload(*, readiness_scope: str, session_probe: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": HOST_READINESS_EVALUATION_SCHEMA,
        "readiness_scope": readiness_scope,
        "session_probe_schema_version": session_probe.get("schema_version"),
        "session_probe_status": session_probe.get("status"),
        "required_checks": [],
        "satisfied_checks": [],
        "blocking_reason_codes": [],
        "warning_reason_codes": [],
        "recommended_actions": [],
    }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _recommended_actions(blocking: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    codes = set(blocking + warnings)
    if "session_probe_error" in codes or "platform_not_supported" in codes:
        actions.append("inspect_session_probe_backend")
    if "atm10_window_not_found" in codes:
        actions.append("bring_atm10_or_minecraft_window_into_view")
    if "atm10_not_probable" in codes:
        actions.append("verify_atm10_instance_identity")
    if "atm10_window_not_foreground" in codes:
        actions.append("focus_atm10_window")
    if "capture_target_miss" in codes or "capture_region_missing" in codes or "capture_target_unconfigured" in codes:
        actions.append("configure_capture_region_or_monitor")
    if "window_identity_unavailable" in codes or "manual_capture_source_required" in codes:
        actions.append("confirm_manual_capture_source")
    return _dedupe(actions)


def _finish(payload: dict[str, Any], *, blocking: list[str], warnings: list[str]) -> dict[str, Any]:
    payload["blocking_reason_codes"] = _dedupe(blocking)
    payload["warning_reason_codes"] = _dedupe(warnings)
    payload["recommended_actions"] = _recommended_actions(
        payload["blocking_reason_codes"],
        payload["warning_reason_codes"],
    )
    if not payload["blocking_reason_codes"]:
        payload["status"] = "ok"
    elif "session_probe_error" in payload["blocking_reason_codes"] or "platform_not_supported" in payload["blocking_reason_codes"]:
        payload["status"] = "error"
    else:
        payload["status"] = "attention"
    return payload


def _evaluate_product_edge(session_probe: Mapping[str, Any]) -> dict[str, Any]:
    payload = _base_payload(readiness_scope=PRODUCT_EDGE_SCOPE, session_probe=session_probe)
    required = [
        "session_probe_not_error",
        "atm10_window_found",
        "atm10_probable",
        "atm10_window_foreground",
        "capture_intersects_window_or_unknown",
    ]
    payload["required_checks"] = required
    blocking: list[str] = []
    warnings = _reason_codes(session_probe)

    if str(session_probe.get("status") or "").strip().lower() == "error":
        blocking.append("session_probe_error")
    else:
        payload["satisfied_checks"].append("session_probe_not_error")

    if bool(session_probe.get("window_found")):
        payload["satisfied_checks"].append("atm10_window_found")
    else:
        blocking.append("atm10_window_not_found")

    if bool(session_probe.get("atm10_probable")):
        payload["satisfied_checks"].append("atm10_probable")
    else:
        blocking.append("atm10_not_probable")

    if bool(session_probe.get("foreground")):
        payload["satisfied_checks"].append("atm10_window_foreground")
    else:
        blocking.append("atm10_window_not_foreground")

    if session_probe.get("capture_intersects_window") is False:
        blocking.append("capture_target_miss")
    else:
        payload["satisfied_checks"].append("capture_intersects_window_or_unknown")

    return _finish(payload, blocking=blocking, warnings=warnings)


def _evaluate_dev_companion(session_probe: Mapping[str, Any]) -> dict[str, Any]:
    payload = _base_payload(readiness_scope=DEV_COMPANION_SCOPE, session_probe=session_probe)
    required = [
        "session_probe_not_error",
        "capture_target_configured",
    ]
    payload["required_checks"] = required
    blocking: list[str] = []
    warnings: list[str] = []

    source_reason_codes = _reason_codes(session_probe)
    if str(session_probe.get("status") or "").strip().lower() == "error":
        blocking.append("session_probe_error")
    else:
        payload["satisfied_checks"].append("session_probe_not_error")

    if "platform_not_supported" in source_reason_codes:
        blocking.append("platform_not_supported")

    capture_kind = _capture_target_kind(session_probe)
    if capture_kind == "unknown":
        blocking.append("capture_target_unconfigured")
    elif capture_kind == "region" and not _capture_bbox_is_valid(session_probe.get("capture_bbox")):
        blocking.append("capture_region_missing")
    else:
        payload["satisfied_checks"].append("capture_target_configured")

    for code in source_reason_codes:
        if code in _ALLOWED_DEV_COMPANION_WARNING_CODES:
            warnings.append(code)
        elif code not in blocking:
            warnings.append(code)

    return _finish(payload, blocking=blocking, warnings=warnings)


def evaluate_session_probe_readiness(
    *,
    readiness_scope: str | None,
    session_probe: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate an ATM10 session probe under a named readiness policy.

    The Windows `product_edge` posture requires ATM10 window identity and focus.
    The Fedora/Linux `dev_companion` posture allows manual capture without window
    identity, while still requiring a concrete capture target and a non-error probe.
    """

    scope = normalize_readiness_scope(readiness_scope)
    if scope == PRODUCT_EDGE_SCOPE:
        return _evaluate_product_edge(session_probe)
    if scope == DEV_COMPANION_SCOPE:
        return _evaluate_dev_companion(session_probe)
    raise AssertionError(f"unhandled readiness_scope={scope!r}")


def _profile_payload(profile: str | Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(profile, Mapping):
        return dict(profile)
    return host_profile_payload(profile or DEFAULT_HOST_PROFILE_ID)


def evaluate_host_profile_session_readiness(
    *,
    host_profile: str | Mapping[str, Any] | None,
    session_probe: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate a session probe using the readiness scope declared by a host profile."""

    profile_payload = _profile_payload(host_profile)
    host_payload = profile_payload.get("host")
    host_payload = host_payload if isinstance(host_payload, Mapping) else {}
    evaluation = evaluate_session_probe_readiness(
        readiness_scope=str(host_payload.get("readiness_scope") or PRODUCT_EDGE_SCOPE),
        session_probe=session_probe,
    )
    evaluation["host_profile_id"] = profile_payload.get("id")
    evaluation["host_profile_validation_status"] = profile_payload.get("validation_status")
    evaluation["host_profile_capabilities"] = dict(profile_payload.get("capabilities") or {})
    return evaluation
