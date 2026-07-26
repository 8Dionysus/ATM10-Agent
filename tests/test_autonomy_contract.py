from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_local_evals import validate_local_evals


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTONOMY_ROOT = REPO_ROOT / "docs" / "autonomy"
ALLOWED_DISPOSITIONS = {"keep", "rewrite", "optionalize", "cut", "import_once"}


def _load_json(name: str) -> dict[str, object]:
    return json.loads((AUTONOMY_ROOT / name).read_text(encoding="utf-8"))


def test_dependency_ledger_is_complete_and_has_no_required_external_owner() -> None:
    payload = _load_json("dependency-ledger.json")
    entries = payload["entries"]

    assert payload["schema_version"] == "atm10_dependency_ledger_v1"
    assert set(payload["allowed_dispositions"]) == ALLOWED_DISPOSITIONS
    assert isinstance(entries, list)
    assert len(entries) >= 15

    ids: set[str] = set()
    for raw_entry in entries:
        assert isinstance(raw_entry, dict)
        entry = raw_entry
        entry_id = str(entry["id"])
        assert entry_id not in ids
        ids.add(entry_id)
        assert entry["disposition"] in ALLOWED_DISPOSITIONS
        assert isinstance(entry["required_for_core"], bool)
        assert str(entry["surface"]).strip()
        assert str(entry["current_owner"]).strip()
        assert str(entry["target_owner"]).strip()
        assert str(entry["reason"]).strip()

        if entry_id.startswith(("federation.", "donor.")):
            assert entry["required_for_core"] is False

    assert "core.companion-loop" in ids
    assert "federation.repo-self-kag" in ids
    assert "federation.stats-validator" in ids
    assert "federation.eval-port" in ids


def test_protected_behavior_has_unique_ids_and_live_evidence_anchors() -> None:
    payload = _load_json("protected-behavior.json")
    behaviors = payload["behaviors"]

    assert payload["schema_version"] == "atm10_protected_behavior_v1"
    assert isinstance(behaviors, list)
    assert len(behaviors) >= 10

    ids: set[str] = set()
    names: set[str] = set()
    for raw_behavior in behaviors:
        assert isinstance(raw_behavior, dict)
        behavior = raw_behavior
        behavior_id = str(behavior["id"])
        name = str(behavior["name"])
        assert behavior_id not in ids
        assert name not in names
        ids.add(behavior_id)
        names.add(name)
        assert str(behavior["contract"]).strip()

        evidence = behavior["evidence"]
        assert isinstance(evidence, list)
        assert evidence
        for raw_path in evidence:
            path = REPO_ROOT / str(raw_path)
            assert path.exists(), f"missing protected-behavior evidence anchor: {raw_path}"


def test_canonical_docs_route_to_autonomy_contract() -> None:
    required_docs = (
        REPO_ROOT / "README.md",
        REPO_ROOT / "MANIFEST.md",
        REPO_ROOT / "ROADMAP.md",
        REPO_ROOT / "docs" / "SOURCE_OF_TRUTH.md",
    )
    for path in required_docs:
        text = path.read_text(encoding="utf-8")
        assert "docs/autonomy/README.md" in text, path


def test_eval_contract_is_source_owned_and_valid() -> None:
    assert validate_local_evals() == []
    assert not any(path.is_file() for path in (REPO_ROOT / "stats").rglob("*"))
    assert not (REPO_ROOT / "scripts" / "validate_local_stats_port.py").exists()


def test_repo_validation_has_no_sibling_checkout_or_owner_action() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "repo-validation.yml").read_text(
        encoding="utf-8"
    )

    assert "8Dionysus/" not in workflow
    assert "repository:" not in workflow
    assert "AOA_" not in workflow
    assert "scripts.validate_local_evals" in workflow
    assert "scripts.validate_local_stats_port" not in workflow
    assert "Smoke - Autonomous companion package" in workflow
    assert "atm10 doctor" in workflow
    assert "atm10 run" in workflow
    assert "atm10 replay" in workflow
    assert "atm10 eval" in workflow


def test_retired_control_plane_is_absent() -> None:
    retired_paths = (
        ".github/workflows/gateway-sla-readiness-nightly.yml",
        ".github/workflows/combo-a-profile-smoke.yml",
        "scripts/gateway_v1_local.py",
        "scripts/pilot_runtime_loop.py",
        "scripts/start_operator_product.py",
        "scripts/streamlit_operator_panel.py",
        "scripts/voice_runtime_service.py",
        "scripts/tts_runtime_service.py",
    )
    for relative_path in retired_paths:
        assert not (REPO_ROOT / relative_path).exists(), relative_path


def test_repo_self_kag_is_removed_but_product_kag_remains() -> None:
    assert not (REPO_ROOT / "kag").exists()
    product_kag = REPO_ROOT / "src" / "atm10_agent" / "kag"
    assert (product_kag / "baseline.py").is_file()
    assert (product_kag / "neo4j_backend.py").is_file()
