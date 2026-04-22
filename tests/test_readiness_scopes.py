from __future__ import annotations

from src.agent_core.host_profiles import FEDORA_LOCAL_DEV_PROFILE_ID
from src.agent_core.readiness_scopes import (
    DEV_COMPANION_SCOPE,
    PRODUCT_EDGE_SCOPE,
    evaluate_host_profile_session_readiness,
    evaluate_session_probe_readiness,
    list_readiness_scopes,
    normalize_readiness_scope,
)


def _probe(**overrides):
    payload = {
        "schema_version": "atm10_session_probe_v1",
        "status": "ok",
        "window_found": True,
        "process_name": "javaw.exe",
        "window_title": "Minecraft - ATM10",
        "foreground": True,
        "capture_target_kind": "region",
        "capture_bbox": [0, 0, 1920, 1080],
        "capture_intersects_window": True,
        "atm10_probable": True,
        "reason_codes": [],
    }
    payload.update(overrides)
    return payload


def test_readiness_scope_registry_is_explicit() -> None:
    assert list_readiness_scopes() == (PRODUCT_EDGE_SCOPE, DEV_COMPANION_SCOPE)
    assert normalize_readiness_scope(None) == PRODUCT_EDGE_SCOPE
    assert normalize_readiness_scope("dev_companion") == DEV_COMPANION_SCOPE
    try:
        normalize_readiness_scope("paper_parity")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown readiness scope was accepted")


def test_product_edge_requires_atm10_window_identity_and_focus() -> None:
    evaluation = evaluate_session_probe_readiness(
        readiness_scope=PRODUCT_EDGE_SCOPE,
        session_probe=_probe(),
    )

    assert evaluation["status"] == "ok"
    assert evaluation["blocking_reason_codes"] == []
    assert set(evaluation["satisfied_checks"]) == set(evaluation["required_checks"])


def test_product_edge_blocks_linux_manual_companion_probe() -> None:
    evaluation = evaluate_session_probe_readiness(
        readiness_scope=PRODUCT_EDGE_SCOPE,
        session_probe=_probe(
            status="attention",
            window_found=False,
            process_name=None,
            window_title=None,
            foreground=False,
            capture_intersects_window=None,
            atm10_probable=False,
            reason_codes=["window_identity_unavailable", "manual_capture_source_required"],
        ),
    )

    assert evaluation["status"] == "attention"
    assert "atm10_window_not_found" in evaluation["blocking_reason_codes"]
    assert "atm10_not_probable" in evaluation["blocking_reason_codes"]
    assert "atm10_window_not_foreground" in evaluation["blocking_reason_codes"]
    assert "confirm_manual_capture_source" in evaluation["recommended_actions"]


def test_dev_companion_accepts_manual_region_capture_without_window_identity() -> None:
    evaluation = evaluate_session_probe_readiness(
        readiness_scope=DEV_COMPANION_SCOPE,
        session_probe=_probe(
            status="attention",
            window_found=False,
            process_name=None,
            window_title=None,
            foreground=False,
            capture_intersects_window=None,
            atm10_probable=False,
            reason_codes=["window_identity_unavailable", "manual_capture_source_required"],
        ),
    )

    assert evaluation["status"] == "ok"
    assert evaluation["blocking_reason_codes"] == []
    assert evaluation["warning_reason_codes"] == ["window_identity_unavailable", "manual_capture_source_required"]
    assert "capture_target_configured" in evaluation["satisfied_checks"]


def test_dev_companion_still_requires_configured_capture_target() -> None:
    evaluation = evaluate_session_probe_readiness(
        readiness_scope=DEV_COMPANION_SCOPE,
        session_probe=_probe(
            status="attention",
            capture_target_kind="unknown",
            capture_bbox=None,
            reason_codes=["window_identity_unavailable", "manual_capture_source_required"],
        ),
    )

    assert evaluation["status"] == "attention"
    assert evaluation["blocking_reason_codes"] == ["capture_target_unconfigured"]
    assert "configure_capture_region_or_monitor" in evaluation["recommended_actions"]


def test_dev_companion_escalates_platform_not_supported_probe() -> None:
    evaluation = evaluate_session_probe_readiness(
        readiness_scope=DEV_COMPANION_SCOPE,
        session_probe=_probe(
            status="error",
            capture_target_kind="monitor",
            capture_bbox=None,
            reason_codes=["platform_not_supported"],
        ),
    )

    assert evaluation["status"] == "error"
    assert "session_probe_error" in evaluation["blocking_reason_codes"]
    assert "platform_not_supported" in evaluation["blocking_reason_codes"]


def test_host_profile_readiness_uses_fedora_dev_companion_scope() -> None:
    evaluation = evaluate_host_profile_session_readiness(
        host_profile=FEDORA_LOCAL_DEV_PROFILE_ID,
        session_probe=_probe(
            status="attention",
            window_found=False,
            foreground=False,
            capture_intersects_window=None,
            atm10_probable=False,
            reason_codes=["window_identity_unavailable", "manual_capture_source_required"],
        ),
    )

    assert evaluation["host_profile_id"] == FEDORA_LOCAL_DEV_PROFILE_ID
    assert evaluation["host_profile_validation_status"] == "preliminary"
    assert evaluation["readiness_scope"] == DEV_COMPANION_SCOPE
    assert evaluation["status"] == "ok"
    assert evaluation["host_profile_capabilities"]["supports_window_session_probe"] is False
