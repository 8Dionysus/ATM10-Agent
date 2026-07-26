"""Stable contracts for one ATM10 companion turn."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


TURN_SCHEMA_VERSION = "atm10_companion_turn_v1"
TRACE_SCHEMA_VERSION = "atm10_turn_trace_v1"
STATE_SCHEMA_VERSION = "atm10_companion_state_v1"


@dataclass(frozen=True)
class TurnRequest:
    prompt: str
    query: str
    image_path: Path | None = None
    world_docs: Path | None = None
    topk: int = 3
    action_intent: str | None = None
    voice: bool = False

    def validate(self) -> None:
        if not self.prompt.strip():
            raise ValueError("prompt must not be empty")
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if self.topk <= 0:
            raise ValueError("topk must be positive")


@dataclass(frozen=True)
class TurnResult:
    turn_id: str
    timestamp_utc: str
    status: str
    degraded: bool
    degradation_reasons: tuple[str, ...]
    stages: Mapping[str, Any]
    citations: tuple[Mapping[str, Any], ...]
    response: Mapping[str, Any]
    action: Mapping[str, Any]
    voice: Mapping[str, Any]
    trace: Mapping[str, Any] = field(default_factory=dict)
    replay_of: str | None = None
    schema_version: str = TURN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["degradation_reasons"] = list(self.degradation_reasons)
        payload["citations"] = [dict(item) for item in self.citations]
        return payload
