from __future__ import annotations

import json
from pathlib import Path

import pytest

from atm10_agent.memory import (
    EmbeddedMemoryStore,
    MemoryLifecycle,
    MemoryObject,
    MemoryTrust,
    capture_turn_memory,
)
from atm10_agent.proof import ProvenanceRef


TIMESTAMP = "2026-07-25T13:00:00+00:00"


def _memory(memory_id: str, kind: str) -> MemoryObject:
    return MemoryObject(
        memory_id=memory_id,
        kind=kind,
        title="Test memory",
        summary="One bounded test memory.",
        scope=("project:ATM10-Agent",),
        content={"test": True},
        created_at_utc=TIMESTAMP,
        observed_at_utc=TIMESTAMP,
        provenance=(ProvenanceRef(kind="trace", ref="turn:test"),),
        trust=MemoryTrust(
            confidence=1.0,
            authority_kind="direct_observation",
            authority="test artifact",
            freshness=1.0,
            salience=0.5,
            temperature="hot",
        ),
        lifecycle=MemoryLifecycle(state="captured", current_recall="allowed"),
    )


def test_store_separates_append_only_objects_from_working_context(
    tmp_path: Path,
) -> None:
    store = EmbeddedMemoryStore(tmp_path / "memory")
    durable = _memory("memory:episode:test", "player_episode")
    working = _memory("memory:working_context:current", "working_context")

    assert store.append(durable) == durable.memory_id
    with pytest.raises(ValueError, match="duplicate memory_id"):
        store.append(durable)
    with pytest.raises(ValueError, match="separate mutable"):
        store.append(working)

    context_path = store.write_working_context(working)
    assert store.read_objects() == [durable]
    assert store.read_working_context() == working
    assert store.objects_path.is_file()
    assert context_path.is_file()
    assert store.objects_path != context_path


def test_online_capture_writes_two_durable_objects_and_one_mutable_context(
    tmp_path: Path,
) -> None:
    store = EmbeddedMemoryStore(tmp_path / "memory")
    result = capture_turn_memory(
        store=store,
        turn_id="turn:test",
        timestamp_utc=TIMESTAMP,
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
            "knowledge": {"readiness": {"status": "bounded_ready"}},
        },
        response={"mode": "grounded_file_world"},
        action={
            "intent": "open_quest_book",
            "status": "planned",
            "dry_run": True,
            "executed": False,
        },
    )

    assert result["status"] == "ok"
    assert len(result["durable_object_ids"]) == 2
    assert Path(result["objects_store"]).is_file()
    assert Path(result["working_context"]).is_file()
    assert {item.kind for item in store.read_objects()} == {
        "observed_world_state",
        "player_episode",
    }
    world_memory = next(
        item for item in store.read_objects() if item.kind == "observed_world_state"
    )
    assert [(item.kind, item.owner, item.ref) for item in world_memory.provenance] == [
        ("trace", "ATM10-Agent", "turn:test"),
        (
            "source",
            "atm10_builtin_world",
            "package://atm10_agent/data/default_world.jsonl#quest:steel_tools",
        ),
    ]
    assert store.read_working_context().kind == "working_context"


def test_store_rejects_structurally_invalid_memory_objects(tmp_path: Path) -> None:
    store = EmbeddedMemoryStore(tmp_path / "memory")
    store.root.mkdir(parents=True)
    payload = _memory("memory:episode:invalid", "player_episode").to_dict()
    payload["trust"]["confidence"] = None
    store.objects_path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="trust axes must be numeric"):
        store.read_objects()
