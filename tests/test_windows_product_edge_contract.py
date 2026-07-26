from __future__ import annotations

from pathlib import Path

from atm10_agent.agent_core.windows_product_edge_contract import (
    evaluate_windows_dependency_boundary,
    evaluate_windows_product_edge,
    evaluate_windows_product_edge_contract,
)


def _write_pyproject(path: Path, *, core: str = "", windows: str = "") -> None:
    path.write_text(
        "[project]\n"
        'name = "fixture"\n'
        'version = "0.0.0"\n'
        f"dependencies = [{core}]\n"
        "[project.optional-dependencies]\n"
        f"windows = [{windows}]\n"
        'dev = ["pytest>=8"]\n',
        encoding="utf-8",
    )


def test_windows_edge_is_machine_profile_free() -> None:
    payload = evaluate_windows_product_edge()
    assert payload["status"] == "ok"
    assert payload["session_probe_backend"] == "windows_win32"
    assert payload["preferred_capture_backend"] == "dxcam_dxgi"
    assert payload["action_mode"] == "dry_run_only"


def test_windows_dependency_boundary_reads_pyproject(tmp_path: Path) -> None:
    _write_pyproject(
        tmp_path / "pyproject.toml",
        windows='"dxcam>=0.3", "numpy>=2", "pillow>=10"',
    )
    payload = evaluate_windows_dependency_boundary(tmp_path)
    assert payload["status"] == "ok"
    assert set(payload["required_checks"]) == set(payload["satisfied_checks"])


def test_windows_dependency_boundary_rejects_core_or_leaked_dxcam(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "fixture"\n'
        'version = "0.0.0"\n'
        'dependencies = ["numpy"]\n'
        "[project.optional-dependencies]\n"
        'windows = ["numpy", "pillow"]\n'
        'dev = ["dxcam"]\n',
        encoding="utf-8",
    )
    payload = evaluate_windows_dependency_boundary(tmp_path)
    assert payload["status"] == "attention"
    assert "core_has_runtime_dependencies" in payload["blocking_reason_codes"]
    assert "windows_extra_missing_dxcam" in payload["blocking_reason_codes"]
    assert "dxcam_leaked_outside_windows_extra" in payload["blocking_reason_codes"]


def test_combined_windows_product_edge_contract_checks_repo_metadata() -> None:
    payload = evaluate_windows_product_edge_contract(repo_root=Path("."))
    assert payload["status"] == "ok"
    assert payload["edge_contract"]["status"] == "ok"
    assert payload["dependency_contract"]["status"] == "ok"
