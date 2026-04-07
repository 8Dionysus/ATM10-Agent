from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_json(relative_path: str) -> dict[str, object]:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def test_antifragility_examples_validate_against_schemas() -> None:
    pairs = [
        (
            "schemas/stressor_receipt_v1.json",
            "examples/stressor_receipt.retrieval_only_fallback.example.json",
        ),
        (
            "schemas/adaptation_delta_v1.json",
            "examples/adaptation_delta.retrieval_only_fallback.example.json",
        ),
    ]

    for schema_path, example_path in pairs:
        schema = _load_json(schema_path)
        example = _load_json(example_path)
        Draft202012Validator(schema).validate(example)


def test_antifragility_docs_are_linked_from_public_surfaces() -> None:
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    manifest_text = (REPO_ROOT / "MANIFEST.md").read_text(encoding="utf-8")
    runbook_text = (REPO_ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    source_of_truth_text = (REPO_ROOT / "docs" / "SOURCE_OF_TRUTH.md").read_text(encoding="utf-8")
    antifragility_text = (REPO_ROOT / "docs" / "ANTIFRAGILITY_FIRST_WAVE.md").read_text(encoding="utf-8")

    assert "docs/ANTIFRAGILITY_FIRST_WAVE.md" in readme_text
    assert "docs/ANTIFRAGILITY_FIRST_WAVE.md" in manifest_text
    assert "stressor_receipt.json" in runbook_text
    assert "docs/ANTIFRAGILITY_FIRST_WAVE.md" in source_of_truth_text
    assert "run_hybrid_query" in antifragility_text
    assert "pilot_runtime_loop" in antifragility_text
