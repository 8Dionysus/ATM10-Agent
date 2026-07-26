from __future__ import annotations

from atm10_agent.proof import ProvenanceRef
from atm10_agent.providers import (
    ProviderCandidate,
    build_turn_provider_routes,
    select_provider,
)


SOURCE = (
    ProvenanceRef(
        kind="source",
        ref="atm10_agent.providers.routing:test",
        role="primary",
    ),
)


def _candidate(
    provider_id: str,
    status: str,
    reason: str | None = None,
) -> ProviderCandidate:
    return ProviderCandidate(
        provider_id=provider_id,
        status=status,
        reason=reason,
        return_handle=f"atm10://providers/{provider_id}",
        evidence=SOURCE,
    )


def test_provider_route_records_selected_provider_and_return_handle() -> None:
    result = select_provider(
        capability="perception.vlm",
        decision_id="turn:test:provider:perception.vlm",
        trace_ref="turn:test",
        candidates=(_candidate("local-vlm", "ready"),),
    )

    assert result["schema_version"] == "atm10_provider_route_v1"
    assert result["status"] == "selected"
    assert result["selected_provider"] == "local-vlm"
    assert result["return_handle"] == "atm10://providers/local-vlm"
    assert result["fallback_reason"] is None
    assert result["global_router"] is False
    assert result["attempts"][0]["evidence"]


def test_provider_route_preserves_unavailable_fallback_reason() -> None:
    result = select_provider(
        capability="response.text",
        decision_id="turn:test:provider:response.text",
        trace_ref="turn:test",
        candidates=(
            _candidate("local-text", "unavailable", "model_not_loaded"),
            _candidate("deterministic-text", "ready"),
        ),
    )

    assert result["status"] == "degraded"
    assert result["selected_provider"] == "deterministic-text"
    assert result["fallback_reason"] == "local-text:model_not_loaded"
    assert [item["status"] for item in result["attempts"]] == [
        "unavailable",
        "ready",
    ]


def test_provider_route_distinguishes_rejection_and_absence() -> None:
    rejected = select_provider(
        capability="action.game_tool",
        decision_id="turn:test:provider:action.game_tool",
        trace_ref="turn:test",
        candidates=(
            _candidate("dry-run-tool", "rejected", "intent_not_allowlisted"),
        ),
    )
    unavailable = select_provider(
        capability="voice.tts",
        decision_id="turn:test:provider:voice.tts",
        trace_ref="turn:test",
        candidates=(),
    )
    not_requested = select_provider(
        capability="voice.asr",
        decision_id="turn:test:provider:voice.asr",
        trace_ref="turn:test",
        candidates=(),
        requested=False,
    )

    assert rejected["status"] == "rejected"
    assert rejected["fallback_reason"] == "dry-run-tool:intent_not_allowlisted"
    assert unavailable["status"] == "unavailable"
    assert unavailable["fallback_reason"] == "no_provider_candidates"
    assert not_requested["status"] == "not_requested"
    assert not_requested["fallback_reason"] is None


def test_turn_bundle_covers_active_provider_families_without_global_router() -> None:
    bundle = build_turn_provider_routes(
        turn_id="turn:test",
        perception={
            "status": "ok",
            "provider": "deterministic_stub_v1",
            "source": "deterministic_placeholder",
        },
        world={
            "status": "ok",
            "backend": "file",
        },
        response={
            "status": "ok",
            "mode": "grounded_file_world",
        },
        action={
            "status": "planned",
            "intent": "open_quest_book",
        },
        voice={
            "status": "not_requested",
            "provider": None,
        },
    )

    assert bundle["schema_version"] == "atm10_provider_route_bundle_v1"
    assert bundle["status"] == "ok"
    assert bundle["global_router"] is False
    assert set(bundle["routes"]) == {
        "perception.capture",
        "perception.vlm",
        "world.store",
        "world.relations",
        "response.text",
        "voice.asr",
        "voice.tts",
        "action.game_tool",
    }
    assert bundle["routes"]["perception.vlm"]["selected_provider"] == (
        "deterministic_stub_v1"
    )
    assert bundle["routes"]["world.store"]["selected_provider"] == (
        "embedded_file_world"
    )
    assert bundle["routes"]["voice.asr"]["status"] == "not_requested"
    assert bundle["routes"]["voice.tts"]["status"] == "not_requested"
    assert bundle["routes"]["action.game_tool"]["selected_provider"] == (
        "dry_run_game_tool_planner"
    )


def test_turn_bundle_surfaces_unavailable_voice_and_rejected_tool() -> None:
    bundle = build_turn_provider_routes(
        turn_id="turn:test",
        perception={
            "status": "ok",
            "provider": "deterministic_stub_v1",
            "source": "provided_image",
        },
        world={
            "status": "degraded",
            "degradation_reason": "no_retrieval_match",
        },
        response={
            "status": "degraded",
            "mode": "ungrounded_degraded",
        },
        action={
            "status": "degraded",
            "intent": "destroy_world",
            "degradation_reason": "unsupported_action_intent",
        },
        voice={
            "status": "degraded",
            "provider": None,
            "degradation_reason": "voice_provider_not_configured",
        },
    )

    assert bundle["status"] == "degraded"
    assert bundle["routes"]["voice.tts"]["status"] == "unavailable"
    assert bundle["routes"]["action.game_tool"]["status"] == "rejected"
    assert bundle["routes"]["world.store"]["status"] == "degraded"
    assert bundle["routes"]["response.text"]["status"] == "degraded"
