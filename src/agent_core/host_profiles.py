from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_HOST_PROFILE_ID = "ov_intel_core_ultra_local"


@dataclass(frozen=True)
class HostProfile:
    profile_id: str
    display_name: str
    runtime_family: str
    validation_status: str
    description: str
    pilot_vlm_model_dir: Path
    pilot_text_model_dir: Path
    pilot_vlm_device: str
    pilot_text_device: str
    pilot_vlm_provider: str
    pilot_text_provider: str
    voice_asr_language: str
    voice_asr_max_new_tokens: int
    voice_asr_warmup_request: bool
    voice_asr_warmup_language: str
    pilot_input_device_index: int | None
    pilot_vlm_max_new_tokens: int
    pilot_text_max_new_tokens: int
    pilot_hybrid_timeout_sec: float
    pilot_gateway_topk: int
    pilot_gateway_candidate_k: int
    pilot_max_entities_per_doc: int
    preferred_capture_backend: str = "dxcam_dxgi"
    notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.profile_id,
            "display_name": self.display_name,
            "runtime_family": self.runtime_family,
            "validation_status": self.validation_status,
            "description": self.description,
            "preferred_capture_backend": self.preferred_capture_backend,
            "defaults": {
                "voice_asr_language": self.voice_asr_language,
                "voice_asr_max_new_tokens": int(self.voice_asr_max_new_tokens),
                "voice_asr_warmup_request": bool(self.voice_asr_warmup_request),
                "voice_asr_warmup_language": self.voice_asr_warmup_language,
                "pilot_input_device_index": self.pilot_input_device_index,
                "pilot_vlm_model_dir": str(self.pilot_vlm_model_dir),
                "pilot_text_model_dir": str(self.pilot_text_model_dir),
                "pilot_vlm_device": self.pilot_vlm_device,
                "pilot_text_device": self.pilot_text_device,
                "pilot_vlm_provider": self.pilot_vlm_provider,
                "pilot_text_provider": self.pilot_text_provider,
                "pilot_vlm_max_new_tokens": int(self.pilot_vlm_max_new_tokens),
                "pilot_text_max_new_tokens": int(self.pilot_text_max_new_tokens),
                "pilot_hybrid_timeout_sec": float(self.pilot_hybrid_timeout_sec),
                "pilot_gateway_topk": int(self.pilot_gateway_topk),
                "pilot_gateway_candidate_k": int(self.pilot_gateway_candidate_k),
                "pilot_max_entities_per_doc": int(self.pilot_max_entities_per_doc),
            },
            "notes": list(self.notes),
        }


_HOST_PROFILES: dict[str, HostProfile] = {
    DEFAULT_HOST_PROFILE_ID: HostProfile(
        profile_id=DEFAULT_HOST_PROFILE_ID,
        display_name="Intel Core Ultra OpenVINO Local",
        runtime_family="openvino_first",
        validation_status="validated",
        description=(
            "Validated repo-host baseline for the local Intel Core Ultra machine with "
            "explicit OpenVINO placement across CPU/GPU/NPU."
        ),
        pilot_vlm_model_dir=Path("models") / "qwen2.5-vl-7b-instruct-int4-ov",
        pilot_text_model_dir=Path("models") / "qwen3-8b-int4-cw-ov",
        pilot_vlm_device="GPU",
        pilot_text_device="GPU",
        pilot_vlm_provider="openvino",
        pilot_text_provider="openvino",
        voice_asr_language="ru",
        voice_asr_max_new_tokens=64,
        voice_asr_warmup_request=True,
        voice_asr_warmup_language="ru",
        pilot_input_device_index=1,
        pilot_vlm_max_new_tokens=64,
        pilot_text_max_new_tokens=64,
        pilot_hybrid_timeout_sec=1.0,
        pilot_gateway_topk=3,
        pilot_gateway_candidate_k=6,
        pilot_max_entities_per_doc=32,
        preferred_capture_backend="dxcam_dxgi",
        notes=(
            "Keep OpenVINO as the canonical repo-host runtime baseline until another host profile is explicitly promoted.",
            "Future NVIDIA or Ollama paths should land as additive machine-specific profiles with their own eval posture.",
        ),
    )
}


SUPPORTED_HOST_PROFILE_IDS: tuple[str, ...] = tuple(_HOST_PROFILES.keys())


def list_host_profile_ids() -> tuple[str, ...]:
    return SUPPORTED_HOST_PROFILE_IDS


def get_host_profile(profile_id: str | None = None) -> HostProfile:
    resolved_id = str(profile_id or DEFAULT_HOST_PROFILE_ID).strip() or DEFAULT_HOST_PROFILE_ID
    try:
        return _HOST_PROFILES[resolved_id]
    except KeyError as exc:
        available = ", ".join(SUPPORTED_HOST_PROFILE_IDS)
        raise KeyError(f"unknown host_profile={resolved_id!r}; expected one of: {available}") from exc


def host_profile_payload(profile_id: str | HostProfile | None = None) -> dict[str, Any]:
    if isinstance(profile_id, HostProfile):
        return profile_id.to_payload()
    return get_host_profile(profile_id).to_payload()
