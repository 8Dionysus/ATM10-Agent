from __future__ import annotations

from pathlib import Path

from src.agent_core.host_profiles import DEFAULT_HOST_PROFILE_ID, FEDORA_LOCAL_DEV_PROFILE_ID
from src.agent_core.windows_product_edge_contract import (
    evaluate_windows_dependency_boundary,
    evaluate_windows_product_edge_contract,
    evaluate_windows_product_edge_profile,
)


def test_default_profile_remains_windows_product_edge_contract() -> None:
    payload = evaluate_windows_product_edge_profile(DEFAULT_HOST_PROFILE_ID)

    assert payload["status"] == "ok"
    assert payload["blocking_reason_codes"] == []
    assert payload["session_probe_backend_for_win32"] == "windows_win32"
    assert "preferred_capture_backend_dxcam_dxgi" in payload["satisfied_checks"]


def test_fedora_profile_is_not_accidentally_product_edge_contract() -> None:
    payload = evaluate_windows_product_edge_profile(FEDORA_LOCAL_DEV_PROFILE_ID)

    assert payload["status"] == "attention"
    assert "default_profile_mismatch" in payload["blocking_reason_codes"]
    assert "os_family_not_windows" in payload["blocking_reason_codes"]
    assert "preferred_capture_backend_not_dxcam_dxgi" in payload["blocking_reason_codes"]


def test_windows_dependency_boundary_keeps_dxcam_out_of_portable_core(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("-r requirements-win-edge.txt\n", encoding="utf-8")
    (tmp_path / "requirements-win-edge.txt").write_text("-r requirements-core.txt\ndxcam>=0.0.5\n", encoding="utf-8")
    (tmp_path / "requirements-core.txt").write_text("fastapi\n", encoding="utf-8")

    payload = evaluate_windows_dependency_boundary(tmp_path)

    assert payload["status"] == "ok"
    assert set(payload["required_checks"]) <= set(payload["satisfied_checks"])


def test_windows_dependency_boundary_blocks_dxcam_in_core(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("-r requirements-win-edge.txt\n", encoding="utf-8")
    (tmp_path / "requirements-win-edge.txt").write_text("-r requirements-core.txt\ndxcam>=0.0.5\n", encoding="utf-8")
    (tmp_path / "requirements-core.txt").write_text("fastapi\ndxcam\n", encoding="utf-8")

    payload = evaluate_windows_dependency_boundary(tmp_path)

    assert payload["status"] == "attention"
    assert "portable_core_contains_dxcam" in payload["blocking_reason_codes"]


def test_combined_windows_product_edge_contract_can_check_repo_files() -> None:
    payload = evaluate_windows_product_edge_contract(repo_root=Path("."))

    assert payload["status"] == "ok"
    assert payload["profile_contract"]["status"] == "ok"
    assert payload["dependency_contract"]["status"] == "ok"
