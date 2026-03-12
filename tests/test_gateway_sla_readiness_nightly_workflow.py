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


def test_gateway_sla_readiness_nightly_contains_transition_wiring() -> None:
    workflow_path = Path(".github/workflows/gateway-sla-readiness-nightly.yml")
    text = workflow_path.read_text(encoding="utf-8")

    assert "check_gateway_sla_fail_nightly_progress.py" in text
    assert "check_gateway_sla_fail_nightly_transition.py" in text
    assert "check_gateway_sla_fail_nightly_remediation.py" in text
    assert "check_gateway_sla_fail_nightly_integrity.py" in text
    assert "Summary - Gateway SLA fail_nightly progress" in text
    assert "Summary - Gateway SLA fail_nightly transition" in text
    assert "Summary - Gateway SLA fail_nightly remediation" in text
    assert "Summary - Gateway SLA fail_nightly integrity" in text
    assert "runs/nightly-gateway-sla-progress/progress_summary.json" in text
    assert "runs/nightly-gateway-sla-transition/transition_summary.json" in text
    assert "runs/nightly-gateway-sla-remediation/remediation_summary.json" in text
    assert "runs/nightly-gateway-sla-integrity/integrity_summary.json" in text
    assert "--critical-policy fail_nightly" in text
    assert "Resolve - Gateway SLA transition gate" not in text

    remediation_block = _extract_step_block(
        text,
        "Remediation - Gateway SLA fail_nightly snapshot (report_only)",
    )
    integrity_block = _extract_step_block(
        text,
        "Integrity - Gateway SLA fail_nightly invariants (report_only)",
    )
    strict_gate_block = _extract_step_block(
        text,
        "Smoke - Gateway SLA trend snapshot (fail_nightly strict gate)",
    )
    readiness_summary_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly readiness")
    governance_summary_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly governance")
    progress_summary_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly progress")
    transition_summary_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly transition")
    remediation_summary_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly remediation")
    integrity_summary_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly integrity")

    assert "if: always()" in remediation_block
    assert "--policy report_only" in remediation_block
    assert "if: always()" in integrity_block
    assert "--policy report_only" in integrity_block
    assert "if:" not in strict_gate_block
    for block in (
        readiness_summary_block,
        governance_summary_block,
        progress_summary_block,
        transition_summary_block,
        remediation_summary_block,
        integrity_summary_block,
    ):
        assert "if: always()" in block

    restore_cache_block = _extract_step_block(text, "Restore cache - Gateway SLA history")
    save_cache_block = _extract_step_block(text, "Save cache - Gateway SLA history")
    upload_artifact_block = _extract_step_block(text, "Upload artifact - Gateway SLA readiness nightly runs")

    for block in (restore_cache_block, save_cache_block, upload_artifact_block):
        assert "runs/nightly-gateway-sla-governance" in block
        assert "runs/nightly-gateway-sla-progress" in block
        assert "runs/nightly-gateway-sla-transition" in block
        assert "runs/nightly-gateway-sla-remediation" in block
        assert "runs/nightly-gateway-sla-integrity" in block
