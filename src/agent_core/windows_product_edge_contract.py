from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from src.agent_core.atm10_session_probe import select_session_probe_backend_id
from src.agent_core.host_profiles import DEFAULT_HOST_PROFILE_ID, host_profile_payload
from src.agent_core.readiness_scopes import PRODUCT_EDGE_SCOPE

WINDOWS_PRODUCT_EDGE_CONTRACT_SCHEMA = "windows_product_edge_contract_v1"
WINDOWS_DEPENDENCY_BOUNDARY_SCHEMA = "windows_dependency_boundary_v1"


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _finish(payload: dict[str, Any], blocking: list[str], warnings: list[str] | None = None) -> dict[str, Any]:
    blocking = _dedupe(blocking)
    warnings = _dedupe(warnings or [])
    payload["blocking_reason_codes"] = blocking
    payload["warning_reason_codes"] = [item for item in warnings if item not in blocking]
    payload["status"] = "ok" if not blocking else "attention"
    return payload


def evaluate_windows_product_edge_profile(profile_id: str | None = DEFAULT_HOST_PROFILE_ID) -> dict[str, Any]:
    """Validate that a host profile still represents the Windows ATM10 edge."""

    profile = host_profile_payload(profile_id or DEFAULT_HOST_PROFILE_ID)
    host = profile.get("host")
    host = host if isinstance(host, Mapping) else {}
    capabilities = profile.get("capabilities")
    capabilities = capabilities if isinstance(capabilities, Mapping) else {}
    backend = select_session_probe_backend_id(platform_name="win32")

    required_checks = [
        "default_profile_is_windows_edge",
        "os_family_windows",
        "readiness_scope_product_edge",
        "window_identity_win32_atm10_window",
        "preferred_capture_backend_dxcam_dxgi",
        "win32_session_probe_backend_selected",
        "window_session_probe_supported",
    ]
    satisfied: list[str] = []
    blocking: list[str] = []

    if profile.get("id") == DEFAULT_HOST_PROFILE_ID:
        satisfied.append("default_profile_is_windows_edge")
    else:
        blocking.append("default_profile_mismatch")

    if host.get("os_family") == "windows":
        satisfied.append("os_family_windows")
    else:
        blocking.append("os_family_not_windows")

    if host.get("readiness_scope") == PRODUCT_EDGE_SCOPE:
        satisfied.append("readiness_scope_product_edge")
    else:
        blocking.append("readiness_scope_not_product_edge")

    if host.get("window_identity_mode") == "win32_atm10_window":
        satisfied.append("window_identity_win32_atm10_window")
    else:
        blocking.append("window_identity_not_win32_atm10")

    if profile.get("preferred_capture_backend") == "dxcam_dxgi":
        satisfied.append("preferred_capture_backend_dxcam_dxgi")
    else:
        blocking.append("preferred_capture_backend_not_dxcam_dxgi")

    if backend == "windows_win32":
        satisfied.append("win32_session_probe_backend_selected")
    else:
        blocking.append("win32_session_probe_backend_not_selected")

    if bool(capabilities.get("supports_window_session_probe")):
        satisfied.append("window_session_probe_supported")
    else:
        blocking.append("window_session_probe_not_supported")

    return _finish(
        {
            "schema_version": WINDOWS_PRODUCT_EDGE_CONTRACT_SCHEMA,
            "profile_id": profile.get("id"),
            "required_checks": required_checks,
            "satisfied_checks": satisfied,
            "session_probe_backend_for_win32": backend,
            "profile": profile,
        },
        blocking=blocking,
    )


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def evaluate_windows_dependency_boundary(repo_root: str | Path = ".") -> dict[str, Any]:
    """Check that Windows-only edge dependencies stay outside portable core."""

    root = Path(repo_root)
    requirements_txt = _read_text(root / "requirements.txt")
    win_edge_txt = _read_text(root / "requirements-win-edge.txt")
    core_txt = _read_text(root / "requirements-core.txt")

    required_checks = [
        "requirements_txt_points_to_windows_edge",
        "windows_edge_contains_dxcam",
        "portable_core_does_not_contain_dxcam",
    ]
    satisfied: list[str] = []
    blocking: list[str] = []

    if requirements_txt is None:
        blocking.append("requirements_txt_missing")
    elif "requirements-win-edge.txt" in requirements_txt:
        satisfied.append("requirements_txt_points_to_windows_edge")
    else:
        blocking.append("requirements_txt_missing_windows_edge_include")

    if win_edge_txt is None:
        blocking.append("requirements_win_edge_missing")
    elif "dxcam" in win_edge_txt.lower():
        satisfied.append("windows_edge_contains_dxcam")
    else:
        blocking.append("windows_edge_missing_dxcam")

    if core_txt is None:
        blocking.append("requirements_core_missing")
    elif "dxcam" not in core_txt.lower():
        satisfied.append("portable_core_does_not_contain_dxcam")
    else:
        blocking.append("portable_core_contains_dxcam")

    return _finish(
        {
            "schema_version": WINDOWS_DEPENDENCY_BOUNDARY_SCHEMA,
            "repo_root": str(root),
            "required_checks": required_checks,
            "satisfied_checks": satisfied,
        },
        blocking=blocking,
    )


def evaluate_windows_product_edge_contract(
    *,
    profile_id: str | None = DEFAULT_HOST_PROFILE_ID,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    profile_contract = evaluate_windows_product_edge_profile(profile_id)
    dependency_contract = None if repo_root is None else evaluate_windows_dependency_boundary(repo_root)
    blocking = list(profile_contract.get("blocking_reason_codes") or [])
    if dependency_contract is not None:
        blocking.extend(str(code) for code in dependency_contract.get("blocking_reason_codes") or [])

    return _finish(
        {
            "schema_version": WINDOWS_PRODUCT_EDGE_CONTRACT_SCHEMA,
            "profile_contract": profile_contract,
            "dependency_contract": dependency_contract,
            "required_checks": [
                "windows_profile_contract_ok",
                "windows_dependency_boundary_ok" if repo_root is not None else "windows_dependency_boundary_not_requested",
            ],
            "satisfied_checks": [
                check
                for check, contract in [
                    ("windows_profile_contract_ok", profile_contract),
                    ("windows_dependency_boundary_ok", dependency_contract),
                ]
                if contract is not None and contract.get("status") == "ok"
            ],
            "notes": [
                "Windows remains the ATM10 product-edge acceptance boundary.",
                "Fedora local development companion evidence does not replace DXGI/Win32 acceptance.",
            ],
        },
        blocking=blocking,
    )
