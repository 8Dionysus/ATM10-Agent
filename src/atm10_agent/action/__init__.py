"""Pure dry-run action contracts owned by the autonomous companion package."""

from __future__ import annotations

from typing import Any, Mapping


INTENT_SCHEMA_VERSION = "automation_intent_v1"
PLAN_SCHEMA_VERSION = "automation_plan_v1"
ACTION_RESULT_SCHEMA_VERSION = "atm10_action_plan_v1"

_ALLOWED_PRIORITIES = {"low", "normal", "high"}
_ALLOWED_ACTION_TYPES = {
    "key_tap",
    "key_hold",
    "mouse_move",
    "mouse_click",
    "mouse_scroll",
    "wait",
}
_ALLOWED_MOUSE_BUTTONS = {"left", "right", "middle"}
_PLANNING_STRING_FIELDS = {
    "intent_type",
    "intent_id",
    "trace_id",
    "intent_schema_version",
    "adapter_name",
    "adapter_version",
}
_ADAPTER_NAME = "intent_to_automation_plan"
_ADAPTER_VERSION = "v1"

_INTENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "open_quest_book": {
        "goal": "open quest book and inspect active objective",
        "tags": ["quests", "ui"],
        "actions": [
            {"id": "open_quest_book", "type": "key_tap", "key": "l"},
            {"id": "wait_ui_stabilize", "type": "wait", "duration_ms": 250, "repeats": 2},
            {
                "id": "focus_first_quest_line",
                "type": "mouse_click",
                "button": "left",
                "x": 1200,
                "y": 640,
            },
        ],
    },
    "check_inventory_tool": {
        "goal": "open inventory and verify tool durability",
        "tags": ["inventory", "status"],
        "actions": [
            {"id": "open_inventory", "type": "key_tap", "key": "e"},
            {"id": "wait_inventory_ui", "type": "wait", "duration_ms": 150},
            {"id": "hover_tool_slot", "type": "mouse_move", "x": 1130, "y": 510},
            {"id": "wait_tooltip_render", "type": "wait", "duration_ms": 120},
        ],
    },
    "open_world_map": {
        "goal": "open world map and focus current position",
        "tags": ["map", "navigation"],
        "actions": [
            {"id": "open_world_map", "type": "key_tap", "key": "m"},
            {"id": "wait_world_map_ui", "type": "wait", "duration_ms": 200, "repeats": 2},
            {"id": "focus_player_marker", "type": "key_tap", "key": "space"},
        ],
    },
}


def available_intents() -> tuple[str, ...]:
    """Return the deterministic action intents supported by the core."""

    return tuple(_INTENT_TEMPLATES)


def _normalize_optional_string(raw_payload: Mapping[str, Any], field: str) -> str | None:
    if field not in raw_payload:
        return None
    value = str(raw_payload.get(field, "")).strip()
    if not value:
        raise ValueError(f"{field} must be non-empty string when provided.")
    return value


def _normalize_string_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be array when provided.")
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_intent_payload(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    schema_version = str(raw_payload.get("schema_version", INTENT_SCHEMA_VERSION)).strip()
    if schema_version != INTENT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported intent schema_version: {schema_version!r}. "
            f"Expected {INTENT_SCHEMA_VERSION!r}."
        )

    intent_type = str(raw_payload.get("intent_type", "")).strip().lower()
    if intent_type not in _INTENT_TEMPLATES:
        raise ValueError(f"Unsupported intent_type: {intent_type!r}.")

    template = _INTENT_TEMPLATES[intent_type]
    goal = str(raw_payload.get("goal", template["goal"])).strip()
    if not goal:
        raise ValueError("intent goal must be non-empty string.")

    priority = str(raw_payload.get("priority", "normal")).strip().lower()
    if priority not in _ALLOWED_PRIORITIES:
        raise ValueError(f"intent priority must be one of {sorted(_ALLOWED_PRIORITIES)}.")

    tags = _normalize_string_list(raw_payload.get("tags"), field="tags")
    if not tags:
        tags = list(template["tags"])
    if intent_type not in tags:
        tags.append(intent_type)

    constraints = _normalize_string_list(raw_payload.get("constraints"), field="constraints")
    if "dry_run_only" not in constraints:
        constraints.insert(0, "dry_run_only")

    context = raw_payload.get("context", {})
    if context is None:
        context = {}
    if not isinstance(context, Mapping):
        raise ValueError("context must be JSON object when provided.")
    normalized_context = dict(context)
    source = str(raw_payload.get("source", "")).strip()
    if source:
        normalized_context["source"] = source
    note = str(raw_payload.get("note", "")).strip()
    if note:
        normalized_context["note"] = note
    normalized_context["intent_type"] = intent_type

    return {
        "schema_version": schema_version,
        "intent_type": intent_type,
        "goal": goal,
        "priority": priority,
        "tags": tags,
        "constraints": constraints,
        "context": normalized_context,
        "intent_id": _normalize_optional_string(raw_payload, "intent_id"),
        "trace_id": _normalize_optional_string(raw_payload, "trace_id"),
    }


def build_plan_from_intent(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic ``automation_plan_v1`` without performing I/O."""

    intent = _normalize_intent_payload(raw_payload)
    planning: dict[str, Any] = {
        "intent_type": intent["intent_type"],
        "intent_schema_version": INTENT_SCHEMA_VERSION,
        "adapter_name": _ADAPTER_NAME,
        "adapter_version": _ADAPTER_VERSION,
    }
    if intent["intent_id"] is not None:
        planning["intent_id"] = intent["intent_id"]
    if intent["trace_id"] is not None:
        planning["trace_id"] = intent["trace_id"]

    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "intent": {
            "goal": intent["goal"],
            "priority": intent["priority"],
            "tags": intent["tags"],
            "constraints": intent["constraints"],
        },
        "context": intent["context"],
        "planning": planning,
        "actions": [dict(action) for action in _INTENT_TEMPLATES[intent["intent_type"]]["actions"]],
    }


def _coerce_int(name: str, value: Any, *, min_value: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be integer.")
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value}.")
    return value


def _normalize_action(action: Mapping[str, Any], *, default_id: str) -> dict[str, Any]:
    action_type = str(action.get("type", "")).strip().lower()
    if action_type not in _ALLOWED_ACTION_TYPES:
        raise ValueError(f"Unsupported action type: {action_type!r}")

    action_id = str(action.get("id", default_id)).strip() or default_id
    repeats = _coerce_int("repeats", action.get("repeats", 1), min_value=1)
    params: dict[str, Any] = {}
    base_duration_ms = 0

    if action_type == "key_tap":
        key = str(action.get("key", "")).strip()
        if not key:
            raise ValueError("key_tap action requires non-empty key.")
        params["key"] = key
        base_duration_ms = 50
    elif action_type == "key_hold":
        key = str(action.get("key", "")).strip()
        if not key:
            raise ValueError("key_hold action requires non-empty key.")
        hold_ms = _coerce_int("hold_ms", action.get("hold_ms"), min_value=1)
        params.update(key=key, hold_ms=hold_ms)
        base_duration_ms = hold_ms
    elif action_type == "mouse_move":
        params["x"] = _coerce_int("x", action.get("x"))
        params["y"] = _coerce_int("y", action.get("y"))
        base_duration_ms = 30
    elif action_type == "mouse_click":
        button = str(action.get("button", "left")).strip().lower()
        if button not in _ALLOWED_MOUSE_BUTTONS:
            raise ValueError(f"mouse_click button must be one of {_ALLOWED_MOUSE_BUTTONS}.")
        params["button"] = button
        if "x" in action:
            params["x"] = _coerce_int("x", action.get("x"))
        if "y" in action:
            params["y"] = _coerce_int("y", action.get("y"))
        base_duration_ms = 40
    elif action_type == "mouse_scroll":
        delta = _coerce_int("delta", action.get("delta"))
        if delta == 0:
            raise ValueError("mouse_scroll delta must not be 0.")
        params["delta"] = delta
        base_duration_ms = 30
    else:
        duration_ms = _coerce_int("duration_ms", action.get("duration_ms"), min_value=1)
        params["duration_ms"] = duration_ms
        base_duration_ms = duration_ms

    return {
        "id": action_id,
        "type": action_type,
        "params": params,
        "repeats": repeats,
        "estimated_duration_ms": base_duration_ms * repeats,
    }


def _normalize_plan_intent(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_intent = raw_payload.get("intent")
    if raw_intent is None:
        return {
            "goal": "unspecified",
            "priority": "normal",
            "tags": [],
            "constraints": ["dry_run_only"],
        }
    if not isinstance(raw_intent, Mapping):
        raise ValueError("intent must be JSON object when provided.")

    goal = str(raw_intent.get("goal", "")).strip()
    if not goal:
        raise ValueError("intent.goal must be non-empty string.")
    priority = str(raw_intent.get("priority", "normal")).strip().lower()
    if priority not in _ALLOWED_PRIORITIES:
        raise ValueError(f"intent.priority must be one of {sorted(_ALLOWED_PRIORITIES)}.")

    tags = _normalize_string_list(raw_intent.get("tags", []), field="intent.tags")
    constraints = _normalize_string_list(
        raw_intent.get("constraints", ["dry_run_only"]),
        field="intent.constraints",
    )
    if "dry_run_only" not in constraints:
        constraints.insert(0, "dry_run_only")
    return {
        "goal": goal,
        "priority": priority,
        "tags": tags,
        "constraints": constraints,
    }


def normalize_plan(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize an action plan while preserving the dry-run fence."""

    schema_version = str(raw_payload.get("schema_version", PLAN_SCHEMA_VERSION)).strip()
    if schema_version != PLAN_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported schema_version: {schema_version!r}. "
            f"Expected {PLAN_SCHEMA_VERSION!r}."
        )

    raw_planning = raw_payload.get("planning")
    planning: dict[str, Any] | None = None
    if raw_planning is not None:
        if not isinstance(raw_planning, Mapping):
            raise ValueError("planning must be JSON object when provided.")
        planning = dict(raw_planning)
        for key in _PLANNING_STRING_FIELDS:
            if key not in planning:
                continue
            value = str(planning[key]).strip()
            if not value:
                raise ValueError(f"planning.{key} must be non-empty string when provided.")
            planning[key] = value

    raw_actions = raw_payload.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise ValueError("Plan payload must contain non-empty actions list.")

    actions: list[dict[str, Any]] = []
    action_ids: set[str] = set()
    for index, raw_action in enumerate(raw_actions, start=1):
        if not isinstance(raw_action, Mapping):
            raise ValueError(f"Action #{index} must be JSON object.")
        action = _normalize_action(raw_action, default_id=f"a{index:03d}")
        action_id = str(action["id"])
        if action_id in action_ids:
            raise ValueError(f"Action id must be unique: {action_id!r}")
        action_ids.add(action_id)
        actions.append(action)

    context = raw_payload.get("context", {})
    if context is None:
        context = {}
    if not isinstance(context, Mapping):
        raise ValueError("context must be JSON object when provided.")

    normalized: dict[str, Any] = {
        "schema_version": schema_version,
        "dry_run": True,
        "intent": _normalize_plan_intent(raw_payload),
        "context": dict(context),
        "actions": actions,
    }
    if planning is not None:
        normalized["planning"] = planning
    return normalized


def build_dry_run_execution(normalized_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Expand a normalized plan into evidence of what would happen."""

    if normalized_payload.get("dry_run") is not True:
        raise ValueError("normalized action plan must preserve dry_run=true.")
    raw_actions = normalized_payload.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise ValueError("normalized action plan must contain actions.")

    steps: list[dict[str, Any]] = []
    for action in raw_actions:
        if not isinstance(action, Mapping):
            raise ValueError("normalized action must be object.")
        repeats = int(action["repeats"])
        for iteration in range(1, repeats + 1):
            steps.append(
                {
                    "step_index": len(steps) + 1,
                    "action_id": str(action["id"]),
                    "action_type": str(action["type"]),
                    "iteration": iteration,
                    "params": dict(action["params"]),
                    "dry_run_message": (
                        f"DRY-RUN: would execute {action['type']} ({iteration}/{repeats})"
                    ),
                }
            )

    return {
        "dry_run": True,
        "executed": False,
        "step_count": len(steps),
        "estimated_total_duration_ms": sum(
            int(action["estimated_duration_ms"]) for action in raw_actions
        ),
        "steps": steps,
    }


def plan(
    intent: str | None,
    *,
    intent_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Plan one product action; this function can never emit system input."""

    if intent is None:
        return {
            "schema_version": ACTION_RESULT_SCHEMA_VERSION,
            "status": "not_requested",
            "dry_run": True,
            "executed": False,
            "intent": None,
            "actions": [],
        }

    normalized_intent = intent.strip().lower()
    if normalized_intent not in _INTENT_TEMPLATES:
        result: dict[str, Any] = {
            "schema_version": ACTION_RESULT_SCHEMA_VERSION,
            "status": "degraded",
            "dry_run": True,
            "executed": False,
            "intent": normalized_intent,
            "actions": [],
            "degradation_reason": "unsupported_action_intent",
        }
        if intent_id is not None:
            result["intent_id"] = intent_id
        if trace_id is not None:
            result["trace_id"] = trace_id
        return result

    raw_intent: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "intent_type": normalized_intent,
    }
    if intent_id is not None:
        raw_intent["intent_id"] = intent_id
    if trace_id is not None:
        raw_intent["trace_id"] = trace_id
    action_plan = build_plan_from_intent(raw_intent)
    normalized_plan = normalize_plan(action_plan)
    execution = build_dry_run_execution(normalized_plan)

    result = {
        "schema_version": ACTION_RESULT_SCHEMA_VERSION,
        "status": "planned",
        "dry_run": True,
        "executed": False,
        "intent": normalized_intent,
        "actions": [dict(action) for action in action_plan["actions"]],
        "normalized_plan": normalized_plan,
        "execution": execution,
    }
    if intent_id is not None:
        result["intent_id"] = intent_id
    if trace_id is not None:
        result["trace_id"] = trace_id
    return result
