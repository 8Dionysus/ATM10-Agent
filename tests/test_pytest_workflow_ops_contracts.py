from __future__ import annotations

import re
from pathlib import Path


def _extract_step_block(workflow_text: str, step_name: str) -> str:
    pattern = re.compile(
        rf"- name: {re.escape(step_name)}\n(?P<body>(?:\s{{8,}}.*\n)+)",
        flags=re.MULTILINE,
    )
    match = pattern.search(workflow_text)
    assert match is not None, f"workflow step not found: {step_name}"
    return match.group("body")


def test_pytest_workflow_contains_ops_validation_and_index_wiring() -> None:
    workflow_path = Path(".github/workflows/pytest.yml")
    text = workflow_path.read_text(encoding="utf-8")

    assert "validate_ops_contracts.py --profile ci_smoke" in text
    assert "build_ops_contract_index.py --profile ci_smoke" in text
    assert "Summary - Ops contract validation/index" in text
    assert "runs/ci-ops/validation_summary.json" in text
    assert "runs/ci-ops/ops_contract_index.json" in text

    upload_block = _extract_step_block(text, "Upload artifact - Automation smoke summaries")
    assert "runs/ci-ops" in upload_block
