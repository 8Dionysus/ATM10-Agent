"""Embedded append-only durable memory and separate mutable working context."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from atm10_agent.memory.model import (
    MEMORY_AUTHORITY_CEILING,
    MemoryLifecycle,
    MemoryObject,
    MemoryTrust,
)
from atm10_agent.proof import ProvenanceRef


MEMORY_CAPTURE_SCHEMA_VERSION = "atm10_memory_capture_v1"


class EmbeddedMemoryStore:
    """Single-process file store for the local modular monolith."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.objects_path = root / "objects.jsonl"
        self.working_context_path = root / "working-context.json"

    def read_objects(self, *, kind: str | None = None) -> list[MemoryObject]:
        if not self.objects_path.is_file():
            return []
        objects: list[MemoryObject] = []
        for line_no, raw_line in enumerate(
            self.objects_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid memory JSON at {self.objects_path}:{line_no}"
                ) from exc
            if not isinstance(payload, Mapping):
                raise ValueError(
                    f"memory line must be an object at {self.objects_path}:{line_no}"
                )
            memory = MemoryObject.from_dict(payload)
            if kind is None or memory.kind == kind:
                objects.append(memory)
        return objects

    def has_object(self, memory_id: str) -> bool:
        return any(item.memory_id == memory_id for item in self.read_objects())

    def append(self, memory: MemoryObject) -> str:
        if memory.kind == "working_context":
            raise ValueError("working_context must use the separate mutable surface")
        if self.has_object(memory.memory_id):
            raise ValueError(f"duplicate memory_id: {memory.memory_id}")
        self.root.mkdir(parents=True, exist_ok=True)
        with self.objects_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(memory.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
            )
        return memory.memory_id

    def write_working_context(self, memory: MemoryObject) -> Path:
        if memory.kind != "working_context":
            raise ValueError("mutable context surface accepts only working_context")
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.working_context_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(memory.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.working_context_path)
        return self.working_context_path

    def read_working_context(self) -> MemoryObject | None:
        if not self.working_context_path.is_file():
            return None
        payload = json.loads(self.working_context_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("working context must contain a JSON object")
        return MemoryObject.from_dict(payload)


def _memory_id(turn_id: str, kind: str) -> str:
    digest = hashlib.sha256(f"{turn_id}:{kind}".encode("utf-8")).hexdigest()[:20]
    return f"memory:{kind}:{digest}"


def _citation_provenance(
    citations: list[dict[str, Any]],
) -> tuple[ProvenanceRef, ...]:
    refs: list[ProvenanceRef] = []
    for citation in citations:
        document_id = str(citation.get("id", "")).strip()
        locator = str(citation.get("path", "")).strip()
        if not document_id and not locator:
            continue
        refs.append(
            ProvenanceRef(
                kind="source",
                ref=(
                    f"{locator}#{document_id}"
                    if locator and document_id
                    else locator or f"document:{document_id}"
                ),
                role="supporting",
                owner=str(citation.get("source", "")).strip() or "ATM10-Agent",
            )
        )
    return tuple(refs)


def capture_turn_memory(
    *,
    store: EmbeddedMemoryStore,
    turn_id: str,
    timestamp_utc: str,
    query: str,
    turn_status: str,
    world: Mapping[str, Any],
    response: Mapping[str, Any],
    action: Mapping[str, Any],
) -> dict[str, Any]:
    """Fast online capture of observations and an episode; no consolidation."""

    trace_ref = ProvenanceRef(kind="trace", ref=turn_id, role="primary")
    citations = [
        dict(item)
        for item in world.get("citations", [])
        if isinstance(item, Mapping)
    ]
    source_refs = _citation_provenance(citations)
    world_memory = MemoryObject(
        memory_id=_memory_id(turn_id, "observed_world_state"),
        kind="observed_world_state",
        title="Observed ATM10 world state",
        summary=(
            f"Turn recalled {len(citations)} cited world source(s) for the current query."
        ),
        scope=("project:ATM10-Agent", turn_id),
        content={
            "query": query,
            "world_status": world.get("status"),
            "world_backend": world.get("backend"),
            "citations": citations,
            "knowledge_readiness": (
                world.get("knowledge", {}).get("readiness")
                if isinstance(world.get("knowledge"), Mapping)
                else None
            ),
        },
        created_at_utc=timestamp_utc,
        observed_at_utc=timestamp_utc,
        provenance=(trace_ref, *source_refs),
        trust=MemoryTrust(
            confidence=0.8 if citations else 0.5,
            authority_kind="source_citation" if citations else "direct_observation",
            authority=(
                "cited ATM10 world sources observed during one turn"
                if citations
                else "absence of a retrieval match observed during one turn"
            ),
            freshness=1.0,
            salience=0.6,
            temperature="hot",
        ),
        lifecycle=MemoryLifecycle(state="captured", current_recall="allowed"),
    )
    episode_memory = MemoryObject(
        memory_id=_memory_id(turn_id, "player_episode"),
        kind="player_episode",
        title="ATM10 companion turn episode",
        summary=f"Companion turn ended with status {turn_status}.",
        scope=("project:ATM10-Agent", turn_id),
        content={
            "query": query,
            "turn_status": turn_status,
            "response_mode": response.get("mode"),
            "action_intent": action.get("intent"),
            "action_status": action.get("status"),
            "dry_run": action.get("dry_run"),
            "executed": action.get("executed"),
        },
        created_at_utc=timestamp_utc,
        observed_at_utc=timestamp_utc,
        provenance=(trace_ref,),
        trust=MemoryTrust(
            confidence=1.0,
            authority_kind="direct_observation",
            authority="ATM10 companion turn artifact",
            freshness=1.0,
            salience=0.5,
            temperature="hot",
        ),
        lifecycle=MemoryLifecycle(state="captured", current_recall="allowed"),
    )
    working_context = MemoryObject(
        memory_id="memory:working_context:current",
        kind="working_context",
        title="Current ATM10 working context",
        summary="Mutable pointer to the most recent companion turn context.",
        scope=("project:ATM10-Agent", "runtime:current"),
        content={
            "turn_id": turn_id,
            "query": query,
            "turn_status": turn_status,
            "world_memory_id": world_memory.memory_id,
            "episode_memory_id": episode_memory.memory_id,
        },
        created_at_utc=timestamp_utc,
        observed_at_utc=timestamp_utc,
        provenance=(trace_ref,),
        trust=MemoryTrust(
            confidence=1.0,
            authority_kind="direct_observation",
            authority="current in-process turn context",
            freshness=1.0,
            salience=1.0,
            temperature="hot",
        ),
        lifecycle=MemoryLifecycle(state="captured", current_recall="preferred"),
    )

    durable_ids = (store.append(world_memory), store.append(episode_memory))
    context_path = store.write_working_context(working_context)
    return {
        "schema_version": MEMORY_CAPTURE_SCHEMA_VERSION,
        "status": "ok",
        "degraded": False,
        "degradation_reason": None,
        "durable_object_ids": list(durable_ids),
        "objects_store": str(store.objects_path),
        "working_context": str(context_path),
        "authority_ceiling": MEMORY_AUTHORITY_CEILING,
        "claim_limit": (
            "Captured memory records what this turn observed; it is not proof "
            "and does not replace current world sources or mutable state."
        ),
    }
