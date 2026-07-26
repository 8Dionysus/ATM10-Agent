from __future__ import annotations

import re
from pathlib import Path


WORKFLOW_ROOT = Path(".github/workflows")


def _read_text(name: str) -> str:
    return (WORKFLOW_ROOT / name).read_text(encoding="utf-8")


def test_all_workflows_declare_least_privilege_permissions() -> None:
    workflows = sorted(WORKFLOW_ROOT.glob("*.yml"))
    assert workflows
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        assert re.search(
            r"^permissions:\n\s+contents:\s+read\s*$",
            text,
            flags=re.MULTILINE,
        ), path


def test_active_workflows_do_not_restore_the_retired_control_plane() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in WORKFLOW_ROOT.glob("*.yml"))
    for retired_term in (
        "gateway_sla",
        "gateway_v1",
        "cross_service_benchmark",
        "streamlit_operator",
        "start_operator_product",
        "pilot_runtime",
        "combo_a",
    ):
        assert retired_term not in combined.lower()


def test_windows_workflow_proves_package_tests_and_installed_smoke() -> None:
    text = _read_text("pytest.yml")
    assert "runs-on: windows-latest" in text
    assert 'python -m pip install -e \".[dev]\"' in text
    assert "python -m pip install . --no-deps" in text
    assert "python -m pytest" in text
    assert "atm10 doctor" in text
    assert "atm10 run" in text
    assert "atm10 replay" in text
    assert "atm10 eval" in text


def test_kag_and_security_artifacts_remain_path_allowlisted() -> None:
    kag_text = _read_text("kag-neo4j-guardrail-nightly.yml")
    security_text = _read_text("security-nightly.yml")
    assert "eval_results.json" in kag_text
    assert "trend_snapshot.json" in kag_text
    assert "path: runs/nightly-kag-build" not in kag_text
    assert "dependency_inventory.json" in security_text
    assert "security_audit.json" in security_text
    assert "path: runs/nightly-security-audit" not in security_text
