from __future__ import annotations

from src.agent_core.service_sla import build_common_metrics, build_service_sla_summary, build_suite_summary_row, degraded_services


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
        profile="baseline_first",
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


def test_build_suite_summary_row_and_degraded_services() -> None:
    ok_summary = build_service_sla_summary(
        service_name="voice_asr",
        surface="benchmark",
        backend="whisper_genai",
        profile="baseline_first",
        policy="signal_only",
        status="ok",
        metrics=build_common_metrics(sample_count=2, success_count=2, latency_values_ms=[10.0, 15.0]),
        quality={"text_similarity_avg": 1.0},
        paths={"service_sla_summary_json": "runs/voice_asr/service_sla_summary.json"},
    )
    error_summary = build_service_sla_summary(
        service_name="kag_file",
        surface="eval",
        backend="file",
        profile="baseline_first",
        policy="signal_only",
        status="error",
        metrics=build_common_metrics(sample_count=2, success_count=1, latency_values_ms=[5.0]),
        quality={"mean_mrr_at_k": 0.5},
        breaches=["sample_errors_present"],
        paths={"service_sla_summary_json": "runs/kag_file/service_sla_summary.json"},
    )

    row = build_suite_summary_row(source="voice_asr", summary=ok_summary)
    assert row["source"] == "voice_asr"
    assert row["quality_primary_name"] == "text_similarity_avg"
    assert row["summary_json"].endswith("service_sla_summary.json")

    degraded = degraded_services({"voice_asr": ok_summary, "kag_file": error_summary})
    assert degraded == ["kag_file"]
