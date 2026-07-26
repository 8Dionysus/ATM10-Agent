from __future__ import annotations

from pathlib import Path

WORKFLOW_PATH = Path(".github/workflows/portable-core-linux.yml")


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_portable_core_linux_workflow_exists() -> None:
    assert WORKFLOW_PATH.is_file()


def test_portable_core_linux_workflow_uses_pinned_actions() -> None:
    text = _workflow_text()

    assert "uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd" in text
    assert "uses: actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405" in text


def test_portable_core_linux_workflow_uses_linux_dependency_surface() -> None:
    text = _workflow_text()

    assert "runs-on: ubuntu-latest" in text
    assert "python -m pip install . --no-deps" in text
    assert "requirements-linux-dev.txt" not in text
    assert "pip install -r requirements-dev.txt" not in text
    assert "pip install -r requirements.txt" not in text
    assert "dxcam" not in text.lower()


def test_portable_core_linux_workflow_exercises_installed_package() -> None:
    text = _workflow_text()

    assert "atm10 doctor" in text
    assert "atm10 run" in text
    assert "atm10 eval" in text
    assert "companion-core" in text
    assert "scripts." not in text
    assert "fedora" not in text.lower()
