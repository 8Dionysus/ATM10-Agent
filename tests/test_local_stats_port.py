from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import scripts.cross_service_benchmark_suite as suite
from src.agent_core.service_sla import derive_cross_service_sla_pass_ratio


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKET_PATH = REPO_ROOT / "stats" / "packets" / "cross-service-sla-pass-ratio.reference.json"
EXPECTED_LANES = {
    "baseline_first": {"voice_asr", "voice_tts", "retrieval", "kag_file"},
    "combo_a": {"voice_asr", "voice_tts", "retrieval", "kag_neo4j"},
}


def _lane(*, status: str = "ok", sla_status: str = "pass") -> dict[str, str]:
    return {
        "schema_version": "service_sla_summary_v1",
        "status": status,
        "sla_status": sla_status,
    }


def _complete_suite(
    *,
    profile: str = "baseline_first",
    passing_lanes: set[str] | None = None,
) -> dict[str, object]:
    expected = EXPECTED_LANES[profile]
    passing = expected if passing_lanes is None else passing_lanes
    services = {
        lane_name: (
            _lane() if lane_name in passing else _lane(status="error", sla_status="breach")
        )
        for lane_name in expected
    }
    degraded = sorted(expected - passing)
    return {
        "schema_version": "cross_service_benchmark_suite_v1",
        "profile": profile,
        "status": "ok",
        "services": services,
        "overall_sla_status": "pass" if not degraded else "breach",
        "degraded_services": degraded,
    }


def test_reference_packet_matches_public_baseline_fixture_suite(tmp_path: Path) -> None:
    result = suite.run_cross_service_benchmark_suite(
        runs_dir=tmp_path / "runs",
        summary_json=tmp_path / "cross_service_benchmark_suite.json",
        now=datetime(2026, 7, 14, 2, 38, 31, tzinfo=timezone.utc),
        smoke_stub_voice_asr=True,
    )
    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    derived = result["summary_payload"]["stats"]["cross_service_sla_pass_ratio"]

    assert result["ok"] is True
    assert derived["status"] == "observed"
    assert packet["dimensions"]["profile"] == derived["profile"]
    assert packet["population"]["size"] == derived["denominator"]
    assert packet["sample"]["size"] == derived["denominator"]
    assert packet["value"]["numerator"] == derived["numerator"]
    assert packet["value"]["denominator"] == derived["denominator"]
    assert packet["value"]["number"] == derived["ratio"]


def test_partial_breach_and_complete_zero_remain_observations() -> None:
    partial = _complete_suite(passing_lanes={"voice_asr", "voice_tts", "kag_file"})
    zero = _complete_suite(passing_lanes=set())

    assert derive_cross_service_sla_pass_ratio(partial)["ratio"] == 0.75
    assert derive_cross_service_sla_pass_ratio(zero) == {
        "status": "observed",
        "reason": "complete",
        "profile": "baseline_first",
        "numerator": 0,
        "denominator": 4,
        "ratio": 0.0,
    }


def test_missing_or_extra_lane_and_error_suite_are_unknown() -> None:
    missing = _complete_suite()
    del missing["services"]["kag_file"]
    extra = _complete_suite()
    extra["services"]["suite_orchestration"] = _lane()
    errored = _complete_suite()
    errored["status"] = "error"

    assert derive_cross_service_sla_pass_ratio(missing)["reason"] == "incomplete_expected_population"
    assert derive_cross_service_sla_pass_ratio(extra)["reason"] == "incomplete_expected_population"
    assert derive_cross_service_sla_pass_ratio(errored) == {
        "status": "unknown",
        "reason": "incomplete_suite",
    }


def test_malformed_or_contradictory_suite_is_unknown() -> None:
    malformed = _complete_suite()
    malformed["services"]["voice_tts"]["sla_status"] = "maybe"
    contradictory_service = _complete_suite()
    contradictory_service["services"]["voice_tts"] = _lane(status="error", sla_status="pass")
    contradictory_overall = _complete_suite(passing_lanes={"voice_asr"})
    contradictory_overall["overall_sla_status"] = "pass"
    contradictory_degraded = deepcopy(_complete_suite(passing_lanes={"voice_asr"}))
    contradictory_degraded["degraded_services"] = []

    assert derive_cross_service_sla_pass_ratio(malformed)["reason"] == "malformed_service_summary"
    assert (
        derive_cross_service_sla_pass_ratio(contradictory_service)["reason"]
        == "inconsistent_service_summary"
    )
    assert (
        derive_cross_service_sla_pass_ratio(contradictory_overall)["reason"]
        == "inconsistent_overall_sla_status"
    )
    assert (
        derive_cross_service_sla_pass_ratio(contradictory_degraded)["reason"]
        == "inconsistent_degraded_services"
    )


def test_combo_a_uses_its_exact_profile_population() -> None:
    derived = derive_cross_service_sla_pass_ratio(_complete_suite(profile="combo_a"))

    assert derived == {
        "status": "observed",
        "reason": "complete",
        "profile": "combo_a",
        "numerator": 4,
        "denominator": 4,
        "ratio": 1.0,
    }
