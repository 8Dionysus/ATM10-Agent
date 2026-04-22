from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from src.agent_core.host_profiles import FEDORA_LOCAL_DEV_PROFILE_ID
from src.agent_core.readiness_scopes import DEV_COMPANION_SCOPE

FEDORA_COMPANION_MILESTONE_RECEIPT_SCHEMA = "fedora_companion_milestone_receipt_v1"

_BASE_REQUIRED_CHECKS = (
    "fedora_local_dev_profile_declared",
    "dev_companion_readiness_scope",
    "startup_delegates_to_product_launcher",
    "manual_capture_target_configured",
    "session_probe_non_error",
    "readiness_evaluation_ok",
    "managed_pilot_runtime_declared",
    "managed_voice_runtime_declared",
    "managed_tts_runtime_declared",
    "automation_dry_run_boundary",
)
_INSTANCE_PATH_CHECK = "atm10_instance_path_known"

_UNSAFE_AUTOMATION_FLAGS = {
    "--execute",
    "--real-input",
    "--unsafe",
    "--unsafe-input",
    "--supervised-input",
}


def parse_capture_region(value: str | Sequence[int] | None) -> list[int] | None:
    """Parse x,y,w,h capture geometry into an integer bbox list."""

    if value is None:
        return None
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
    else:
        parts = [str(part).strip() for part in value]
    if len(parts) != 4:
        return None
    try:
        parsed = [int(part) for part in parts]
    except Exception:
        return None
    return parsed


def _command(startup_payload: Mapping[str, Any]) -> list[str]:
    value = startup_payload.get("command")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _contains_product_launcher(command: Sequence[str]) -> bool:
    for item in command:
        normalized = str(item).replace("\\", "/")
        if normalized.endswith("scripts/start_operator_product.py"):
            return True
    return False


def _capture_bbox_is_valid(value: Any) -> bool:
    bbox = parse_capture_region(value)
    if bbox is None:
        return False
    _x, _y, width, height = bbox
    return width > 0 and height > 0


def _capture_configured(session_probe: Mapping[str, Any]) -> bool:
    kind = str(session_probe.get("capture_target_kind") or "unknown").strip().lower()
    if kind == "region":
        return _capture_bbox_is_valid(session_probe.get("capture_bbox"))
    return kind in {"monitor", "desktop", "window"}


def _instance_path_known(instance_discovery_report: Mapping[str, Any] | None) -> bool:
    if not instance_discovery_report:
        return False
    paths = instance_discovery_report.get("paths")
    if not isinstance(paths, Mapping):
        return False
    atm10_dir = str(paths.get("atm10_dir") or "").strip()
    return bool(atm10_dir)


def _instance_path_exists(instance_discovery_report: Mapping[str, Any] | None) -> bool:
    if not instance_discovery_report:
        return False
    exists = instance_discovery_report.get("exists")
    if not isinstance(exists, Mapping):
        return False
    return bool(exists.get("atm10_dir"))


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _recommended_actions(blocking: Sequence[str], warnings: Sequence[str]) -> list[str]:
    codes = set(blocking) | set(warnings)
    actions: list[str] = []
    if "startup_host_profile_mismatch" in codes:
        actions.append("launch_with_fedora_local_dev_profile")
    if "readiness_scope_mismatch" in codes:
        actions.append("evaluate_with_dev_companion_readiness_scope")
    if "startup_launcher_not_canonical" in codes:
        actions.append("delegate_to_scripts_start_operator_product")
    if "capture_target_unconfigured" in codes:
        actions.append("set_manual_capture_region_or_monitor")
    if "session_probe_error" in codes:
        actions.append("inspect_linux_manual_session_probe")
    if "readiness_evaluation_not_ok" in codes:
        actions.append("resolve_readiness_blocking_reason_codes")
    if "managed_runtime_flag_missing" in codes:
        actions.append("print_command_with_managed_voice_tts_and_pilot_runtimes")
    if "unsafe_automation_flag_present" in codes:
        actions.append("remove_runtime_flags_that_bypass_dry_run_boundary")
    if "atm10_instance_path_missing" in codes:
        actions.append("set_ATM10_DIR_or_place_ATM10_under_a_scanned_launcher_root")
    if "atm10_instance_path_not_existing" in codes:
        actions.append("point_ATM10_DIR_to_an_existing_instance_directory")
    return _dedupe(actions)


def evaluate_fedora_companion_milestone(
    *,
    startup_payload: Mapping[str, Any],
    session_probe: Mapping[str, Any],
    readiness_evaluation: Mapping[str, Any],
    instance_discovery_report: Mapping[str, Any] | None = None,
    artifact_paths: Mapping[str, str | Path] | None = None,
    require_instance_path: bool = True,
    require_instance_exists: bool = False,
) -> dict[str, Any]:
    """Evaluate whether a local Fedora companion run has enough milestone evidence.

    This is a development-companion receipt, not a Fedora ATM10 product-edge
    support claim. It verifies the portable-core seam: explicit Fedora profile,
    manual capture, non-error Linux session probe, dev-companion readiness, and
    dry-run-preserving startup posture.
    """

    command = _command(startup_payload)
    required_checks = list(_BASE_REQUIRED_CHECKS)
    skipped_checks: list[str] = []
    if require_instance_path:
        required_checks.append(_INSTANCE_PATH_CHECK)
    else:
        skipped_checks.append(_INSTANCE_PATH_CHECK)

    satisfied: list[str] = []
    blocking: list[str] = []
    warnings: list[str] = []

    startup_profile = str(startup_payload.get("host_profile") or "")
    readiness_profile = str(readiness_evaluation.get("host_profile_id") or "")
    if startup_profile == FEDORA_LOCAL_DEV_PROFILE_ID and readiness_profile == FEDORA_LOCAL_DEV_PROFILE_ID:
        satisfied.append("fedora_local_dev_profile_declared")
    else:
        blocking.append("startup_host_profile_mismatch")

    startup_scope = str(startup_payload.get("readiness_scope") or "")
    readiness_scope = str(readiness_evaluation.get("readiness_scope") or "")
    if startup_scope == DEV_COMPANION_SCOPE and readiness_scope == DEV_COMPANION_SCOPE:
        satisfied.append("dev_companion_readiness_scope")
    else:
        blocking.append("readiness_scope_mismatch")

    if _contains_product_launcher(command):
        satisfied.append("startup_delegates_to_product_launcher")
    else:
        blocking.append("startup_launcher_not_canonical")

    if _capture_configured(session_probe):
        satisfied.append("manual_capture_target_configured")
    else:
        blocking.append("capture_target_unconfigured")

    if str(session_probe.get("status") or "").strip().lower() != "error":
        satisfied.append("session_probe_non_error")
    else:
        blocking.append("session_probe_error")

    readiness_blocking = readiness_evaluation.get("blocking_reason_codes")
    readiness_blocking = readiness_blocking if isinstance(readiness_blocking, list) else []
    if str(readiness_evaluation.get("status") or "").strip().lower() == "ok" and not readiness_blocking:
        satisfied.append("readiness_evaluation_ok")
    else:
        blocking.append("readiness_evaluation_not_ok")

    for flag, check_name in [
        ("--start-pilot-runtime", "managed_pilot_runtime_declared"),
        ("--start-voice-runtime", "managed_voice_runtime_declared"),
        ("--start-tts-runtime", "managed_tts_runtime_declared"),
    ]:
        if flag in command:
            satisfied.append(check_name)
        else:
            blocking.append("managed_runtime_flag_missing")

    if any(flag in command for flag in _UNSAFE_AUTOMATION_FLAGS):
        blocking.append("unsafe_automation_flag_present")
    else:
        satisfied.append("automation_dry_run_boundary")

    if require_instance_path:
        if _instance_path_known(instance_discovery_report):
            satisfied.append(_INSTANCE_PATH_CHECK)
        else:
            blocking.append("atm10_instance_path_missing")
    if require_instance_exists and not _instance_path_exists(instance_discovery_report):
        blocking.append("atm10_instance_path_not_existing")

    if session_probe.get("reason_codes"):
        warnings.extend(str(code) for code in session_probe.get("reason_codes") if str(code).strip())
    if readiness_evaluation.get("warning_reason_codes"):
        warnings.extend(str(code) for code in readiness_evaluation.get("warning_reason_codes") if str(code).strip())

    blocking = _dedupe(blocking)
    warnings = [code for code in _dedupe(warnings) if code not in blocking]
    status = "ok" if not blocking else "attention"

    return {
        "schema_version": FEDORA_COMPANION_MILESTONE_RECEIPT_SCHEMA,
        "status": status,
        "host_profile": FEDORA_LOCAL_DEV_PROFILE_ID,
        "readiness_scope": DEV_COMPANION_SCOPE,
        "required_checks": required_checks,
        "satisfied_checks": _dedupe(satisfied),
        "skipped_checks": skipped_checks,
        "blocking_reason_codes": blocking,
        "warning_reason_codes": warnings,
        "recommended_actions": _recommended_actions(blocking, warnings),
        "artifact_paths": {key: str(value) for key, value in dict(artifact_paths or {}).items()},
        "notes": [
            "Fedora companion milestone evidence is development-scope only.",
            "Windows ATM10 product-edge support remains a separate acceptance boundary.",
        ],
    }
