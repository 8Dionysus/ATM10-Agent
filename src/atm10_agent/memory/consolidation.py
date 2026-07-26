"""Explicit offline derivation of proposed semantic and procedural memory."""

from __future__ import annotations

import hashlib
from typing import Any

from atm10_agent.memory.model import (
    MEMORY_AUTHORITY_CEILING,
    MemoryLifecycle,
    MemoryObject,
    MemoryTrust,
)
from atm10_agent.memory.store import EmbeddedMemoryStore
from atm10_agent.proof import ProvenanceRef


MEMORY_CONSOLIDATION_SCHEMA_VERSION = "atm10_memory_consolidation_v1"


def _candidate_id(kind: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{kind}:{source_id}".encode("utf-8")).hexdigest()[:20]
    return f"memory:{kind}:{digest}"


def _semantic_candidate(
    source: MemoryObject,
    observed_at_utc: str,
) -> MemoryObject | None:
    citations = source.content.get("citations")
    if not isinstance(citations, list) or not citations:
        return None
    return MemoryObject(
        memory_id=_candidate_id("semantic_game_knowledge", source.memory_id),
        kind="semantic_game_knowledge",
        title="Cited game-knowledge candidate",
        summary="A prior turn recalled cited ATM10 world sources for this query.",
        scope=("project:ATM10-Agent",),
        content={
            "query": source.content.get("query"),
            "citation_handles": citations,
            "source_memory_ids": [source.memory_id],
        },
        created_at_utc=observed_at_utc,
        observed_at_utc=source.observed_at_utc,
        provenance=(
            ProvenanceRef(kind="artifact", ref=source.memory_id, role="primary"),
            *tuple(item for item in source.provenance if item.kind == "source"),
        ),
        trust=MemoryTrust(
            confidence=min(source.trust.confidence, 0.7),
            authority_kind="agent_derived",
            authority="derived from one cited world observation",
            freshness=source.trust.freshness,
            salience=source.trust.salience,
            temperature="warm",
        ),
        lifecycle=MemoryLifecycle(state="proposed", current_recall="allowed"),
    )


def _procedural_candidate(
    source: MemoryObject,
    observed_at_utc: str,
) -> MemoryObject | None:
    intent = str(source.content.get("action_intent") or "").strip()
    if not intent or source.content.get("dry_run") is not True:
        return None
    return MemoryObject(
        memory_id=_candidate_id("procedural_gameplay", source.memory_id),
        kind="procedural_gameplay",
        title=f"Dry-run procedure candidate for {intent}",
        summary=(
            f"ATM10 generated a dry-run plan for {intent}; execution effectiveness "
            "was not observed."
        ),
        scope=("project:ATM10-Agent",),
        content={
            "intent": intent,
            "action_status": source.content.get("action_status"),
            "dry_run": True,
            "executed": source.content.get("executed"),
            "source_memory_ids": [source.memory_id],
        },
        created_at_utc=observed_at_utc,
        observed_at_utc=source.observed_at_utc,
        provenance=(
            ProvenanceRef(kind="artifact", ref=source.memory_id, role="primary"),
        ),
        trust=MemoryTrust(
            confidence=0.6,
            authority_kind="agent_derived",
            authority="derived from one dry-run companion episode",
            freshness=source.trust.freshness,
            salience=source.trust.salience,
            temperature="warm",
        ),
        lifecycle=MemoryLifecycle(state="proposed", current_recall="allowed"),
    )


def consolidate_memory(
    *,
    store: EmbeddedMemoryStore,
    observed_at_utc: str,
) -> dict[str, Any]:
    """Create reviewable candidates without confirming or freezing them."""

    candidates: list[MemoryObject] = []
    for source in store.read_objects():
        candidate = (
            _semantic_candidate(source, observed_at_utc)
            if source.kind == "observed_world_state"
            else _procedural_candidate(source, observed_at_utc)
            if source.kind == "player_episode"
            else None
        )
        if candidate is not None:
            candidates.append(candidate)

    created: list[str] = []
    skipped_existing: list[str] = []
    for candidate in candidates:
        if store.has_object(candidate.memory_id):
            skipped_existing.append(candidate.memory_id)
            continue
        created.append(store.append(candidate))

    return {
        "schema_version": MEMORY_CONSOLIDATION_SCHEMA_VERSION,
        "status": "ok",
        "created_candidate_ids": created,
        "skipped_existing_ids": skipped_existing,
        "candidate_lifecycle": "proposed",
        "automatic_confirmation": False,
        "automatic_freeze": False,
        "authority_ceiling": MEMORY_AUTHORITY_CEILING,
        "claim_limit": (
            "Consolidation creates recall candidates from captured memory; it "
            "does not confirm truth, prove gameplay effectiveness, or replace "
            "authored world knowledge."
        ),
    }
