from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SUPPORTED_OPENVINO_VLM_MODEL_TYPES = (
    "gemma3",
    "internvl_chat",
    "llava",
    "llava-qwen2",
    "llava_next",
    "llava_next_video",
    "phi3_v",
    "phi4mm",
    "qwen2_5_vl",
)


def build_generation_config(ov_genai: Any, *, max_new_tokens: int, temperature: float) -> Any:
    config = ov_genai.GenerationConfig()
    config.max_new_tokens = int(max_new_tokens)

    normalized_temperature = float(temperature)
    if normalized_temperature > 0.0:
        config.do_sample = True
        config.temperature = normalized_temperature
    else:
        # OpenVINO GenAI 2026.0 validates temperature strictly when sampling is enabled.
        config.do_sample = False

    return config


def read_model_type_hint(model_dir: str | Path) -> str | None:
    config_path = Path(model_dir) / "config.json"
    if not config_path.exists():
        return None

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    model_type = payload.get("model_type")
    if model_type is None:
        return None
    normalized = str(model_type).strip()
    return normalized or None


def explain_vlm_runtime_error(*, model_dir: str | Path, error: Exception) -> str:
    resolved_model_dir = Path(model_dir)
    error_text = str(error).strip()
    model_type = read_model_type_hint(resolved_model_dir)

    base = f"OpenVINO VLM init failed for {resolved_model_dir}"
    if model_type:
        base += f" (model_type={model_type})"

    if "Unsupported '" in error_text and "VLM model type" in error_text:
        supported = ", ".join(SUPPORTED_OPENVINO_VLM_MODEL_TYPES)
        return (
            f"{base}: {error_text}. "
            f"This OpenVINO GenAI build supports: {supported}. "
            "Use a supported OpenVINO GenAI VLM model dir or keep pilot vision degraded."
        )

    if "Stateful models without `beam_idx` input are not supported" in error_text:
        return (
            f"{base}: {error_text}. "
            "The exported VLM graph is not compatible with OpenVINO GenAI VLMPipeline. "
            "Re-export a supported VLM model or use a different local vision runtime."
        )

    return f"{base}: {error_text}"
