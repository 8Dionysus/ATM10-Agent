"""Thin, turn-local provider decisions without a global dispatch plane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from atm10_agent.proof import ProvenanceRef


PROVIDER_ROUTE_SCHEMA_VERSION = "atm10_provider_route_v1"
PROVIDER_ROUTE_BUNDLE_SCHEMA_VERSION = "atm10_provider_route_bundle_v1"
PROVIDER_CANDIDATE_STATUSES = {
    "ready",
    "degraded",
    "unavailable",
    "rejected",
}
PROVIDER_ROUTE_STATUSES = {
    "selected",
    "degraded",
    "unavailable",
    "rejected",
    "not_requested",
}
PROVIDER_ROUTE_AUTHORITY_CEILING = (
    "turn_local_selection_not_provider_quality_or_global_routing_authority"
)


@dataclass(frozen=True)
class ProviderCandidate:
    """One caller-supplied provider posture for a bounded capability."""

    provider_id: str
    status: str
    return_handle: str
    evidence: tuple[ProvenanceRef, ...]
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id must not be empty")
        if self.status not in PROVIDER_CANDIDATE_STATUSES:
            raise ValueError(f"unsupported provider candidate status: {self.status!r}")
        if not self.return_handle.strip():
            raise ValueError("provider return_handle must not be empty")
        if not self.evidence:
            raise ValueError("provider candidate evidence must not be empty")
        if any(not isinstance(item, ProvenanceRef) for item in self.evidence):
            raise ValueError("provider candidate evidence must use ProvenanceRef")
        if self.status == "ready" and self.reason is not None:
            raise ValueError("ready provider candidate must not carry a failure reason")
        if self.status != "ready" and (
            self.reason is None or not self.reason.strip()
        ):
            raise ValueError(
                f"{self.status} provider candidate requires an explicit reason"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "status": self.status,
            "return_handle": self.return_handle,
            "reason": self.reason,
            "evidence": [item.to_dict() for item in self.evidence],
        }


def _route_payload(
    *,
    capability: str,
    decision_id: str,
    trace_ref: str,
    status: str,
    selected: ProviderCandidate | None,
    fallback_reason: str | None,
    attempts: Sequence[ProviderCandidate],
    selection_basis: str,
) -> dict[str, Any]:
    if status not in PROVIDER_ROUTE_STATUSES:
        raise ValueError(f"unsupported provider route status: {status!r}")
    return {
        "schema_version": PROVIDER_ROUTE_SCHEMA_VERSION,
        "capability": capability,
        "decision_id": decision_id,
        "trace_ref": trace_ref,
        "status": status,
        "selected_provider": selected.provider_id if selected is not None else None,
        "fallback_reason": fallback_reason,
        "return_handle": selected.return_handle if selected is not None else None,
        "attempts": [item.to_dict() for item in attempts],
        "selection_basis": selection_basis,
        "global_router": False,
        "authority_ceiling": PROVIDER_ROUTE_AUTHORITY_CEILING,
        "claim_limit": (
            "This result records one bounded ATM10 provider decision; it does "
            "not prove provider quality, future availability, or optimality."
        ),
    }


def select_provider(
    *,
    capability: str,
    decision_id: str,
    trace_ref: str,
    candidates: Sequence[ProviderCandidate],
    requested: bool = True,
    allow_degraded: bool = False,
    selection_basis: str = "caller_ordered_candidates",
) -> dict[str, Any]:
    """Select one bounded provider while preserving every failed attempt."""

    for name, value in (
        ("capability", capability),
        ("decision_id", decision_id),
        ("trace_ref", trace_ref),
        ("selection_basis", selection_basis),
    ):
        if not value.strip():
            raise ValueError(f"{name} must not be empty")
    provider_ids = [item.provider_id for item in candidates]
    if len(set(provider_ids)) != len(provider_ids):
        raise ValueError("provider candidate ids must be unique")
    if not requested:
        return _route_payload(
            capability=capability,
            decision_id=decision_id,
            trace_ref=trace_ref,
            status="not_requested",
            selected=None,
            fallback_reason=None,
            attempts=(),
            selection_basis=selection_basis,
        )

    attempts: list[ProviderCandidate] = []
    failed_reasons: list[str] = []
    for candidate in candidates:
        attempts.append(candidate)
        if candidate.status == "ready":
            return _route_payload(
                capability=capability,
                decision_id=decision_id,
                trace_ref=trace_ref,
                status="degraded" if failed_reasons else "selected",
                selected=candidate,
                fallback_reason="; ".join(failed_reasons) or None,
                attempts=attempts,
                selection_basis=selection_basis,
            )
        failed_reasons.append(f"{candidate.provider_id}:{candidate.reason}")
        if candidate.status == "degraded" and allow_degraded:
            return _route_payload(
                capability=capability,
                decision_id=decision_id,
                trace_ref=trace_ref,
                status="degraded",
                selected=candidate,
                fallback_reason="; ".join(failed_reasons),
                attempts=attempts,
                selection_basis=selection_basis,
            )

    all_rejected = bool(attempts) and all(
        item.status == "rejected" for item in attempts
    )
    return _route_payload(
        capability=capability,
        decision_id=decision_id,
        trace_ref=trace_ref,
        status="rejected" if all_rejected else "unavailable",
        selected=None,
        fallback_reason="; ".join(failed_reasons) or "no_provider_candidates",
        attempts=attempts,
        selection_basis=selection_basis,
    )


def _source_candidate(
    *,
    provider_id: str,
    status: str,
    return_handle: str,
    reason: str | None = None,
) -> ProviderCandidate:
    return ProviderCandidate(
        provider_id=provider_id,
        status=status,
        return_handle=return_handle,
        reason=reason,
        evidence=(
            ProvenanceRef(
                kind="source",
                ref=return_handle,
                role="primary",
            ),
        ),
    )


def build_turn_provider_routes(
    *,
    turn_id: str,
    perception: Mapping[str, Any],
    world: Mapping[str, Any],
    response: Mapping[str, Any],
    action: Mapping[str, Any],
    voice: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe actual providers used by one companion turn."""

    def route(
        capability: str,
        candidates: Sequence[ProviderCandidate],
        *,
        requested: bool = True,
        allow_degraded: bool = False,
        basis: str,
    ) -> dict[str, Any]:
        return select_provider(
            capability=capability,
            decision_id=f"{turn_id}:provider:{capability}",
            trace_ref=turn_id,
            candidates=candidates,
            requested=requested,
            allow_degraded=allow_degraded,
            selection_basis=basis,
        )

    perception_status = (
        "ready" if perception.get("status") == "ok" else "degraded"
    )
    perception_reason = (
        None
        if perception_status == "ready"
        else str(perception.get("degradation_reason") or "perception_degraded")
    )
    source = str(perception.get("source", "")).strip()
    capture_provider = (
        "provided_image_input"
        if source == "provided_image"
        else "deterministic_placeholder"
    )
    world_status = "ready" if world.get("status") == "ok" else "degraded"
    world_reason = (
        None
        if world_status == "ready"
        else str(world.get("degradation_reason") or "world_degraded")
    )
    response_status = "ready" if response.get("status") == "ok" else "degraded"
    response_reason = (
        None
        if response_status == "ready"
        else str(response.get("mode") or "response_degraded")
    )

    voice_status = str(voice.get("status", ""))
    voice_requested = voice_status != "not_requested"
    voice_candidates: tuple[ProviderCandidate, ...] = ()
    if voice_requested:
        configured_voice = str(voice.get("provider") or "").strip()
        voice_candidates = (
            _source_candidate(
                provider_id=configured_voice or "configured_tts_provider",
                status="ready" if voice_status == "ok" else "unavailable",
                return_handle="atm10_agent.voice:render",
                reason=(
                    None
                    if voice_status == "ok"
                    else str(
                        voice.get("degradation_reason")
                        or "voice_provider_unavailable"
                    )
                ),
            ),
        )

    action_status = str(action.get("status", ""))
    action_requested = action_status != "not_requested"
    action_candidates: tuple[ProviderCandidate, ...] = ()
    if action_requested:
        action_candidates = (
            _source_candidate(
                provider_id="dry_run_game_tool_planner",
                status="ready" if action_status == "planned" else "rejected",
                return_handle="atm10_agent.action:plan",
                reason=(
                    None
                    if action_status == "planned"
                    else str(
                        action.get("degradation_reason")
                        or "action_route_rejected"
                    )
                ),
            ),
        )

    routes = {
        "perception.capture": route(
            "perception.capture",
            (
                _source_candidate(
                    provider_id=capture_provider,
                    status="ready",
                    return_handle="atm10_agent.perception:perceive",
                ),
            ),
            basis="explicit_image_or_local_placeholder",
        ),
        "perception.vlm": route(
            "perception.vlm",
            (
                _source_candidate(
                    provider_id=str(
                        perception.get("provider") or "unknown_perception_provider"
                    ),
                    status=perception_status,
                    return_handle="atm10_agent.perception:perceive",
                    reason=perception_reason,
                ),
            ),
            allow_degraded=True,
            basis="active_perception_result",
        ),
        "world.store": route(
            "world.store",
            (
                _source_candidate(
                    provider_id="embedded_file_world",
                    status=world_status,
                    return_handle="atm10_agent.world:recall",
                    reason=world_reason,
                ),
            ),
            allow_degraded=True,
            basis="embedded_baseline_before_optional_stores",
        ),
        "world.relations": route(
            "world.relations",
            (
                _source_candidate(
                    provider_id="embedded_product_kag",
                    status=world_status,
                    return_handle="atm10_agent.kag:build_kag_graph",
                    reason=world_reason,
                ),
            ),
            allow_degraded=True,
            basis="embedded_relations_before_optional_graph_store",
        ),
        "response.text": route(
            "response.text",
            (
                _source_candidate(
                    provider_id="deterministic_cited_response",
                    status=response_status,
                    return_handle="atm10_agent.response:compose",
                    reason=response_reason,
                ),
            ),
            allow_degraded=True,
            basis="active_response_result",
        ),
        "voice.asr": route(
            "voice.asr",
            (),
            requested=False,
            basis="no_audio_observation_in_turn_contract",
        ),
        "voice.tts": route(
            "voice.tts",
            voice_candidates,
            requested=voice_requested,
            basis="explicit_voice_request",
        ),
        "action.game_tool": route(
            "action.game_tool",
            action_candidates,
            requested=action_requested,
            basis="dry_run_tool_allowlist",
        ),
    }
    active_failures = [
        capability
        for capability, result in routes.items()
        if result["status"] in {"degraded", "unavailable", "rejected"}
    ]
    return {
        "schema_version": PROVIDER_ROUTE_BUNDLE_SCHEMA_VERSION,
        "status": "degraded" if active_failures else "ok",
        "degraded_capabilities": active_failures,
        "routes": routes,
        "global_router": False,
        "authority_ceiling": PROVIDER_ROUTE_AUTHORITY_CEILING,
        "claim_limit": (
            "The bundle records turn-local provider choices only; optional "
            "providers not requested by this turn were not probed."
        ),
    }
