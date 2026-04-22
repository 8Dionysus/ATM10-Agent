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
    assert "pip install -r requirements-linux-dev.txt" in text
    assert "pip install -r requirements-dev.txt" not in text
    assert "pip install -r requirements.txt" not in text
    assert "dxcam" not in text.lower()


def test_portable_core_linux_workflow_exercises_wave_contracts() -> None:
    text = _workflow_text()

    assert "tests/test_host_profiles.py" in text
    assert "tests/test_atm10_session_probe_adapters.py" in text
    assert "tests/test_readiness_scopes.py" in text
    assert "tests/test_discover_instance.py" in text
    assert "tests/test_start_operator_fedora_dev.py" in text
    assert "scripts/discover_instance.py --runs-dir runs/ci-linux-discover-instance" in text
    assert "scripts/start_operator_fedora_dev.py" in text
    assert "--print-only" in text



def test_portable_core_linux_workflow_writes_fedora_companion_receipt() -> None:
    text = _workflow_text()

    assert "tests/test_fedora_companion_milestone.py" in text
    assert "scripts/write_fedora_companion_receipt.py" in text
    assert "--allow-missing-atm10-dir" in text
    assert "runs/ci-fedora-companion-receipt" in text



def test_portable_core_linux_workflow_keeps_windows_edge_contract_visible() -> None:
    text = _workflow_text()

    assert "tests/test_windows_product_edge_contract.py" in text
