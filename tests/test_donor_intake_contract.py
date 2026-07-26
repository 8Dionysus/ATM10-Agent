from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "docs" / "intake" / "donor-ledger.json"
SCHEMA_PATH = REPO_ROOT / "schemas" / "donor_intake_ledger_v1.json"
EXPECTED_DONORS = {
    "donor.aoa-evals",
    "donor.aoa-kag",
    "donor.aoa-stats",
    "donor.aoa-memo",
    "donor.aoa-routing",
    "donor.abyss-stack",
}


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_donor_ledger_validates_and_has_unique_pinned_entries() -> None:
    schema = _load(SCHEMA_PATH)
    ledger = _load(LEDGER_PATH)
    Draft202012Validator(schema).validate(ledger)

    entries = ledger["entries"]
    assert isinstance(entries, list)
    assert {entry["id"] for entry in entries} == EXPECTED_DONORS
    assert len({entry["owner_repo"] for entry in entries}) == len(entries)
    statuses = {entry["id"]: entry["status"] for entry in entries}
    assert {
        entry_id for entry_id, status in statuses.items() if status == "adapted"
    } == {
        "donor.aoa-evals",
        "donor.aoa-kag",
        "donor.aoa-stats",
        "donor.aoa-memo",
        "donor.aoa-routing",
        "donor.abyss-stack",
    }

    for entry in entries:
        assert re.fullmatch(r"[0-9a-f]{40}", entry["revision"])
        assert entry["license"] == {
            "spdx": "Apache-2.0",
            "source_path": "LICENSE",
            "reviewed": True,
        }
        assert entry["status"] in {"admitted_for_implementation", "adapted"}
        assert entry["runtime_dependency"] is False
        assert entry["auto_sync"] is False
        assert entry["selected_paths"]
        assert entry["target_surfaces"]
        assert entry["required_local_tests"]
        assert entry["rejected_surfaces"]


def test_selected_sources_are_authored_relative_paths() -> None:
    ledger = _load(LEDGER_PATH)
    forbidden_fragments = (
        "generated/",
        "kag/indexes/",
        "/runtime/",
        "/logs/",
        ".aoa/",
    )

    for entry in ledger["entries"]:
        for selection in entry["selected_paths"]:
            source_path = selection["path"]
            assert not source_path.startswith(("/", "~"))
            assert "\\" not in source_path
            assert ".." not in Path(source_path).parts
            assert not any(fragment in source_path.lower() for fragment in forbidden_fragments)


def test_linux_gate_admits_intake_without_claiming_windows() -> None:
    ledger = _load(LEDGER_PATH)

    assert ledger["standalone_gate"]["platform"] == "linux"
    assert ledger["standalone_gate"]["status"] == "passed"
    assert ledger["windows_lane"]["required_for_intake"] is False
    assert ledger["windows_lane"]["status"] == "deferred_to_separate_session"
    assert "unfinished" in ledger["windows_lane"]["claim_limit"]

    autonomy = (REPO_ROOT / "docs" / "autonomy" / "README.md").read_text(
        encoding="utf-8"
    )
    manifest = (REPO_ROOT / "MANIFEST.md").read_text(encoding="utf-8")
    roadmap = (REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    for text in (autonomy, manifest, roadmap):
        assert "docs/intake/donor-ledger.json" in text
    assert "required_for_intake" not in roadmap


def test_core_metadata_has_no_donor_runtime_dependency() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for donor in (
        "aoa-evals",
        "aoa-kag",
        "aoa-stats",
        "aoa-memo",
        "aoa-routing",
        "abyss-stack",
    ):
        assert donor not in pyproject
