"""Dry-run-only action planning owned by the companion core."""

from __future__ import annotations

from typing import Any


_TEMPLATES: dict[str, tuple[dict[str, Any], ...]] = {
    "open_quest_book": (
        {"type": "key_tap", "key": "l"},
        {"type": "wait", "duration_ms": 250},
    ),
    "check_inventory_tool": (
        {"type": "key_tap", "key": "e"},
        {"type": "wait", "duration_ms": 150},
    ),
    "open_world_map": (
        {"type": "key_tap", "key": "m"},
        {"type": "wait", "duration_ms": 200},
    ),
}


def plan(intent: str | None) -> dict[str, Any]:
    if intent is None:
        return {
            "schema_version": "atm10_action_plan_v1",
            "status": "not_requested",
            "dry_run": True,
            "executed": False,
            "intent": None,
            "actions": [],
        }
    normalized = intent.strip().lower()
    actions = _TEMPLATES.get(normalized)
    if actions is None:
        return {
            "schema_version": "atm10_action_plan_v1",
            "status": "degraded",
            "dry_run": True,
            "executed": False,
            "intent": normalized,
            "actions": [],
            "degradation_reason": "unsupported_action_intent",
        }
    return {
        "schema_version": "atm10_action_plan_v1",
        "status": "planned",
        "dry_run": True,
        "executed": False,
        "intent": normalized,
        "actions": [dict(item) for item in actions],
    }
