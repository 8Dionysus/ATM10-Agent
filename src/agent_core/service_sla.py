from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

SERVICE_SLA_SCHEMA = "service_sla_summary_v1"
CROSS_SERVICE_BENCHMARK_SUITE_SCHEMA = "cross_service_benchmark_suite_v1"
_PRIMARY_QUALITY_KEYS: dict[str, tuple[str, ...]] = {
    "voice_asr": ("text_similarity_avg",),
    "voice_tts": ("non_empty_audio_rate", "cache_hit_rate", "chunk_count_mean"),
    "retrieval": ("mean_mrr_at_k", "mean_recall_at_k", "hit_rate_at_k"),
    "kag": ("mean_mrr_at_k", "mean_recall_at_k", "hit_rate_at_k"),
    "kag_file": ("mean_mrr_at_k", "mean_recall_at_k", "hit_rate_at_k"),
    "kag_neo4j": ("mean_mrr_at_k", "mean_recall_at_k", "hit_rate_at_k"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile_nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    normalized = [float(value) for value in values]
    if not normalized:
        return None
    sorted_values = sorted(normalized)
    if percentile <= 0:
        return sorted_values[0]
    if percentile >= 100:
        return sorted_values[-1]
    rank = math.ceil((percentile / 100.0) * len(sorted_values))
    index = min(max(rank - 1, 0), len(sorted_values) - 1)
    return sorted_values[index]


def build_common_metrics(
    *,
    sample_count: int,
    success_count: int,
    error_count: int | None = None,
    latency_values_ms: Sequence[float] | None = None,
) -> dict[str, Any]:
    normalized_sample_count = max(int(sample_count), 0)
    normalized_success_count = max(int(success_count), 0)
    normalized_error_count = (
        max(int(error_count), 0)
        if error_count is not None
        else max(normalized_sample_count - normalized_success_count, 0)
    )
    latencies_ms = [float(value) for value in (latency_values_ms or [])]
    error_rate = (
        float(normalized_error_count) / float(normalized_sample_count)
        if normalized_sample_count > 0
        else 0.0
    )
    latency_mean_ms = (sum(latencies_ms) / len(latencies_ms)) if latencies_ms else None
    return {
        "sample_count": normalized_sample_count,
        "success_count": normalized_success_count,
        "error_count": normalized_error_count,
        "error_rate": error_rate,
        "latency_mean_ms": latency_mean_ms,
        "latency_p50_ms": percentile_nearest_rank(latencies_ms, 50.0),
        "latency_p95_ms": percentile_nearest_rank(latencies_ms, 95.0),
        "latency_max_ms": max(latencies_ms) if latencies_ms else None,
    }


def build_service_sla_summary(
    *,
    service_name: str,
    surface: str,
    backend: str,
    profile: str,
    policy: str,
    status: str,
    metrics: Mapping[str, Any],
    quality: Mapping[str, Any] | None = None,
    thresholds: Mapping[str, Any] | None = None,
    warnings: Sequence[str] | None = None,
    breaches: Sequence[str] | None = None,
    paths: Mapping[str, Any] | None = None,
    checked_at_utc: str | None = None,
) -> dict[str, Any]:
    warning_items = [str(item) for item in (warnings or []) if str(item).strip()]
    breach_items = [str(item) for item in (breaches or []) if str(item).strip()]
    normalized_status = str(status).strip() or "unknown"
    normalized_policy = str(policy).strip() or "signal_only"
    normalized_service_name = str(service_name).strip()
    normalized_surface = str(surface).strip()
    normalized_backend = str(backend).strip()
    normalized_profile = str(profile).strip()

    normalized_paths: dict[str, Any] = {}
    for key, value in (paths or {}).items():
        normalized_paths[str(key)] = None if value is None else str(value)

    sla_status = "pass"
    if normalized_status != "ok" or breach_items:
        sla_status = "breach"

    return {
        "schema_version": SERVICE_SLA_SCHEMA,
        "service_name": normalized_service_name,
        "surface": normalized_surface,
        "backend": normalized_backend,
        "profile": normalized_profile,
        "policy": normalized_policy,
        "checked_at_utc": checked_at_utc or utc_now(),
        "status": normalized_status,
        "sla_status": sla_status,
        "metrics": dict(metrics),
        "quality": dict(quality or {}),
        "thresholds": dict(thresholds or {}),
        "breaches": breach_items,
        "warnings": warning_items,
        "paths": normalized_paths,
    }


def primary_quality_metric(
    service_name: str,
    quality: Mapping[str, Any] | None,
) -> tuple[str | None, Any]:
    normalized_service_name = str(service_name).strip()
    normalized_quality = quality if isinstance(quality, Mapping) else {}
    for candidate_key in _PRIMARY_QUALITY_KEYS.get(normalized_service_name, ()):
        if candidate_key in normalized_quality:
            return candidate_key, normalized_quality.get(candidate_key)
    for key, value in normalized_quality.items():
        return str(key), value
    return None, None


def build_suite_summary_row(
    *,
    source: str,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = summary.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    quality = summary.get("quality")
    quality = quality if isinstance(quality, Mapping) else {}
    primary_quality_name, primary_quality_value = primary_quality_metric(
        str(summary.get("service_name", "")),
        quality,
    )
    return {
        "source": str(source),
        "service_name": str(summary.get("service_name", "")),
        "surface": str(summary.get("surface", "")),
        "backend": str(summary.get("backend", "")),
        "profile": str(summary.get("profile", "")),
        "status": str(summary.get("status", "unknown")),
        "sla_status": str(summary.get("sla_status", "unknown")),
        "sample_count": metrics.get("sample_count"),
        "success_count": metrics.get("success_count"),
        "error_count": metrics.get("error_count"),
        "latency_p95_ms": metrics.get("latency_p95_ms"),
        "quality_primary_name": primary_quality_name,
        "quality_primary_value": primary_quality_value,
        "summary_json": _extract_summary_json_path(summary),
    }


def degraded_services(services: Mapping[str, Mapping[str, Any]]) -> list[str]:
    degraded: list[str] = []
    for source, summary in services.items():
        if not isinstance(summary, Mapping):
            degraded.append(str(source))
            continue
        if str(summary.get("status", "unknown")) != "ok" or str(summary.get("sla_status", "unknown")) != "pass":
            degraded.append(str(source))
    return sorted(degraded)


def _extract_summary_json_path(summary: Mapping[str, Any]) -> str | None:
    paths = summary.get("paths")
    if not isinstance(paths, Mapping):
        return None
    summary_json = paths.get("service_sla_summary_json")
    if summary_json is None:
        return None
    return str(summary_json)
