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


def test_gateway_sla_readiness_nightly_contains_progress_wiring() -> None:
    workflow_path = Path(".github/workflows/gateway-sla-readiness-nightly.yml")
    text = workflow_path.read_text(encoding="utf-8")

    assert "check_gateway_sla_fail_nightly_progress.py" in text
    assert "Summary - Gateway SLA fail_nightly progress" in text
    assert "runs/nightly-gateway-sla-progress/progress_summary.json" in text

    restore_cache_block = _extract_step_block(text, "Restore cache - Gateway SLA history")
    save_cache_block = _extract_step_block(text, "Save cache - Gateway SLA history")
    upload_artifact_block = _extract_step_block(text, "Upload artifact - Gateway SLA readiness nightly runs")

    for block in (restore_cache_block, save_cache_block, upload_artifact_block):
        assert "runs/nightly-gateway-sla-governance" in block
        assert "runs/nightly-gateway-sla-progress" in block
