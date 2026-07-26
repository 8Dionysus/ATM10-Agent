"""Temporal, provenance-aware memory objects for the ATM10 companion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any, Mapping

from atm10_agent.proof import ProvenanceRef


MEMORY_OBJECT_SCHEMA_VERSION = "atm10_memory_object_v1"
MEMORY_KINDS = {
    "observed_world_state",
    "player_episode",
    "semantic_game_knowledge",
    "procedural_gameplay",
    "working_context",
}
MEMORY_AUTHORITY_KINDS = {
    "direct_observation",
    "source_citation",
    "agent_derived",
    "operator_reviewed",
}
MEMORY_TEMPERATURES = {"hot", "warm", "cool", "cold", "frozen"}
MEMORY_LIFECYCLE_STATES = {
    "captured",
    "proposed",
    "confirmed",
    "frozen",
    "superseded",
    "retracted",
    "archived",
}
MEMORY_RECALL_STATES = {"preferred", "allowed", "historical", "withdrawn"}
MEMORY_FREEZE_BASES = {"operator_review", "source_boundary", "product_contract"}
MEMORY_AUTHORITY_CEILING = "memory_not_proof_or_world_authority"


def _validate_timestamp(name: str, value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")


def _validate_axis(name: str, value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 <= value <= 1.0
    ):
        raise ValueError(f"{name} must be a finite value in the 0..1 range")


@dataclass(frozen=True)
class MemoryTrust:
    """Interpretation posture whose axes must not collapse into one score."""

    confidence: float
    authority_kind: str
    authority: str
    freshness: float
    salience: float
    temperature: str

    def __post_init__(self) -> None:
        _validate_axis("confidence", self.confidence)
        _validate_axis("freshness", self.freshness)
        _validate_axis("salience", self.salience)
        if self.authority_kind not in MEMORY_AUTHORITY_KINDS:
            raise ValueError(f"unsupported memory authority_kind: {self.authority_kind!r}")
        if not self.authority.strip():
            raise ValueError("memory authority must not be empty")
        if self.temperature not in MEMORY_TEMPERATURES:
            raise ValueError(f"unsupported memory temperature: {self.temperature!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "authority_kind": self.authority_kind,
            "authority": self.authority,
            "freshness": self.freshness,
            "salience": self.salience,
            "temperature": self.temperature,
        }


@dataclass(frozen=True)
class MemoryLifecycle:
    """Explicit lifecycle and current recall posture for one immutable object."""

    state: str
    current_recall: str
    freeze_basis: str | None = None
    supersedes: tuple[str, ...] = ()
    contradiction_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.state not in MEMORY_LIFECYCLE_STATES:
            raise ValueError(f"unsupported memory lifecycle state: {self.state!r}")
        if self.current_recall not in MEMORY_RECALL_STATES:
            raise ValueError(f"unsupported current_recall state: {self.current_recall!r}")
        if self.state == "frozen" and self.freeze_basis not in MEMORY_FREEZE_BASES:
            raise ValueError("frozen memory requires an explicit supported freeze_basis")
        if self.state != "frozen" and self.freeze_basis is not None:
            raise ValueError("freeze_basis is valid only for frozen memory")
        if self.state == "retracted" and self.current_recall != "withdrawn":
            raise ValueError("retracted memory must be withdrawn from current recall")
        for name, values in (
            ("supersedes", self.supersedes),
            ("contradiction_refs", self.contradiction_refs),
        ):
            if any(not item.strip() for item in values):
                raise ValueError(f"{name} must contain non-empty refs")
            if len(set(values)) != len(values):
                raise ValueError(f"{name} refs must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "current_recall": self.current_recall,
            "freeze_basis": self.freeze_basis,
            "supersedes": list(self.supersedes),
            "contradiction_refs": list(self.contradiction_refs),
        }


@dataclass(frozen=True)
class MemoryObject:
    """One append-only memory record; later change is represented by a new record."""

    memory_id: str
    kind: str
    title: str
    summary: str
    scope: tuple[str, ...]
    content: Mapping[str, Any]
    created_at_utc: str
    observed_at_utc: str
    provenance: tuple[ProvenanceRef, ...]
    trust: MemoryTrust
    lifecycle: MemoryLifecycle
    authority_ceiling: str = MEMORY_AUTHORITY_CEILING
    schema_version: str = MEMORY_OBJECT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MEMORY_OBJECT_SCHEMA_VERSION:
            raise ValueError("unsupported memory object schema_version")
        for name, value in (
            ("memory_id", self.memory_id),
            ("title", self.title),
            ("summary", self.summary),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.kind not in MEMORY_KINDS:
            raise ValueError(f"unsupported memory kind: {self.kind!r}")
        if not self.scope or any(not item.strip() for item in self.scope):
            raise ValueError("memory scope must contain non-empty values")
        if len(set(self.scope)) != len(self.scope):
            raise ValueError("memory scope values must be unique")
        _validate_timestamp("created_at_utc", self.created_at_utc)
        _validate_timestamp("observed_at_utc", self.observed_at_utc)
        if not self.provenance:
            raise ValueError("memory provenance must not be empty")
        if self.authority_ceiling != MEMORY_AUTHORITY_CEILING:
            raise ValueError(
                f"authority_ceiling must be {MEMORY_AUTHORITY_CEILING!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "memory_id": self.memory_id,
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "scope": list(self.scope),
            "content": dict(self.content),
            "created_at_utc": self.created_at_utc,
            "observed_at_utc": self.observed_at_utc,
            "provenance": [item.to_dict() for item in self.provenance],
            "trust": self.trust.to_dict(),
            "lifecycle": self.lifecycle.to_dict(),
            "authority_ceiling": self.authority_ceiling,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MemoryObject":
        content = payload.get("content")
        trust = payload.get("trust")
        lifecycle = payload.get("lifecycle")
        scope = payload.get("scope")
        provenance = payload.get("provenance")
        if not isinstance(content, Mapping):
            raise ValueError("memory content must be an object")
        if not isinstance(trust, Mapping):
            raise ValueError("memory trust must be an object")
        if not isinstance(lifecycle, Mapping):
            raise ValueError("memory lifecycle must be an object")
        if not isinstance(scope, list):
            raise ValueError("memory scope must be an array")
        if not isinstance(provenance, list) or any(
            not isinstance(item, Mapping) for item in provenance
        ):
            raise ValueError("memory provenance must be an array of objects")
        supersedes = lifecycle.get("supersedes")
        contradiction_refs = lifecycle.get("contradiction_refs")
        if not isinstance(supersedes, list):
            raise ValueError("memory supersedes must be an array")
        if not isinstance(contradiction_refs, list):
            raise ValueError("memory contradiction_refs must be an array")
        try:
            confidence = float(trust.get("confidence"))
            freshness = float(trust.get("freshness"))
            salience = float(trust.get("salience"))
        except (TypeError, ValueError) as exc:
            raise ValueError("memory trust axes must be numeric") from exc

        return cls(
            schema_version=str(payload.get("schema_version", "")),
            memory_id=str(payload.get("memory_id", "")),
            kind=str(payload.get("kind", "")),
            title=str(payload.get("title", "")),
            summary=str(payload.get("summary", "")),
            scope=tuple(str(item) for item in scope),
            content=content,
            created_at_utc=str(payload.get("created_at_utc", "")),
            observed_at_utc=str(payload.get("observed_at_utc", "")),
            provenance=tuple(
                ProvenanceRef(
                    ref=str(item.get("ref", "")),
                    kind=str(item.get("kind", "")),
                    role=str(item.get("role", "supporting")),
                    owner=str(item.get("owner", "ATM10-Agent")),
                    revision=(
                        str(item["revision"]) if item.get("revision") is not None else None
                    ),
                )
                for item in provenance
            ),
            trust=MemoryTrust(
                confidence=confidence,
                authority_kind=str(trust.get("authority_kind", "")),
                authority=str(trust.get("authority", "")),
                freshness=freshness,
                salience=salience,
                temperature=str(trust.get("temperature", "")),
            ),
            lifecycle=MemoryLifecycle(
                state=str(lifecycle.get("state", "")),
                current_recall=str(lifecycle.get("current_recall", "")),
                freeze_basis=(
                    str(lifecycle.get("freeze_basis"))
                    if lifecycle.get("freeze_basis") is not None
                    else None
                ),
                supersedes=tuple(
                    str(item) for item in supersedes
                ),
                contradiction_refs=tuple(
                    str(item) for item in contradiction_refs
                ),
            ),
            authority_ceiling=str(payload.get("authority_ceiling", "")),
        )
