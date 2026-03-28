from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from src.agent_core.io_voice import VoiceRuntimeUnavailableError
from src.agent_core.openvino_genai_compat import build_generation_config, explain_vlm_runtime_error
from src.agent_core.vlm import VLMClient

DEFAULT_OPENVINO_VLM_MODEL_DIR = Path("models") / "qwen2.5-vl-7b-instruct-int4-ov"
_SUMMARY_FIELD_PATTERN = re.compile(r'"summary"\s*:\s*"((?:\\.|[^"\\])*)"', re.IGNORECASE | re.DOTALL)


def _load_openvino_genai() -> Any:
    try:
        import openvino_genai as ov_genai
    except Exception as exc:  # pragma: no cover - dependency presence
        raise VoiceRuntimeUnavailableError(
            "OpenVINO GenAI runtime is not installed. Install dependency: openvino-genai."
        ) from exc
    return ov_genai


def _load_openvino_tensor_type() -> Any:
    try:
        from openvino import Tensor
    except Exception as exc:  # pragma: no cover - dependency presence
        raise VoiceRuntimeUnavailableError(
            "OpenVINO runtime is not installed. Install dependency: openvino."
        ) from exc
    return Tensor


def _extract_output_text(result: Any) -> str:
    text_attr = getattr(result, "text", None)
    if text_attr is not None:
        return str(text_attr)

    texts_attr = getattr(result, "texts", None)
    if isinstance(texts_attr, (list, tuple)) and texts_attr:
        return str(texts_attr[0])

    if isinstance(result, str):
        return result
    return str(result)


def _read_image_tensor(image_path: Path) -> Any:
    if not image_path.exists():
        raise FileNotFoundError(f"image_path does not exist: {image_path}")
    tensor_type = _load_openvino_tensor_type()
    image = Image.open(image_path).convert("RGB")
    image_data = np.array(image, dtype=np.uint8).reshape(1, image.height, image.width, 3)
    return tensor_type(image_data)


def _parse_vlm_json(response_text: str) -> dict[str, Any]:
    normalized_response = _strip_markdown_fence(_strip_reasoning_markup(response_text))
    if not normalized_response.strip():
        return {"summary": "", "next_steps": []}
    try:
        payload = json.loads(_extract_json_candidate(normalized_response))
    except json.JSONDecodeError:
        extracted_summary = _extract_summary_field_candidate(normalized_response)
        if extracted_summary is not None:
            return {"summary": sanitize_vlm_summary_text(extracted_summary), "next_steps": []}
        return {"summary": sanitize_vlm_summary_text(normalized_response), "next_steps": []}
    if not isinstance(payload, dict):
        extracted_summary = _extract_summary_field_candidate(normalized_response)
        if extracted_summary is not None:
            return {"summary": sanitize_vlm_summary_text(extracted_summary), "next_steps": []}
        return {"summary": sanitize_vlm_summary_text(normalized_response), "next_steps": []}
    summary = payload.get("summary", "")
    next_steps = payload.get("next_steps", [])
    if not isinstance(summary, str):
        summary = str(summary)
    if not isinstance(next_steps, list):
        next_steps = []
    return {
        "summary": sanitize_vlm_summary_text(summary),
        "next_steps": [str(item) for item in next_steps if str(item).strip()],
    }


def _strip_reasoning_markup(response_text: str) -> str:
    normalized = str(response_text or "").strip()
    while normalized.startswith("<think>"):
        end_index = normalized.find("</think>")
        if end_index < 0:
            return normalized
        normalized = normalized[end_index + len("</think>") :].lstrip()
    return normalized


def _strip_markdown_fence(response_text: str) -> str:
    normalized = str(response_text or "").strip()
    normalized = re.sub(r"^\s*```(?:json)?\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*```\s*$", "", normalized)
    return normalized.strip()


def _extract_json_candidate(response_text: str) -> str:
    start_index = response_text.find("{")
    end_index = response_text.rfind("}")
    if start_index >= 0 and end_index > start_index:
        return response_text[start_index : end_index + 1]
    return response_text


def _extract_summary_field_candidate(response_text: str) -> str | None:
    match = _SUMMARY_FIELD_PATTERN.search(str(response_text or ""))
    if match is None:
        return None
    encoded_value = match.group(1)
    try:
        return str(json.loads(f'"{encoded_value}"'))
    except json.JSONDecodeError:
        return encoded_value.replace("\\n", " ").replace("\\r", " ").replace("\\t", " ").replace('\\"', '"')


def sanitize_vlm_summary_text(summary_text: str) -> str:
    normalized = _strip_markdown_fence(_strip_reasoning_markup(summary_text))
    extracted_summary = _extract_summary_field_candidate(normalized)
    if extracted_summary is not None:
        normalized = extracted_summary
    normalized = " ".join(str(normalized or "").replace("\r", " ").replace("\n", " ").split())
    if normalized.lower().startswith("summary:"):
        normalized = normalized.split(":", 1)[1].strip()
    normalized = normalized.strip("`{}[]\"' ")
    normalized = re.sub(r"!{2,}", "!", normalized)
    normalized = re.sub(r"\?{2,}", "?", normalized)
    return normalized.strip()


class OpenVINOVLMClient(VLMClient):
    """Local OpenVINO GenAI VLM provider for supported Qwen2.5-VL-style models."""

    def __init__(
        self,
        *,
        pipeline: Any,
        model_dir: Path,
        device: str,
        max_new_tokens: int = 192,
        temperature: float = 0.0,
    ) -> None:
        self._pipeline = pipeline
        self._model_dir = Path(model_dir)
        self._device = str(device).strip().upper()
        self._max_new_tokens = int(max_new_tokens)
        self._temperature = float(temperature)

    @classmethod
    def from_pretrained(
        cls,
        *,
        model_dir: str | Path = DEFAULT_OPENVINO_VLM_MODEL_DIR,
        device: str = "NPU",
        max_new_tokens: int = 192,
        temperature: float = 0.0,
    ) -> "OpenVINOVLMClient":
        resolved_model_dir = Path(model_dir)
        if not resolved_model_dir.exists():
            raise FileNotFoundError(f"VLM model directory does not exist: {resolved_model_dir}")

        normalized_device = str(device).strip().upper()
        if normalized_device not in {"CPU", "GPU", "NPU"}:
            raise ValueError("device must be one of: CPU, GPU, NPU.")

        ov_genai = _load_openvino_genai()
        try:
            pipeline = ov_genai.VLMPipeline(str(resolved_model_dir), normalized_device)
        except Exception as exc:
            raise RuntimeError(explain_vlm_runtime_error(model_dir=resolved_model_dir, error=exc)) from exc
        return cls(
            pipeline=pipeline,
            model_dir=resolved_model_dir,
            device=normalized_device,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )

    def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
        normalized_prompt = str(prompt).strip()
        if not normalized_prompt:
            raise ValueError("prompt must be non-empty.")

        ov_genai = _load_openvino_genai()
        generation_config = build_generation_config(
            ov_genai,
            max_new_tokens=self._max_new_tokens,
            temperature=self._temperature,
        )

        image_tensor = _read_image_tensor(image_path)
        response = self._pipeline.generate(
            normalized_prompt,
            images=[image_tensor],
            generation_config=generation_config,
        )
        response_text = _extract_output_text(response)
        parsed = _parse_vlm_json(response_text)
        return {
            "provider": "openvino_genai_vlm_v1",
            "model": self._model_dir.name,
            "device": self._device,
            "summary": parsed["summary"],
            "next_steps": parsed["next_steps"],
            "raw_response_text": response_text,
        }
