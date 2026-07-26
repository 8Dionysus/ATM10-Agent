from __future__ import annotations

from pathlib import Path
import re

import atm10_agent


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_installable_package_is_the_only_source_package() -> None:
    assert atm10_agent.__version__
    assert (REPO_ROOT / "pyproject.toml").is_file()
    assert (REPO_ROOT / "src" / "atm10_agent" / "app.py").is_file()
    assert (REPO_ROOT / "src" / "atm10_agent" / "action" / "__init__.py").is_file()
    assert (REPO_ROOT / "src" / "atm10_agent" / "evals" / "__init__.py").is_file()
    assert (REPO_ROOT / "src" / "atm10_agent" / "memory" / "model.py").is_file()
    assert (REPO_ROOT / "src" / "atm10_agent" / "world" / "knowledge.py").is_file()
    assert not (REPO_ROOT / "src" / "__init__.py").exists()


def test_production_python_has_no_repository_path_injection() -> None:
    pattern = re.compile(r"sys\.path\.(?:insert|append)")
    for root in (REPO_ROOT / "src", REPO_ROOT / "scripts"):
        for path in root.rglob("*.py"):
            assert pattern.search(path.read_text(encoding="utf-8")) is None, path


def test_old_src_namespace_is_not_imported() -> None:
    pattern = re.compile(r"^\s*(?:from|import)\s+src(?:\.|\s|$)", re.MULTILINE)
    for root in (REPO_ROOT / "src", REPO_ROOT / "scripts", REPO_ROOT / "tests"):
        for path in root.rglob("*.py"):
            assert pattern.search(path.read_text(encoding="utf-8")) is None, path


def test_product_package_never_imports_the_scripts_shell() -> None:
    pattern = re.compile(r"^\s*(?:from|import)\s+scripts(?:\.|\s|$)", re.MULTILINE)
    for path in (REPO_ROOT / "src" / "atm10_agent").rglob("*.py"):
        assert pattern.search(path.read_text(encoding="utf-8")) is None, path


def test_retired_action_and_control_plane_runners_are_absent() -> None:
    retired = (
        "automation_dry_run.py",
        "automation_intent_chain_smoke.py",
        "intent_to_automation_plan.py",
        "gateway_v1_local.py",
        "gateway_v1_http_service.py",
        "pilot_runtime_loop.py",
        "start_operator_product.py",
        "streamlit_operator_panel.py",
    )
    for name in retired:
        assert not (REPO_ROOT / "scripts" / name).exists(), name


def test_windows_capture_is_package_owned_and_import_safe() -> None:
    capture_module = (
        REPO_ROOT / "src" / "atm10_agent" / "perception" / "windows_capture.py"
    )
    assert capture_module.is_file()
    text = capture_module.read_text(encoding="utf-8")
    assert "import dxcam" in text
    assert text.index("def _get_dxcam_camera") < text.index("import dxcam")
