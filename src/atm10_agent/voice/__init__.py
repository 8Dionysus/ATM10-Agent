"""Optional voice stage with an explicit no-provider baseline."""

from __future__ import annotations

from typing import Any


def render(*, requested: bool, text: str) -> dict[str, Any]:
    if not requested:
        return {
            "schema_version": "atm10_voice_result_v1",
            "status": "not_requested",
            "provider": None,
            "audio_written": False,
        }
    return {
        "schema_version": "atm10_voice_result_v1",
        "status": "degraded",
        "provider": None,
        "audio_written": False,
        "text": text,
        "degradation_reason": "voice_provider_not_configured",
    }
