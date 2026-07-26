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


def test_legacy_action_commands_are_thin_package_wrappers() -> None:
    dry_run = (REPO_ROOT / "scripts" / "automation_dry_run.py").read_text(
        encoding="utf-8"
    )
    intent = (REPO_ROOT / "scripts" / "intent_to_automation_plan.py").read_text(
        encoding="utf-8"
    )

    assert "from atm10_agent.action import build_dry_run_execution, normalize_plan" in dry_run
    assert "from atm10_agent.action import build_plan_from_intent" in intent
    for retired_duplicate in (
        "def _normalize_action(",
        "def _build_execution_plan(",
        "def build_automation_plan_from_intent(",
    ):
        assert retired_duplicate not in dry_run
        assert retired_duplicate not in intent
