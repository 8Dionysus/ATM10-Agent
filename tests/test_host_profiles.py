from __future__ import annotations

import pytest

from src.agent_core.host_profiles import (
    DEFAULT_HOST_PROFILE_ID,
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


def test_get_host_profile_rejects_unknown_profile() -> None:
    with pytest.raises(KeyError):
        get_host_profile("unknown_profile")
