"""Single composition root for the autonomous ATM10 companion."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from atm10_agent.action import plan
from atm10_agent.contracts import TURN_SCHEMA_VERSION, TurnRequest, TurnResult
from atm10_agent.interpretation import interpret
from atm10_agent.memory import EmbeddedMemoryStore, capture_turn_memory
from atm10_agent.perception import perceive
from atm10_agent.providers import build_turn_provider_routes
from atm10_agent.response import compose
from atm10_agent.trace import record_turn, write_json
from atm10_agent.voice import render
from atm10_agent.world import recall


def _iso_utc(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat()


def _turn_fingerprint(request: TurnRequest) -> str:
    seed = json.dumps(
        {
            "prompt": request.prompt,
            "query": request.query,
            "image_path": str(request.image_path) if request.image_path else None,
            "world_docs": str(request.world_docs) if request.world_docs else None,
            "topk": request.topk,
            "action_intent": request.action_intent,
            "voice": request.voice,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _create_run_dir(runs_dir: Path, now: datetime, fingerprint: str) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    base = f"{now.astimezone(timezone.utc):%Y%m%d_%H%M%S}-turn-{fingerprint[:8]}"
    candidate = runs_dir / base
    suffix = 1
    while candidate.exists():
        candidate = runs_dir / f"{base}-{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


class CompanionApp:
    """In-process composition root; adapters enrich this boundary, not replace it."""

    def __init__(
        self,
        *,
        runs_dir: Path,
        state_dir: Path,
        memory_dir: Path | None = None,
    ) -> None:
        self.runs_dir = runs_dir
        self.state_dir = state_dir
        self.memory_dir = memory_dir or state_dir.with_name(f"{state_dir.name}-memory")
        resolved_roots = (
            self.runs_dir.resolve(),
            self.state_dir.resolve(),
            self.memory_dir.resolve(),
        )
        for index, root in enumerate(resolved_roots):
            for other in resolved_roots[index + 1 :]:
                if root == other or root in other.parents or other in root.parents:
                    raise ValueError(
                        "runs_dir, state_dir, and memory_dir must be separate, "
                        "non-nested roots"
                    )

    def run(self, request: TurnRequest, *, now: datetime | None = None) -> dict[str, Any]:
        request.validate()
        observed_at = now or datetime.now(timezone.utc)
        fingerprint = _turn_fingerprint(request)
        run_dir = _create_run_dir(self.runs_dir, observed_at, fingerprint)
        turn_id = f"turn:{run_dir.name}"

        perception = perceive(
            image_path=request.image_path,
            prompt=request.prompt,
            run_dir=run_dir,
        )
        interpretation = interpret(
            perception=perception,
            query=request.query,
            action_intent=request.action_intent,
        )
        world = recall(
            query=interpretation["world_query"],
            topk=request.topk,
            world_docs=request.world_docs,
        )
        response = compose(perception=perception, world=world)
        action = plan(
            request.action_intent,
            intent_id=f"intent:{fingerprint}",
            trace_id=turn_id,
        )
        voice = render(requested=request.voice, text=response["answer"])
        providers = build_turn_provider_routes(
            turn_id=turn_id,
            perception=perception,
            world=world,
            response=response,
            action=action,
            voice=voice,
        )

        pre_memory_reasons = tuple(
            reason
            for reason in (
                world.get("degradation_reason"),
                action.get("degradation_reason"),
                voice.get("degradation_reason"),
            )
            if isinstance(reason, str) and reason
        )
        try:
            memory = capture_turn_memory(
                store=EmbeddedMemoryStore(self.memory_dir),
                turn_id=turn_id,
                timestamp_utc=_iso_utc(observed_at),
                query=request.query,
                turn_status="degraded" if pre_memory_reasons else "ok",
                world=world,
                response=response,
                action=action,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            memory = {
                "schema_version": "atm10_memory_capture_v1",
                "status": "degraded",
                "degraded": True,
                "degradation_reason": "memory_capture_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "authority_ceiling": "memory_not_proof_or_world_authority",
            }
        reasons = (
            *pre_memory_reasons,
            *(
                (str(memory["degradation_reason"]),)
                if memory.get("degradation_reason")
                else ()
            ),
        )
        result = TurnResult(
            turn_id=turn_id,
            timestamp_utc=_iso_utc(observed_at),
            status="degraded" if reasons else "ok",
            degraded=bool(reasons),
            degradation_reasons=reasons,
            stages={
                "perception": perception,
                "interpretation": interpretation,
                "world": world,
                "providers": providers,
                "memory": memory,
            },
            citations=tuple(world["citations"]),
            response=response,
            action=action,
            voice=voice,
        ).to_dict()
        trace_paths = record_turn(
            runs_dir=self.runs_dir,
            run_dir=run_dir,
            state_dir=self.state_dir,
            turn=result,
        )
        result["trace"] = trace_paths
        # Rewrite the turn artifact once so it carries its own trace pointers.
        write_json(Path(trace_paths["turn_json"]), result)
        return result

    def replay(
        self,
        turn_path: Path,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        source = json.loads(turn_path.read_text(encoding="utf-8"))
        if not isinstance(source, dict) or source.get("schema_version") != TURN_SCHEMA_VERSION:
            raise ValueError("replay source is not an atm10_companion_turn_v1 artifact")

        observed_at = now or datetime.now(timezone.utc)
        source_turn_id = str(source.get("turn_id", "")).strip()
        if not source_turn_id:
            raise ValueError("replay source is missing turn_id")
        replay_stages = deepcopy(source.get("stages", {}))
        if isinstance(replay_stages, dict) and isinstance(
            replay_stages.get("memory"),
            dict,
        ):
            replay_stages["memory"] = {
                **replay_stages["memory"],
                "replay_capture_performed": False,
                "replay_source_turn_id": source_turn_id,
            }
        if isinstance(replay_stages, dict) and isinstance(
            replay_stages.get("providers"),
            dict,
        ):
            replay_stages["providers"] = {
                **replay_stages["providers"],
                "replay_routing_performed": False,
                "replay_source_turn_id": source_turn_id,
            }
        replay_fingerprint = hashlib.sha256(
            f"{source_turn_id}:replay".encode("utf-8")
        ).hexdigest()[:16]
        run_dir = _create_run_dir(self.runs_dir, observed_at, replay_fingerprint)
        replay = {
            **source,
            "turn_id": f"turn:{run_dir.name}",
            "timestamp_utc": _iso_utc(observed_at),
            "stages": replay_stages,
            "replay_of": source_turn_id,
            "trace": {},
        }
        trace_paths = record_turn(
            runs_dir=self.runs_dir,
            run_dir=run_dir,
            state_dir=self.state_dir,
            turn=replay,
        )
        replay["trace"] = trace_paths
        write_json(Path(trace_paths["turn_json"]), replay)
        return replay


def run_companion_turn(
    request: TurnRequest,
    *,
    runs_dir: Path,
    state_dir: Path,
    memory_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    return CompanionApp(
        runs_dir=runs_dir,
        state_dir=state_dir,
        memory_dir=memory_dir,
    ).run(request, now=now)
