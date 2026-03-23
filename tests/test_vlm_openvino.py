from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

import src.agent_core.vlm_openvino as vlm_openvino
from src.agent_core.vlm_openvino import OpenVINOVLMClient


class _FakeGenerationConfig:
    def __init__(self) -> None:
        self.max_new_tokens = None
        self.temperature = 1.0
        self.do_sample = False


class _FakePipeline:
    def generate(self, prompt: str, *, images: list[object], generation_config: _FakeGenerationConfig):
        assert "summary" in prompt
        assert len(images) == 1
        assert generation_config.max_new_tokens == 192
        assert generation_config.do_sample is False
        return '{"summary":"Detected quest context.","next_steps":["Open quest book"]}'


def test_openvino_vlm_parses_json(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "qwen3-vl"
    model_dir.mkdir(parents=True)
    image_path = tmp_path / "image.png"
    Image.new("RGB", (16, 16), color=(1, 2, 3)).save(image_path)

    monkeypatch.setattr(
        vlm_openvino,
        "_load_openvino_genai",
        lambda: SimpleNamespace(VLMPipeline=lambda model, device: _FakePipeline(), GenerationConfig=_FakeGenerationConfig),
    )
    monkeypatch.setattr(vlm_openvino, "_load_openvino_tensor_type", lambda: (lambda array: array))

    client = OpenVINOVLMClient.from_pretrained(model_dir=model_dir, device="CPU")
    result = client.analyze_image(image_path=image_path, prompt="Return summary JSON.")

    assert result["provider"] == "openvino_genai_vlm_v1"
    assert result["summary"] == "Detected quest context."
    assert result["next_steps"] == ["Open quest book"]


def test_openvino_vlm_reports_unsupported_model_type(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "qwen3-vl"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text('{"model_type":"qwen3_vl"}', encoding="utf-8")

    def _raise_unsupported(_model: str, _device: str):
        raise RuntimeError("Unsupported 'qwen3_vl' VLM model type")

    monkeypatch.setattr(
        vlm_openvino,
        "_load_openvino_genai",
        lambda: SimpleNamespace(VLMPipeline=_raise_unsupported),
    )

    with pytest.raises(RuntimeError) as exc_info:
        OpenVINOVLMClient.from_pretrained(model_dir=model_dir, device="CPU")

    error_text = str(exc_info.value)
    assert "model_type=qwen3_vl" in error_text
    assert "qwen2_5_vl" in error_text
