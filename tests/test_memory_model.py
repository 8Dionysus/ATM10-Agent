from __future__ import annotations

import pytest

from atm10_agent.memory import MemoryLifecycle, MemoryObject, MemoryTrust
from atm10_agent.proof import ProvenanceRef


TIMESTAMP = "2026-07-25T13:00:00+00:00"
MEMORY_KINDS = (
    "observed_world_state",
    "player_episode",
    "semantic_game_knowledge",
    "procedural_gameplay",
    "working_context",
)


def _memory(kind: str) -> MemoryObject:
    return MemoryObject(
        memory_id=f"memory:{kind}:test",
        kind=kind,
        title=f"{kind} title",
        summary=f"{kind} summary",
        scope=("project:ATM10-Agent",),
        content={"kind": kind},
        created_at_utc=TIMESTAMP,
        observed_at_utc=TIMESTAMP,
        provenance=(ProvenanceRef(kind="trace", ref="turn:test"),),
        trust=MemoryTrust(
            confidence=0.8,
            authority_kind="direct_observation",
            authority="one deterministic test observation",
            freshness=0.9,
            salience=0.6,
            temperature="warm",
        ),
        lifecycle=MemoryLifecycle(state="captured", current_recall="allowed"),
    )


@pytest.mark.parametrize("kind", MEMORY_KINDS)
def test_memory_object_canon_preserves_separate_trust_axes(kind: str) -> None:
    payload = _memory(kind).to_dict()

    assert payload["kind"] == kind
    assert payload["trust"] == {
        "confidence": 0.8,
        "authority_kind": "direct_observation",
        "authority": "one deterministic test observation",
        "freshness": 0.9,
        "salience": 0.6,
        "temperature": "warm",
    }
    assert payload["authority_ceiling"] == "memory_not_proof_or_world_authority"
    assert MemoryObject.from_dict(payload) == _memory(kind)


def test_memory_trust_rejects_collapsed_or_invalid_posture() -> None:
    with pytest.raises(ValueError, match="confidence"):
        MemoryTrust(
            confidence=1.1,
            authority_kind="direct_observation",
            authority="test",
            freshness=0.5,
            salience=0.5,
            temperature="warm",
        )
    with pytest.raises(ValueError, match="authority_kind"):
        MemoryTrust(
            confidence=0.5,
            authority_kind="proof",
            authority="test",
            freshness=0.5,
            salience=0.5,
            temperature="warm",
        )


def test_memory_lifecycle_requires_visible_freeze_and_retraction_posture() -> None:
    with pytest.raises(ValueError, match="freeze_basis"):
        MemoryLifecycle(state="frozen", current_recall="preferred")
    frozen = MemoryLifecycle(
        state="frozen",
        current_recall="preferred",
        freeze_basis="operator_review",
    )
    assert frozen.freeze_basis == "operator_review"

    with pytest.raises(ValueError, match="withdrawn"):
        MemoryLifecycle(state="retracted", current_recall="allowed")
    retracted = MemoryLifecycle(state="retracted", current_recall="withdrawn")
    assert retracted.current_recall == "withdrawn"
