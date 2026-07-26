"""Pure checks for the first-class Windows ATM10 product edge."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from atm10_agent.agent_core.atm10_session_probe import select_session_probe_backend_id

WINDOWS_PRODUCT_EDGE_CONTRACT_SCHEMA = "windows_product_edge_contract_v2"
WINDOWS_DEPENDENCY_BOUNDARY_SCHEMA = "windows_dependency_boundary_v2"
REQUIRED_WINDOWS_PACKAGES = frozenset({"dxcam", "numpy", "pillow"})


def _dedupe(items: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _finish(
    payload: dict[str, Any],
    blocking: list[str],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    blocking = _dedupe(blocking)
    warnings = _dedupe(warnings or [])
    payload["blocking_reason_codes"] = blocking
    payload["warning_reason_codes"] = [item for item in warnings if item not in blocking]
    payload["status"] = "ok" if not blocking else "attention"
    return payload


def _dependency_name(spec: str) -> str:
    match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)", spec.strip())
    return "" if match is None else match.group(1).lower().replace("_", "-")


def _dependency_names(raw_specs: Any) -> set[str]:
    if not isinstance(raw_specs, list):
        return set()
    return {
        name
        for raw_spec in raw_specs
        if isinstance(raw_spec, str) and (name := _dependency_name(raw_spec))
    }


def evaluate_windows_product_edge() -> dict[str, Any]:
    """Validate stable platform facts without a machine-specific host profile."""

    backend = select_session_probe_backend_id(platform_name="win32")
    blocking = [] if backend == "windows_win32" else ["win32_session_probe_backend_not_selected"]
    return _finish(
        {
            "schema_version": WINDOWS_PRODUCT_EDGE_CONTRACT_SCHEMA,
            "platform": "windows",
            "shell": "pwsh",
            "session_probe_backend": backend,
            "preferred_capture_backend": "dxcam_dxgi",
            "fallback_capture_backend": "pillow_imagegrab",
            "action_mode": "dry_run_only",
            "required_checks": [
                "win32_session_probe_backend_selected",
                "dxcam_first_capture",
                "pillow_fallback_evidence",
                "dry_run_action_fence",
            ],
            "satisfied_checks": (
                [
                    "win32_session_probe_backend_selected",
                    "dxcam_first_capture",
                    "pillow_fallback_evidence",
                    "dry_run_action_fence",
                ]
                if not blocking
                else [
                    "dxcam_first_capture",
                    "pillow_fallback_evidence",
                    "dry_run_action_fence",
                ]
            ),
        },
        blocking,
    )


def evaluate_windows_dependency_boundary(repo_root: str | Path = ".") -> dict[str, Any]:
    """Check Windows extras directly against canonical ``pyproject.toml``."""

    pyproject_path = Path(repo_root) / "pyproject.toml"
    try:
        payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return _finish(
            {
                "schema_version": WINDOWS_DEPENDENCY_BOUNDARY_SCHEMA,
                "pyproject_path": str(pyproject_path),
                "required_checks": [],
                "satisfied_checks": [],
            },
            ["pyproject_unreadable"],
        )

    project = payload.get("project")
    project = project if isinstance(project, Mapping) else {}
    core = _dependency_names(project.get("dependencies"))
    optional = project.get("optional-dependencies")
    optional = optional if isinstance(optional, Mapping) else {}
    windows = _dependency_names(optional.get("windows"))
    non_windows = {
        dependency
        for extra_name, specs in optional.items()
        if extra_name != "windows"
        for dependency in _dependency_names(specs)
    }

    required_checks = [
        "core_dependency_free",
        "windows_extra_complete",
        "dxcam_is_windows_only",
    ]
    satisfied: list[str] = []
    blocking: list[str] = []
    if not core:
        satisfied.append("core_dependency_free")
    else:
        blocking.append("core_has_runtime_dependencies")
    missing_windows = sorted(REQUIRED_WINDOWS_PACKAGES - windows)
    if not missing_windows:
        satisfied.append("windows_extra_complete")
    else:
        blocking.extend(f"windows_extra_missing_{name}" for name in missing_windows)
    if "dxcam" not in core and "dxcam" not in non_windows:
        satisfied.append("dxcam_is_windows_only")
    else:
        blocking.append("dxcam_leaked_outside_windows_extra")

    return _finish(
        {
            "schema_version": WINDOWS_DEPENDENCY_BOUNDARY_SCHEMA,
            "pyproject_path": str(pyproject_path),
            "core_dependencies": sorted(core),
            "windows_dependencies": sorted(windows),
            "required_checks": required_checks,
            "satisfied_checks": satisfied,
        },
        blocking,
    )


def evaluate_windows_product_edge_contract(
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    edge = evaluate_windows_product_edge()
    dependency = (
        None if repo_root is None else evaluate_windows_dependency_boundary(repo_root)
    )
    blocking = list(edge["blocking_reason_codes"])
    if dependency is not None:
        blocking.extend(dependency["blocking_reason_codes"])
    return _finish(
        {
            "schema_version": WINDOWS_PRODUCT_EDGE_CONTRACT_SCHEMA,
            "edge_contract": edge,
            "dependency_contract": dependency,
            "notes": [
                "Windows 11 and PowerShell 7 remain the ATM10 product edge.",
                "Portable Linux evidence does not replace live Win32 and DXGI acceptance.",
            ],
        },
        blocking,
    )
