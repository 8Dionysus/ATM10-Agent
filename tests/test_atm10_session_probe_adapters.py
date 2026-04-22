from __future__ import annotations

from datetime import datetime, timezone

import pytest

import src.agent_core.atm10_session_probe as session_probe

_FIXED_NOW = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)


def test_backend_selection_is_platform_aware() -> None:
    assert session_probe.list_session_probe_backend_ids() == (
        "windows_win32",
        "linux_manual",
        "unsupported",
    )
    assert session_probe.select_session_probe_backend_id(platform_name="win32") == "windows_win32"
    assert session_probe.select_session_probe_backend_id(platform_name="linux") == "linux_manual"
    assert session_probe.select_session_probe_backend_id(platform_name="linux2") == "linux_manual"
    assert session_probe.select_session_probe_backend_id(platform_name="darwin") == "unsupported"


def test_backend_selection_rejects_unknown_explicit_backend() -> None:
    with pytest.raises(KeyError):
        session_probe.select_session_probe_backend_id(backend_name="portal_dragon")


def test_linux_manual_backend_is_attention_not_platform_error() -> None:
    payload = session_probe.probe_atm10_session(
        capture_target_kind="region",
        capture_bbox=[10, 20, 110, 220],
        now=_FIXED_NOW,
        platform_name="linux",
    )

    assert payload["schema_version"] == "atm10_session_probe_v1"
    assert payload["checked_at_utc"] == "2026-04-21T12:00:00+00:00"
    assert payload["status"] == "attention"
    assert payload["window_found"] is False
    assert payload["foreground"] is False
    assert payload["capture_target_kind"] == "region"
    assert payload["capture_bbox"] == [10, 20, 110, 220]
    assert payload["capture_intersects_window"] is None
    assert payload["atm10_probable"] is False
    assert "window_identity_unavailable" in payload["reason_codes"]
    assert "manual_capture_source_required" in payload["reason_codes"]
    assert "platform_not_supported" not in payload["reason_codes"]


def test_unsupported_backend_preserves_platform_not_supported_error() -> None:
    payload = session_probe.probe_atm10_session(
        capture_target_kind="monitor",
        capture_bbox=None,
        now=_FIXED_NOW,
        platform_name="darwin",
    )

    assert payload["status"] == "error"
    assert payload["window_found"] is False
    assert payload["capture_target_kind"] == "monitor"
    assert payload["reason_codes"] == ["platform_not_supported"]


def test_windows_backend_no_window_contract_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session_probe,
        "find_best_atm10_window",
        lambda *, platform_name=None: None,
    )

    payload = session_probe.probe_atm10_session(
        capture_target_kind="monitor",
        capture_bbox=None,
        now=_FIXED_NOW,
        platform_name="win32",
    )

    assert payload["status"] == "attention"
    assert payload["window_found"] is False
    assert payload["atm10_probable"] is False
    assert payload["reason_codes"] == ["atm10_window_not_found"]
