from __future__ import annotations

from pathlib import Path
from typing import Any


PROFILE_SOURCE_SPECS: dict[str, list[dict[str, Any]]] = {
    "ci_smoke": [
        {
            "source_key": "phase_a",
            "path_parts": ("ci-smoke-phase-a", "smoke_summary.json"),
            "expected_schema_version": None,
            "required_fields": ("status", "observed", "violations"),
        },
        {
            "source_key": "retrieve",
            "path_parts": ("ci-smoke-retrieve", "smoke_summary.json"),
            "expected_schema_version": None,
            "required_fields": ("status", "observed", "violations"),
        },
        {
            "source_key": "eval",
            "path_parts": ("ci-smoke-eval", "smoke_summary.json"),
            "expected_schema_version": None,
            "required_fields": ("status", "observed", "violations"),
        },
        {
            "source_key": "gateway_core",
            "path_parts": ("ci-smoke-gateway-core", "gateway_smoke_summary.json"),
            "expected_schema_version": None,
            "required_fields": ("status", "request_count", "failed_requests_count", "requests"),
        },
        {
            "source_key": "gateway_automation",
            "path_parts": ("ci-smoke-gateway-automation", "gateway_smoke_summary.json"),
            "expected_schema_version": None,
            "required_fields": ("status", "request_count", "failed_requests_count", "requests"),
        },
        {
            "source_key": "gateway_http_core",
            "path_parts": ("ci-smoke-gateway-http-core", "gateway_http_smoke_summary.json"),
            "expected_schema_version": None,
            "required_fields": ("status", "request_count", "failed_requests_count", "requests"),
        },
        {
            "source_key": "gateway_http_automation",
            "path_parts": ("ci-smoke-gateway-http-automation", "gateway_http_smoke_summary.json"),
            "expected_schema_version": None,
            "required_fields": ("status", "request_count", "failed_requests_count", "requests"),
        },
        {
            "source_key": "gateway_sla",
            "path_parts": ("ci-smoke-gateway-sla", "gateway_sla_summary.json"),
            "expected_schema_version": "gateway_sla_summary_v1",
            "required_fields": ("schema_version", "status", "sla_status", "metrics", "exit_code"),
        },
        {
            "source_key": "streamlit",
            "path_parts": ("ci-smoke-streamlit", "streamlit_smoke_summary.json"),
            "expected_schema_version": "streamlit_smoke_summary_v1",
            "required_fields": (
                "schema_version",
                "status",
                "startup_ok",
                "tabs_detected",
                "required_missing_sources",
                "optional_missing_sources",
                "exit_code",
            ),
        },
    ],
    "nightly_readiness": [
        {
            "source_key": "nightly_http_core",
            "path_parts": ("nightly-gateway-http-core", "gateway_http_smoke_summary.json"),
            "expected_schema_version": None,
            "required_fields": ("status", "request_count", "failed_requests_count", "requests"),
        },
        {
            "source_key": "nightly_sla",
            "path_parts": ("nightly-gateway-sla-history", "gateway_sla_summary.json"),
            "expected_schema_version": "gateway_sla_summary_v1",
            "required_fields": ("schema_version", "status", "sla_status", "metrics", "exit_code"),
        },
        {
            "source_key": "readiness",
            "path_parts": ("nightly-gateway-sla-readiness", "readiness_summary.json"),
            "expected_schema_version": "gateway_sla_fail_nightly_readiness_v1",
            "required_fields": (
                "schema_version",
                "status",
                "readiness_status",
                "criteria",
                "window_summary",
                "recommendation",
                "exit_code",
            ),
        },
        {
            "source_key": "governance",
            "path_parts": ("nightly-gateway-sla-governance", "governance_summary.json"),
            "expected_schema_version": "gateway_sla_fail_nightly_governance_v1",
            "required_fields": (
                "schema_version",
                "status",
                "decision_status",
                "criteria",
                "observed",
                "recommendation",
                "exit_code",
            ),
        },
        {
            "source_key": "progress",
            "path_parts": ("nightly-gateway-sla-progress", "progress_summary.json"),
            "expected_schema_version": "gateway_sla_fail_nightly_progress_v1",
            "required_fields": (
                "schema_version",
                "status",
                "decision_status",
                "criteria",
                "observed",
                "recommendation",
                "exit_code",
            ),
        },
        {
            "source_key": "transition",
            "path_parts": ("nightly-gateway-sla-transition", "transition_summary.json"),
            "expected_schema_version": "gateway_sla_fail_nightly_transition_v1",
            "required_fields": (
                "schema_version",
                "status",
                "decision_status",
                "allow_switch",
                "criteria",
                "observed",
                "recommendation",
                "exit_code",
            ),
        },
    ],
}


def resolve_profile_sources(profile: str, runs_dir: Path) -> list[dict[str, Any]]:
    if profile not in PROFILE_SOURCE_SPECS:
        available = ", ".join(sorted(PROFILE_SOURCE_SPECS.keys()))
        raise ValueError(f"Unsupported profile: {profile!r}. Expected one of: {available}")
    sources: list[dict[str, Any]] = []
    for spec in PROFILE_SOURCE_SPECS[profile]:
        source = dict(spec)
        source["path"] = str(Path(runs_dir).joinpath(*tuple(spec["path_parts"])))
        sources.append(source)
    return sources
