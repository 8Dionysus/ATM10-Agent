import base64
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.phase_a_smoke as phase_a_smoke
import src.agent_core.vlm_openai as vlm_openai
from src.agent_core.vlm_openai import OpenAIResponsesVLM


def _write_placeholder_png(path: Path) -> None:
    png_base64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sUP4A0AAAAASUVORK5CYII="
    )
    path.write_bytes(base64.b64decode(png_base64))


def test_openai_vlm_parses_json_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    _write_placeholder_png(image_path)

    def fake_post_json(*, url: str, payload: dict, headers: dict, timeout_sec: float) -> dict:
        assert url.endswith("/responses")
        assert headers["Authorization"] == "Bearer test_key"
        assert isinstance(timeout_sec, float)
        assert payload["model"] == "gpt-4.1-mini"
        return {
            "id": "resp_test",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"summary":"Detected quest context.","next_steps":["Open quest book"]}',
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(vlm_openai, "_post_json", fake_post_json)

    client = OpenAIResponsesVLM(api_key="test_key", model="gpt-4.1-mini")
    result = client.analyze_image(image_path=image_path, prompt="test prompt")

    assert result["provider"] == "openai_responses_api_v1"
    assert result["response_id"] == "resp_test"
    assert result["summary"] == "Detected quest context."
    assert result["next_steps"] == ["Open quest book"]


def test_openai_vlm_handles_non_json_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    _write_placeholder_png(image_path)

    def fake_post_json(*, url: str, payload: dict, headers: dict, timeout_sec: float) -> dict:
        return {
            "id": "resp_test",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "free-form fallback text"},
                    ],
                }
            ],
        }

    monkeypatch.setattr(vlm_openai, "_post_json", fake_post_json)

    client = OpenAIResponsesVLM(api_key="test_key")
    result = client.analyze_image(image_path=image_path, prompt="test prompt")

    assert result["summary"] == "free-form fallback text"
    assert result["next_steps"] == []


def test_phase_a_openai_failure_falls_back_to_stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FailingOpenAIResponsesVLM:
        def __init__(self, *, api_key: str, model: str, api_base: str) -> None:
            assert api_key == "test_key"
            assert model == "gpt-4.1-mini"
            assert api_base == "https://api.openai.com/v1"

        def analyze_image(self, *, image_path: Path, prompt: str) -> dict:
            raise RuntimeError("simulated network failure")

    monkeypatch.setattr(phase_a_smoke, "OpenAIResponsesVLM", FailingOpenAIResponsesVLM)
    run_result = phase_a_smoke.run_phase_a_smoke(
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 20, 14, 0, 0, tzinfo=timezone.utc),
        vlm_provider="openai",
        openai_api_key="test_key",
    )

    run_payload = run_result["run_payload"]
    response_payload = run_result["response_payload"]

    assert run_payload["vlm"]["requested"] == "openai"
    assert run_payload["vlm"]["resolved"] == "stub"
    assert run_payload["vlm"]["fallback_used"] is True
    assert run_payload["vlm"]["provider_failed"] == "openai"
    assert "simulated network failure" in run_payload["vlm"]["fallback_reason"]
    assert response_payload["provider"] == "deterministic_stub_v1"


def test_phase_a_strict_openai_raises_without_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        phase_a_smoke.run_phase_a_smoke(
            runs_dir=tmp_path / "runs",
            now=datetime(2026, 2, 20, 14, 0, 0, tzinfo=timezone.utc),
            vlm_provider="openai",
            openai_api_key=None,
            allow_vlm_fallback=False,
        )
