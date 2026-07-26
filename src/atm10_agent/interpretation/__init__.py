"""Interpretation stage for one companion turn."""

from __future__ import annotations

from typing import Any, Mapping


def interpret(
    *,
    perception: Mapping[str, Any],
    query: str,
    action_intent: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": "atm10_interpretation_v1",
        "status": "ok",
        "observation": str(perception.get("summary", "")).strip(),
        "world_query": query.strip(),
        "requested_action_intent": action_intent,
        "constraints": ["local_first", "dry_run_only"],
    }
