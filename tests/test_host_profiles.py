from __future__ import annotations

import pytest

from src.agent_core.host_profiles import (
    DEFAULT_HOST_PROFILE_ID,
    FEDORA_LOCAL_DEV_PROFILE_ID,
    get_host_profile,
    host_profile_payload,
    list_host_profile_ids,
)


def test_default_host_profile_is_openvino_intel_local() -> None:
    profile = get_host_profile()
    payload = host_profile_payload()

    assert profile.profile_id == DEFAULT_HOST_PROFILE_ID
    assert profile.runtime_family == "openvino_first"
    assert "ov_intel_core_ultra_local" in list_host_profile_ids()
    assert payload["id"] == DEFAULT_HOST_PROFILE_ID
    assert payload["defaults"]["pilot_vlm_device"] == "GPU"
    assert payload["defaults"]["pilot_text_device"] == "GPU"
    assert payload["defaults"]["pilot_vlm_provider"] == "openvino"
    assert payload["defaults"]["pilot_text_provider"] == "openvino"
    assert payload["preferred_capture_backend"] == "dxcam_dxgi"
    assert payload["host"]["os_family"] == "windows"
    assert payload["host"]["readiness_scope"] == "product_edge"
    assert payload["host"]["window_identity_mode"] == "win32_atm10_window"
    assert payload["capabilities"]["supports_window_session_probe"] is True
    assert payload["capabilities"]["supports_supervised_input"] is False


def test_fedora_local_dev_profile_is_additive_preliminary_companion_path() -> None:
    profile = get_host_profile(FEDORA_LOCAL_DEV_PROFILE_ID)
    payload = host_profile_payload(FEDORA_LOCAL_DEV_PROFILE_ID)

    assert FEDORA_LOCAL_DEV_PROFILE_ID in list_host_profile_ids()
    assert profile.validation_status == "preliminary"
    assert profile.runtime_family == "openvino_first"
    assert payload["id"] == FEDORA_LOCAL_DEV_PROFILE_ID
    assert payload["preferred_capture_backend"] == "mss_region"
    assert payload["host"]["os_family"] == "linux"
    assert payload["host"]["readiness_scope"] == "dev_companion"
    assert payload["host"]["window_identity_mode"] == "manual_or_unavailable"
    assert payload["host"]["capture_source_mode"] == "manual_region_or_monitor"
    assert payload["capabilities"]["supports_window_session_probe"] is False
    assert payload["capabilities"]["supports_supervised_input"] is False
    assert payload["defaults"]["pilot_input_device_index"] is None
    assert payload["defaults"]["pilot_vlm_device"] == "AUTO"
    assert payload["defaults"]["pilot_text_device"] == "AUTO"


def test_get_host_profile_rejects_unknown_profile() -> None:
    with pytest.raises(KeyError):
        get_host_profile("unknown_profile")
