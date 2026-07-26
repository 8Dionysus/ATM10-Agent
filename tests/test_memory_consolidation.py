from __future__ import annotations

import json
from pathlib import Path

from atm10_agent.memory import EmbeddedMemoryStore, capture_turn_memory, consolidate_memory
from atm10_agent.cli import main


CAPTURED_AT = "2026-07-25T13:00:00+00:00"
CONSOLIDATED_AT = "2026-07-25T14:00:00+00:00"


def _capture(store: EmbeddedMemoryStore) -> None:
    capture_turn_memory(
        store=store,
        turn_id="turn:consolidation",
        timestamp_utc=CAPTURED_AT,
        query="steel tools",
        turn_status="ok",
        world={
            "status": "ok",
            "backend": "file",
            "citations": [
                {
                    "id": "quest:steel_tools",
                    "source": "atm10_builtin_world",
                    "path": "package://atm10_agent/data/default_world.jsonl",
                }
            ],
        },
        response={"mode": "grounded_file_world"},
        action={
            "intent": "open_quest_book",
            "status": "planned",
            "dry_run": True,
            "executed": False,
        },
    )


def test_offline_consolidation_creates_only_proposed_candidates(
    tmp_path: Path,
) -> None:
    store = EmbeddedMemoryStore(tmp_path / "memory")
    _capture(store)

    report = consolidate_memory(store=store, observed_at_utc=CONSOLIDATED_AT)
    candidates = [
        item
        for item in store.read_objects()
        if item.kind in {"semantic_game_knowledge", "procedural_gameplay"}
    ]

    assert report["status"] == "ok"
    assert len(report["created_candidate_ids"]) == 2
    assert report["automatic_confirmation"] is False
    assert report["automatic_freeze"] is False
    assert {item.kind for item in candidates} == {
        "semantic_game_knowledge",
        "procedural_gameplay",
    }
    assert {item.lifecycle.state for item in candidates} == {"proposed"}
    assert {item.trust.authority_kind for item in candidates} == {"agent_derived"}
    semantic = next(
        item for item in candidates if item.kind == "semantic_game_knowledge"
    )
    assert [(item.kind, item.owner, item.ref) for item in semantic.provenance] == [
        ("artifact", "ATM10-Agent", "memory:observed_world_state:fcee66f74e584831afa0"),
        (
            "source",
            "atm10_builtin_world",
            "package://atm10_agent/data/default_world.jsonl#quest:steel_tools",
        ),
    ]
    procedural = next(item for item in candidates if item.kind == "procedural_gameplay")
    assert "effectiveness was not observed" in procedural.summary


def test_consolidation_is_idempotent_by_candidate_identity(tmp_path: Path) -> None:
    store = EmbeddedMemoryStore(tmp_path / "memory")
    _capture(store)
    first = consolidate_memory(store=store, observed_at_utc=CONSOLIDATED_AT)
    second = consolidate_memory(store=store, observed_at_utc=CONSOLIDATED_AT)

    assert len(first["created_candidate_ids"]) == 2
    assert second["created_candidate_ids"] == []
    assert set(second["skipped_existing_ids"]) == set(first["created_candidate_ids"])
    assert len(store.read_objects()) == 4


def test_cli_consolidation_exposes_only_proposed_candidates(
    tmp_path: Path,
    capsys: object,
) -> None:
    store = EmbeddedMemoryStore(tmp_path / "memory")
    _capture(store)

    assert (
        main(
            [
                "consolidate-memory",
                "--memory-dir",
                str(store.root),
                "--now",
                CONSOLIDATED_AT,
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["candidate_lifecycle"] == "proposed"
    assert report["automatic_confirmation"] is False
    assert report["automatic_freeze"] is False
