from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.text_core_openvino_demo as text_demo


def test_text_core_openvino_demo_writes_response_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    class _FakeGenerationConfig:
        def __init__(self) -> None:
            self.max_new_tokens = None
            self.temperature = 1.0
            self.do_sample = False

    class _FakePipeline:
        def __init__(self, model_dir: str, device: str) -> None:
            calls["model_dir"] = model_dir
            calls["device"] = device

        def generate(self, prompt: str, *, generation_config: _FakeGenerationConfig):
            calls["prompt"] = prompt
            calls["max_new_tokens"] = generation_config.max_new_tokens
            calls["temperature"] = generation_config.temperature
            calls["do_sample"] = generation_config.do_sample
            return SimpleNamespace(text="fake answer")

    monkeypatch.setattr(
        text_demo,
        "_load_openvino_genai",
        lambda: SimpleNamespace(LLMPipeline=_FakePipeline, GenerationConfig=_FakeGenerationConfig),
    )

    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    result = text_demo.run_text_core_openvino_demo(
        model_dir=model_dir,
        prompt="how to start mekanism?",
        device="NPU",
        max_new_tokens=64,
        temperature=0.1,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 18, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    response_payload = json.loads((run_dir / "response.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260222_180000-text-core-openvino"
    assert run_payload["status"] == "ok"
    assert response_payload["text"] == "fake answer"
    assert calls == {
        "model_dir": str(model_dir),
        "device": "NPU",
        "prompt": "how to start mekanism?",
        "max_new_tokens": 64,
        "temperature": 0.1,
        "do_sample": True,
    }


def test_text_core_openvino_demo_uses_greedy_config_for_zero_temperature(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: dict[str, object] = {}

    class _FakeGenerationConfig:
        def __init__(self) -> None:
            self.max_new_tokens = None
            self.temperature = 1.0
            self.do_sample = False

    class _FakePipeline:
        def __init__(self, model_dir: str, device: str) -> None:
            _ = model_dir, device

        def generate(self, prompt: str, *, generation_config: _FakeGenerationConfig):
            calls["prompt"] = prompt
            calls["max_new_tokens"] = generation_config.max_new_tokens
            calls["temperature"] = generation_config.temperature
            calls["do_sample"] = generation_config.do_sample
            return SimpleNamespace(text="greedy answer")

    monkeypatch.setattr(
        text_demo,
        "_load_openvino_genai",
        lambda: SimpleNamespace(LLMPipeline=_FakePipeline, GenerationConfig=_FakeGenerationConfig),
    )

    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    result = text_demo.run_text_core_openvino_demo(
        model_dir=model_dir,
        prompt="hello",
        temperature=0.0,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 18, 0, 1, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    assert calls == {
        "prompt": "hello",
        "max_new_tokens": 128,
        "temperature": 1.0,
        "do_sample": False,
    }


def test_text_core_openvino_demo_missing_runtime_reports_dependency_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _raise_missing_runtime():
        raise text_demo.VoiceRuntimeUnavailableError("OpenVINO GenAI runtime is not installed.")

    monkeypatch.setattr(text_demo, "_load_openvino_genai", _raise_missing_runtime)
    model_dir = tmp_path / "model"
    model_dir.mkdir(parents=True, exist_ok=True)

    result = text_demo.run_text_core_openvino_demo(
        model_dir=model_dir,
        prompt="hello",
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 18, 1, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["run_payload"]["error_code"] == "runtime_missing_dependency"


def test_text_core_openvino_demo_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["text_core_openvino_demo.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        text_demo.parse_args()
    assert exc.value.code == 0
