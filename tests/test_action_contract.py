from __future__ import annotations

import pytest

from atm10_agent.action import (
    available_intents,
    build_dry_run_execution,
    build_plan_from_intent,
    normalize_plan,
    plan,
)


def test_package_owns_all_canonical_intent_templates() -> None:
    assert available_intents() == (
        "open_quest_book",
        "check_inventory_tool",
        "open_world_map",
    )

    expected_action_types = {
        "open_quest_book": ["key_tap", "wait", "mouse_click"],
        "check_inventory_tool": ["key_tap", "wait", "mouse_move", "wait"],
        "open_world_map": ["key_tap", "wait", "key_tap"],
    }
    for intent, action_types in expected_action_types.items():
        action_plan = build_plan_from_intent(
            {
                "schema_version": "automation_intent_v1",
                "intent_type": intent,
                "intent_id": f"intent:{intent}",
                "trace_id": f"trace:{intent}",
            }
        )
        assert [item["type"] for item in action_plan["actions"]] == action_types
        assert action_plan["planning"]["intent_id"] == f"intent:{intent}"
        assert action_plan["planning"]["trace_id"] == f"trace:{intent}"
        assert action_plan["intent"]["constraints"][0] == "dry_run_only"


def test_normalization_and_execution_preserve_dry_run_and_trace_correlation() -> None:
    action_plan = build_plan_from_intent(
        {
            "intent_type": "open_quest_book",
            "intent_id": "intent-001",
            "trace_id": "trace-001",
            "source": "voice_intent",
        }
    )
    normalized = normalize_plan(action_plan)
    execution = build_dry_run_execution(normalized)

    assert normalized["dry_run"] is True
    assert normalized["planning"]["intent_id"] == "intent-001"
    assert normalized["planning"]["trace_id"] == "trace-001"
    assert normalized["context"]["source"] == "voice_intent"
    assert execution["dry_run"] is True
    assert execution["executed"] is False
    assert execution["step_count"] == 4
    assert execution["steps"][1]["dry_run_message"].startswith(
        "DRY-RUN: would execute wait"
    )


def test_normalizer_supports_the_full_protected_action_vocabulary() -> None:
    normalized = normalize_plan(
        {
            "actions": [
                {"id": "tap", "type": "key_tap", "key": "m"},
                {"id": "hold", "type": "key_hold", "key": "shift", "hold_ms": 75},
                {"id": "move", "type": "mouse_move", "x": 10, "y": 20},
                {"id": "click", "type": "mouse_click", "button": "right"},
                {"id": "scroll", "type": "mouse_scroll", "delta": -2},
                {"id": "wait", "type": "wait", "duration_ms": 25},
            ]
        }
    )
    assert [action["type"] for action in normalized["actions"]] == [
        "key_tap",
        "key_hold",
        "mouse_move",
        "mouse_click",
        "mouse_scroll",
        "wait",
    ]
    assert build_dry_run_execution(normalized)["step_count"] == 6


@pytest.mark.parametrize(
    "payload,error",
    [
        ({"schema_version": "automation_plan_v2", "actions": [{"type": "wait"}]}, "schema"),
        ({"actions": []}, "non-empty actions"),
        (
            {
                "actions": [
                    {"id": "same", "type": "key_tap", "key": "a"},
                    {"id": "same", "type": "key_tap", "key": "b"},
                ]
            },
            "unique",
        ),
        ({"actions": [{"type": "mouse_scroll", "delta": 0}]}, "must not be 0"),
    ],
)
def test_invalid_action_plans_are_rejected(payload: dict, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        normalize_plan(payload)


def test_companion_action_result_can_never_execute_input() -> None:
    result = plan(
        "open_world_map",
        intent_id="intent-world-map",
        trace_id="turn:world-map",
    )

    assert result["status"] == "planned"
    assert result["dry_run"] is True
    assert result["executed"] is False
    assert result["execution"]["executed"] is False
    assert result["intent_id"] == "intent-world-map"
    assert result["trace_id"] == "turn:world-map"
    assert result["normalized_plan"]["planning"]["intent_id"] == "intent-world-map"
    assert result["normalized_plan"]["planning"]["trace_id"] == "turn:world-map"


def test_unknown_intent_degrades_without_actions() -> None:
    result = plan("destroy_world", intent_id="intent-negative", trace_id="turn:negative")

    assert result["status"] == "degraded"
    assert result["actions"] == []
    assert result["executed"] is False
    assert result["degradation_reason"] == "unsupported_action_intent"
    assert result["intent_id"] == "intent-negative"
    assert result["trace_id"] == "turn:negative"
