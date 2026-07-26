from __future__ import annotations

from atm10_agent.agent_core.service_sla import build_common_metrics, build_service_sla_summary


def test_build_common_metrics_aggregates_latency_and_error_rate() -> None:
    metrics = build_common_metrics(
        sample_count=4,
        success_count=3,
        latency_values_ms=[100.0, 200.0, 400.0],
    )

    assert metrics["sample_count"] == 4
    assert metrics["success_count"] == 3
    assert metrics["error_count"] == 1
    assert metrics["error_rate"] == 0.25
    assert metrics["latency_p50_ms"] == 200.0
    assert metrics["latency_p95_ms"] == 400.0


def test_build_service_sla_summary_defaults_to_breach_when_status_is_error() -> None:
    payload = build_service_sla_summary(
        service_name="retrieval",
        surface="eval",
        backend="in_memory",
        profile="local_eval",
        policy="signal_only",
        status="error",
        metrics=build_common_metrics(sample_count=0, success_count=0, error_count=1, latency_values_ms=[]),
        quality={},
        breaches=["eval_error: boom"],
        paths={"service_sla_summary_json": "runs/x/service_sla_summary.json"},
    )

    assert payload["schema_version"] == "service_sla_summary_v1"
    assert payload["sla_status"] == "breach"
    assert payload["paths"]["service_sla_summary_json"].endswith("service_sla_summary.json")
