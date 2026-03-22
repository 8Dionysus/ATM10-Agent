from __future__ import annotations

import re
from pathlib import Path


WORKFLOW_PATHS = (
    ".github/workflows/pytest.yml",
    ".github/workflows/combo-a-profile-smoke.yml",
    ".github/workflows/gateway-sla-readiness-nightly.yml",
    ".github/workflows/kag-neo4j-guardrail-nightly.yml",
    ".github/workflows/security-nightly.yml",
)


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _extract_step_block(workflow_text: str, step_name: str) -> str:
    pattern = re.compile(
        rf"- name: {re.escape(step_name)}\n(?P<body>(?:\s{{8,}}.*\n)+)",
        flags=re.MULTILINE,
    )
    match = pattern.search(workflow_text)
    assert match is not None, f"workflow step not found: {step_name}"
    return match.group("body")


def test_tracked_workflows_declare_least_privilege_permissions() -> None:
    for workflow_path in WORKFLOW_PATHS:
        text = _read_text(workflow_path)
        assert re.search(r"^permissions:\n\s+contents:\s+read\s*$", text, flags=re.MULTILINE), workflow_path


def test_pytest_workflow_public_summary_is_sanitized() -> None:
    text = _read_text(".github/workflows/pytest.yml")

    assert "GATEWAY_SLA_TREND_SNAPSHOT_JSON=$($trendSnapshot.FullName)" not in text
    assert "GATEWAY_SLA_TREND_SUMMARY_MD=$($trendSummary.FullName)" not in text

    trend_block = _extract_step_block(text, "Summary - Gateway SLA trend")
    cross_service_block = _extract_step_block(text, "Summary - Cross-service benchmark suite")
    automation_block = _extract_step_block(text, "Summary - Automation smoke contracts")
    smoke_artifact_block = _extract_step_block(text, "Upload artifact - Automation smoke summaries")
    dependency_artifact_block = _extract_step_block(text, "Upload artifact - Dependency audit")

    for token in ("should_fail_nightly", "trend_snapshot_json", "trend_summary_md"):
        assert token not in trend_block
    for token in ("summary_json", "run_dir", "child_runs_root"):
        assert token not in cross_service_block
    for token in ("trace_id", "intent_id"):
        assert token not in automation_block

    assert "gateway_sla_trend_snapshot.json" in smoke_artifact_block
    assert "cross_service_benchmark_suite.json" in smoke_artifact_block
    assert "service_sla_summary.json" in smoke_artifact_block
    assert "runs/ci-smoke-gateway-sla-trend\n" not in smoke_artifact_block
    assert "path: runs/ci-smoke-cross-service-suite" not in smoke_artifact_block
    for token in (
        "run.json",
        "dependency_inventory.json",
        "dependency_findings.json",
        "security_audit.json",
        "summary.md",
    ):
        assert token in dependency_artifact_block
    assert "path: runs/ci-dependency-audit" not in dependency_artifact_block


def test_gateway_nightly_public_summary_is_sanitized() -> None:
    text = _read_text(".github/workflows/gateway-sla-readiness-nightly.yml")

    readiness_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly readiness")
    governance_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly governance")
    progress_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly progress")
    transition_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly transition")
    remediation_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly remediation")
    integrity_block = _extract_step_block(text, "Summary - Gateway SLA fail_nightly integrity")
    upload_artifact_block = _extract_step_block(text, "Upload artifact - Gateway SLA readiness nightly runs")

    for token in ("invalid_or_error_count", "reason_codes", "target_policy"):
        assert token not in readiness_block
    for token in ("invalid_or_mismatched_count", "reason_codes", "target_policy", "switch_surface"):
        assert token not in governance_block
    for token in ("readiness_valid_count", "governance_valid_count", "latest_governance_status", "target_policy", "reason_codes"):
        assert token not in progress_block
    for token in ("allow_switch", "latest_ready_streak", "invalid_or_mismatched_count", "target_policy", "reason_codes"):
        assert token not in transition_block
    for token in ("candidate_item_ids", "reason_codes"):
        assert token not in remediation_block
    for token in ("telemetry_ok", "dual_write_ok", "anti_double_count_ok", "utc_guardrail_status", "reason_codes"):
        assert token not in integrity_block

    assert "gateway_sla_trend_snapshot.json" in upload_artifact_block
    assert "readiness_summary.json" in upload_artifact_block
    assert "governance_summary.json" in upload_artifact_block
    assert "progress_summary.json" in upload_artifact_block
    assert "transition_summary.json" in upload_artifact_block
    assert "remediation_summary.json" in upload_artifact_block
    assert "integrity_summary.json" in upload_artifact_block
    for line in (
        "runs/nightly-gateway-sla-history",
        "runs/nightly-gateway-sla-trend-history",
        "runs/nightly-gateway-sla-readiness",
        "runs/nightly-gateway-sla-governance",
        "runs/nightly-gateway-sla-progress",
        "runs/nightly-gateway-sla-transition",
        "runs/nightly-gateway-sla-remediation",
        "runs/nightly-gateway-sla-integrity",
    ):
        assert f"{line}\n" not in upload_artifact_block


def test_kag_and_security_workflow_public_artifacts_are_allowlisted() -> None:
    kag_text = _read_text(".github/workflows/kag-neo4j-guardrail-nightly.yml")
    kag_summary_block = _extract_step_block(kag_text, "Summary - KAG guardrail trend")
    kag_upload_block = _extract_step_block(kag_text, "Upload artifact - KAG nightly runs")

    for token in (
        "sample_latest_run",
        "hard_latest_run",
        "delta_mrr",
        "delta_latency_p95_ms",
        "sample_mrr_status",
        "hard_mrr_status",
        "should_fail_nightly",
        "trend_summary_md",
        "RUNBOOK M6.8",
    ):
        assert token not in kag_summary_block
    for token in ("eval_results.json", "trend_snapshot.json", "summary.md", "run.json"):
        assert token in kag_upload_block
    for line in ("runs/nightly-kag-build", "runs/nightly-kag-sync", "runs/nightly-kag-eval-sample\n", "runs/nightly-kag-eval-hard\n", "runs/nightly-kag-trend\n"):
        assert line not in kag_upload_block

    security_text = _read_text(".github/workflows/security-nightly.yml")
    security_upload_block = _extract_step_block(security_text, "Upload artifact - Security nightly report")
    for token in (
        "run.json",
        "dependency_inventory.json",
        "dependency_findings.json",
        "security_audit.json",
        "summary.md",
    ):
        assert token in security_upload_block
    assert "path: runs/nightly-security-audit" not in security_upload_block


def test_combo_a_workflow_public_artifacts_are_allowlisted() -> None:
    text = _read_text(".github/workflows/combo-a-profile-smoke.yml")

    gateway_block = _extract_step_block(text, "Summary - Combo A gateway smoke")
    suite_block = _extract_step_block(text, "Summary - Combo A cross-service suite")
    operator_block = _extract_step_block(text, "Summary - Combo A operator probes")
    upload_block = _extract_step_block(text, "Upload artifact - Combo A profile runs")

    for token in ("NEO4J_PASSWORD", "service.log", "collection", "dataset_tag"):
        assert token not in gateway_block
    for token in ("combo_a_seed_run_dir", "child_runs_root", "history_summary_json"):
        assert token not in suite_block
    for token in ("missing_config", "warnings", "password"):
        assert token not in operator_block

    for token in (
        "gateway_smoke_summary.json",
        "gateway_http_smoke_summary.json",
        "cross_service_benchmark_suite.json",
        "service_sla_summary.json",
        "summary.md",
        "operator_snapshot.json",
        "healthz.json",
        "run.json",
    ):
        assert token in upload_block
    for line in (
        "path: runs/ci-smoke-gateway-combo-a",
        "path: runs/ci-smoke-gateway-http-combo-a",
        "path: runs/nightly-combo-a-cross-service-suite",
        "path: runs/nightly-combo-a-operator-probes",
    ):
        assert line not in upload_block
