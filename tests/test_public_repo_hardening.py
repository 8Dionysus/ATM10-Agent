from __future__ import annotations

from pathlib import Path


def test_public_repo_docs_and_workflows_avoid_literal_default_passwords_and_personal_paths() -> None:
    files = [
        Path(".github/workflows/kag-neo4j-guardrail-nightly.yml"),
        Path("docs/RUNBOOK.md"),
        Path("docs/DECISIONS.md"),
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "neo4jpass" not in text, f"literal default password leaked in {path}"
        assert r"C:\Users\Admin" not in text, f"personal local path leaked in {path}"


def test_public_kag_examples_use_local_only_placeholder_pattern() -> None:
    workflow_text = Path(".github/workflows/kag-neo4j-guardrail-nightly.yml").read_text(encoding="utf-8")
    runbook_text = Path("docs/RUNBOOK.md").read_text(encoding="utf-8")

    assert "NEO4J_PASSWORD: local-ci-only-not-secret" in workflow_text
    assert "NEO4J_AUTH: neo4j/${{ env.NEO4J_PASSWORD }}" in workflow_text
    assert '"neo4j:${NEO4J_PASSWORD}"' in workflow_text
    assert "<set-local-neo4j-password>" in runbook_text
