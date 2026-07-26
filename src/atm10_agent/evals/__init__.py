"""Dependency-light executable evals for the autonomous ATM10 boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from atm10_agent.action import available_intents, plan
from atm10_agent.app import CompanionApp
from atm10_agent.contracts import TurnRequest
from atm10_agent.trace import write_json


EVAL_REPORT_SCHEMA_VERSION = "atm10_eval_report_v1"
COMPANION_CORE_SUITE_ID = "atm10-companion-core"


def _iso_utc(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat()


def _create_report_dir(reports_dir: Path, now: datetime) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    base = f"{now.astimezone(timezone.utc):%Y%m%d_%H%M%S}-companion-core"
    candidate = reports_dir / base
    suffix = 1
    while candidate.exists():
        candidate = reports_dir / f"{base}-{suffix:02d}"
        suffix += 1
    candidate.mkdir()
    return candidate


def _case(
    case_id: str,
    protects: tuple[str, ...],
    check: Callable[[], tuple[bool, dict[str, Any]]],
) -> dict[str, Any]:
    try:
        passed, observed = check()
        return {
            "id": case_id,
            "status": "pass" if passed else "fail",
            "protects": list(protects),
            "observed": observed,
        }
    except Exception as exc:
        return {
            "id": case_id,
            "status": "error",
            "protects": list(protects),
            "observed": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def run_companion_core_suite(
    *,
    runs_dir: Path,
    state_dir: Path,
    reports_dir: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run the core product contract without pytest, services, models, or network."""

    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    app = CompanionApp(runs_dir=runs_dir, state_dir=state_dir)
    shared: dict[str, Any] = {}

    def deterministic_turn() -> tuple[bool, dict[str, Any]]:
        turn = app.run(
            TurnRequest(
                prompt="Evaluate the autonomous ATM10 companion.",
                query="steel tools",
                action_intent="open_quest_book",
            ),
            now=observed_at,
        )
        shared["base_turn"] = turn
        passed = (
            turn["status"] == "ok"
            and turn["stages"]["perception"]["provider"] == "deterministic_stub_v1"
            and turn["action"]["executed"] is False
        )
        return passed, {
            "turn_id": turn["turn_id"],
            "provider": turn["stages"]["perception"]["provider"],
            "status": turn["status"],
        }

    def cited_world() -> tuple[bool, dict[str, Any]]:
        turn = shared["base_turn"]
        citations = turn["citations"]
        graph_results = turn["stages"]["world"]["product_kag"]
        passed = bool(citations) and bool(graph_results) and all(
            str(item.get("source", "")).strip() for item in citations
        )
        return passed, {
            "citation_count": len(citations),
            "product_kag_result_count": len(graph_results),
            "world_backend": turn["stages"]["world"]["backend"],
        }

    def dry_run_actions() -> tuple[bool, dict[str, Any]]:
        observed: dict[str, Any] = {}
        passed = True
        for intent in available_intents():
            result = plan(
                intent,
                intent_id=f"eval-intent:{intent}",
                trace_id=f"eval-trace:{intent}",
            )
            execution = result["execution"]
            plan_ok = (
                result["dry_run"] is True
                and result["executed"] is False
                and execution["dry_run"] is True
                and execution["executed"] is False
                and execution["step_count"] >= len(result["actions"])
                and result["normalized_plan"]["planning"]["intent_id"]
                == f"eval-intent:{intent}"
                and result["normalized_plan"]["planning"]["trace_id"]
                == f"eval-trace:{intent}"
            )
            passed = passed and plan_ok
            observed[intent] = {
                "status": result["status"],
                "action_count": len(result["actions"]),
                "step_count": execution["step_count"],
                "dry_run": result["dry_run"],
                "executed": result["executed"],
            }
        return passed, observed

    def optional_voice() -> tuple[bool, dict[str, Any]]:
        turn = app.run(
            TurnRequest(
                prompt="Evaluate optional ATM10 voice.",
                query="starter tools",
                voice=True,
            ),
            now=observed_at,
        )
        voice = turn["voice"]
        passed = (
            turn["status"] == "degraded"
            and voice["status"] == "degraded"
            and voice["audio_written"] is False
            and voice["degradation_reason"] == "voice_provider_not_configured"
        )
        return passed, {
            "turn_id": turn["turn_id"],
            "turn_status": turn["status"],
            "voice_status": voice["status"],
            "audio_written": voice["audio_written"],
        }

    def state_trace_separation() -> tuple[bool, dict[str, Any]]:
        turn = shared["base_turn"]
        trace = turn["trace"]
        append_only = Path(trace["append_only_trace"])
        mutable = Path(trace["mutable_state"])
        passed = (
            append_only.is_file()
            and mutable.is_file()
            and append_only.parent.resolve() != mutable.parent.resolve()
            and append_only.parent.resolve() == runs_dir.resolve()
            and mutable.parent.resolve() == state_dir.resolve()
        )
        return passed, {
            "append_only_trace_exists": append_only.is_file(),
            "mutable_state_exists": mutable.is_file(),
            "separate_roots": append_only.parent.resolve() != mutable.parent.resolve(),
        }

    def useful_negatives() -> tuple[bool, dict[str, Any]]:
        unsupported = app.run(
            TurnRequest(
                prompt="Evaluate unsupported ATM10 action.",
                query="steel",
                action_intent="destroy_world",
            ),
            now=observed_at,
        )
        no_match = app.run(
            TurnRequest(
                prompt="Evaluate absent ATM10 evidence.",
                query="xylophonic_unfindable_zz",
            ),
            now=observed_at,
        )
        passed = (
            unsupported["status"] == "degraded"
            and unsupported["action"]["executed"] is False
            and unsupported["action"]["degradation_reason"] == "unsupported_action_intent"
            and no_match["status"] == "degraded"
            and no_match["stages"]["world"]["degradation_reason"] == "no_retrieval_match"
            and not no_match["citations"]
        )
        shared["negative_turn"] = unsupported
        return passed, {
            "unsupported_action_status": unsupported["action"]["status"],
            "unsupported_action_executed": unsupported["action"]["executed"],
            "no_match_world_status": no_match["stages"]["world"]["status"],
            "no_match_citation_count": len(no_match["citations"]),
        }

    def replay() -> tuple[bool, dict[str, Any]]:
        original = shared["base_turn"]
        replayed = app.replay(Path(original["trace"]["turn_json"]), now=observed_at)
        passed = (
            replayed["replay_of"] == original["turn_id"]
            and replayed["turn_id"] != original["turn_id"]
            and replayed["response"] == original["response"]
            and replayed["citations"] == original["citations"]
        )
        return passed, {
            "source_turn_id": original["turn_id"],
            "replay_turn_id": replayed["turn_id"],
            "response_preserved": replayed["response"] == original["response"],
            "citations_preserved": replayed["citations"] == original["citations"],
        }

    cases = [
        _case("deterministic-stub-turn", ("PB-001",), deterministic_turn),
        _case("cited-file-world", ("PB-002", "PB-003"), cited_world),
        _case("dry-run-action-fence", ("PB-005",), dry_run_actions),
        _case("optional-provider-honesty", ("PB-007",), optional_voice),
        _case("state-trace-separation", ("PB-008",), state_trace_separation),
        _case("useful-negative-cases", ("PB-012",), useful_negatives),
        _case("provider-free-replay", ("PB-012",), replay),
    ]
    passed_count = sum(case["status"] == "pass" for case in cases)
    report_dir = _create_report_dir(reports_dir, observed_at)
    report_path = report_dir / "atm10_eval_report.json"
    report = {
        "schema_version": EVAL_REPORT_SCHEMA_VERSION,
        "suite_id": COMPANION_CORE_SUITE_ID,
        "status": "pass" if passed_count == len(cases) else "fail",
        "observed_at_utc": _iso_utc(observed_at),
        "case_count": len(cases),
        "passed_count": passed_count,
        "failed_count": len(cases) - passed_count,
        "network_required": False,
        "live_services_required": False,
        "real_input_emitted": False,
        "storage": {
            "runs_root": str(runs_dir),
            "state_root": str(state_dir),
            "reports_root": str(reports_dir),
        },
        "cases": cases,
        "report_path": str(report_path),
    }
    write_json(report_path, report)
    return report


def run_suite(
    suite_id: str,
    *,
    runs_dir: Path,
    state_dir: Path,
    reports_dir: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized = suite_id.strip().lower()
    if normalized in {"companion-core", COMPANION_CORE_SUITE_ID}:
        return run_companion_core_suite(
            runs_dir=runs_dir,
            state_dir=state_dir,
            reports_dir=reports_dir,
            now=now,
        )
    raise ValueError(f"Unsupported eval suite: {suite_id!r}.")
