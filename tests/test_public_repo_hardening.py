from __future__ import annotations

import re
from pathlib import Path


PUBLIC_DOCS_WITH_EXAMPLES = [
    Path("AGENTS.md"),
    Path("README.md"),
    Path("docs/RUNBOOK.md"),
    Path("docs/DECISIONS.md"),
]

PUBLIC_ENTRY_AND_REFERENCE_DOCS = [
    Path("README.md"),
    Path("MANIFEST.md"),
    Path("docs/RELEASE_WAVE6.md"),
]

PUBLIC_WORKFLOW_SURFACE = [
    Path(".github/workflows/kag-neo4j-guardrail-nightly.yml"),
]


def test_public_docs_and_workflows_avoid_workstation_paths_and_literal_demo_tokens() -> None:
    files = PUBLIC_DOCS_WITH_EXAMPLES + PUBLIC_WORKFLOW_SURFACE
    disallowed_literals = [
        "neo4jpass",
        r"D:\atm10-agent",
        r"C:\Users\Admin",
        r"C:\path\to",
        '--service-token "change-me"',
    ]

    for path in files:
        text = path.read_text(encoding="utf-8")
        for literal in disallowed_literals:
            assert literal not in text, f"disallowed public literal {literal!r} found in {path}"


def test_public_kag_examples_keep_local_only_placeholder_pattern() -> None:
    workflow_text = Path(".github/workflows/kag-neo4j-guardrail-nightly.yml").read_text(encoding="utf-8")
    runbook_text = Path("docs/RUNBOOK.md").read_text(encoding="utf-8")

    assert "NEO4J_PASSWORD: local-ci-only-not-secret" in workflow_text
    assert "NEO4J_AUTH: neo4j/${{ env.NEO4J_PASSWORD }}" in workflow_text
    assert '"neo4j:${NEO4J_PASSWORD}"' in workflow_text
    assert "<set-local-neo4j-password>" in runbook_text


def test_public_docs_use_generic_repo_and_local_path_placeholders() -> None:
    docs_text = "\n".join(path.read_text(encoding="utf-8") for path in PUBLIC_DOCS_WITH_EXAMPLES)

    assert "<repo-root>" in docs_text
    assert "<path-to-" in docs_text
    assert "ATM10_SERVICE_TOKEN" in docs_text


def test_public_entry_and_release_docs_avoid_concrete_local_runs_evidence() -> None:
    disallowed_runs_patterns = [
        re.compile(r"runs/ci-"),
        re.compile(r"runs/nightly-"),
        re.compile(r"runs/\d{8}_"),
    ]

    for path in PUBLIC_ENTRY_AND_REFERENCE_DOCS:
        text = path.read_text(encoding="utf-8")
        for pattern in disallowed_runs_patterns:
            assert pattern.search(text) is None, (
                f"concrete local runs evidence leaked into public entry/reference doc {path}: "
                f"{pattern.pattern}"
            )
