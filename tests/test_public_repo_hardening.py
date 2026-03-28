from __future__ import annotations

import re
from pathlib import Path


PUBLIC_DOCS_WITH_EXAMPLES = [
    Path("AGENTS.md"),
    Path("README.md"),
    Path("docs/RUNBOOK.md"),
]

PUBLIC_ENTRY_AND_REFERENCE_DOCS = [
    Path("README.md"),
    Path("MANIFEST.md"),
    Path("docs/ARCHIVED_TRACKS.md"),
    Path("docs/QWEN3_MODEL_STACK.md"),
    Path("docs/RELEASE_WAVE6.md"),
]

PUBLIC_WORKFLOW_SURFACE = [
    Path(".github/workflows/kag-neo4j-guardrail-nightly.yml"),
]


def test_public_docs_and_workflows_avoid_workstation_paths_and_literal_demo_tokens() -> None:
    files = PUBLIC_DOCS_WITH_EXAMPLES + PUBLIC_WORKFLOW_SURFACE
    disallowed_literals = [
        "".join(["neo4j", "pass"]),
        f"D:{chr(92)}atm10-agent",
        f"C:{chr(92)}Users{chr(92)}Admin",
        f"C:{chr(92)}path{chr(92)}to",
        '--service-token "' + "change" + '-me"',
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


def test_public_automation_rollout_records_are_documented() -> None:
    readme_text = Path("README.md").read_text(encoding="utf-8")
    roadmap_text = Path("ROADMAP.md").read_text(encoding="utf-8")
    manifest_text = Path("MANIFEST.md").read_text(encoding="utf-8")
    runbook_text = Path("docs/RUNBOOK.md").read_text(encoding="utf-8")

    for text in (readme_text, roadmap_text, manifest_text, runbook_text):
        assert "M6.19" in text
        assert "open_quest_book" in text
        assert "check_inventory_tool" in text
        assert "open_world_map" in text

    assert "## M6.19 rollout records" in runbook_text
    assert "public intent -> plan -> dry-run chain" in runbook_text


def test_public_surface_cleanup_boundaries_are_enforced() -> None:
    readme_text = Path("README.md").read_text(encoding="utf-8")
    runbook_text = Path("docs/RUNBOOK.md").read_text(encoding="utf-8")
    archived_text = Path("docs/ARCHIVED_TRACKS.md").read_text(encoding="utf-8")
    source_of_truth_text = Path("docs/SOURCE_OF_TRUTH.md").read_text(encoding="utf-8")
    gitignore_text = Path(".gitignore").read_text(encoding="utf-8")

    assert not Path("docs/reviews/2026-03-21-publication-surface").exists()
    assert ".codex/config.toml" in gitignore_text

    for heading in (
        "## Quickstart",
        "## Common launch paths",
        "## Dependency profiles",
        "## Repo map",
    ):
        assert heading not in readme_text

    for removed_section in (
        "### Qwen3-ASR self-conversion (archived reference, keep for future restore)",
        "### Voice support probe + matrix",
        "### ASR demo (archived qwen3-asr path)",
        "### Optional rollback: archived qwen_asr service profile",
        "### Voice latency benchmark (historical)",
    ):
        assert removed_section not in runbook_text

    assert "archived, recoverable, and historical command references" in archived_text
    assert "python scripts/export_qwen3_openvino.py --preset qwen3-asr-0.6b" in archived_text
    assert "python scripts/asr_demo.py --allow-archived-qwen-asr --audio-in" in archived_text
    assert "python scripts/probe_qwen3_voice_support.py" in archived_text
    assert "runs/*qwen3-tts*" in archived_text

    assert "Link-first and non-operational." in source_of_truth_text
    assert "Active runnable commands and operational paths only." in source_of_truth_text
    assert "review snapshots, and proposed-doc drafts" in source_of_truth_text
