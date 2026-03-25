from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import src.agent_core.grounded_reply_openvino as grounded_reply_openvino
from src.agent_core.grounded_reply_openvino import (
    DeterministicGroundedReplyStub,
    OpenVINOGroundedReplyClient,
    sanitize_grounded_reply_answer_text,
)


class _FakeGenerationConfig:
    def __init__(self) -> None:
        self.max_new_tokens = None
        self.temperature = 1.0
        self.do_sample = False


class _FakePipeline:
    def generate(self, prompt: str, *, generation_config: _FakeGenerationConfig):
        assert "answer_text" in prompt
        assert generation_config.max_new_tokens == 256
        assert generation_config.temperature == 0.1
        assert generation_config.do_sample is True
        return (
            '{"answer_text":"Use the quest book to confirm the next steel task.",'
            '"cited_entities":["Quest Book"],'
            '"degraded_flags":["retrieval_only_fallback"]}'
        )


def test_openvino_grounded_reply_parses_json(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "qwen3-8b"
    model_dir.mkdir(parents=True)
    monkeypatch.setattr(
        grounded_reply_openvino,
        "_load_openvino_genai",
        lambda: SimpleNamespace(LLMPipeline=lambda model, device: _FakePipeline(), GenerationConfig=_FakeGenerationConfig),
    )

    client = OpenVINOGroundedReplyClient.from_pretrained(model_dir=model_dir, device="CPU")
    result = client.generate_reply(
        transcript="What is next?",
        visual_summary="A quest book is open.",
        citations=[{"title": "Quest Book", "citation": {"path": "fixture.jsonl"}}],
        hybrid_summary={"planner_status": "retrieval_only_fallback"},
        degraded_flags=["retrieval_only_fallback"],
        preferred_language="ru",
    )

    assert result["provider"] == "openvino_genai_grounded_reply_v1"
    assert "quest book" in result["answer_text"].lower()
    assert result["cited_entities"] == ["Quest Book"]
    assert result["degraded_flags"] == ["retrieval_only_fallback"]
    assert '"preferred_answer_language": "ru"' in result["prompt"]


def test_openvino_grounded_reply_strips_thinking_markup(monkeypatch, tmp_path: Path) -> None:
    class _FakeThinkingPipeline:
        def generate(self, prompt: str, *, generation_config: _FakeGenerationConfig):
            assert "answer_text" in prompt
            assert generation_config.do_sample is True
            return (
                "<think>reasoning omitted</think>\n"
                '{"answer_text":"Check the quest book first.","cited_entities":["Quest Book"],"degraded_flags":[]}'
            )

    model_dir = tmp_path / "qwen3-8b"
    model_dir.mkdir(parents=True)
    monkeypatch.setattr(
        grounded_reply_openvino,
        "_load_openvino_genai",
        lambda: SimpleNamespace(
            LLMPipeline=lambda model, device: _FakeThinkingPipeline(),
            GenerationConfig=_FakeGenerationConfig,
        ),
    )

    client = OpenVINOGroundedReplyClient.from_pretrained(model_dir=model_dir, device="CPU")
    result = client.generate_reply(
        transcript="What next?",
        visual_summary="A quest book is nearby.",
        citations=[{"title": "Quest Book", "citation": {"path": "fixture.jsonl"}}],
        hybrid_summary={"planner_status": "ok"},
        degraded_flags=[],
        preferred_language="en",
    )

    assert result["answer_text"] == "Check the quest book first."
    assert result["cited_entities"] == ["Quest Book"]


def test_openvino_grounded_reply_rejects_unclosed_thinking_leak(monkeypatch, tmp_path: Path) -> None:
    class _FakeThinkingLeakPipeline:
        def generate(self, prompt: str, *, generation_config: _FakeGenerationConfig):
            assert "answer_text" in prompt
            assert generation_config.do_sample is True
            return (
                "<think>\n"
                "Okay, let's tackle this. The user is in a dark cave. "
                "The answer should be in JSON format with answer_text and degraded_flags."
            )

    model_dir = tmp_path / "qwen3-8b"
    model_dir.mkdir(parents=True)
    monkeypatch.setattr(
        grounded_reply_openvino,
        "_load_openvino_genai",
        lambda: SimpleNamespace(
            LLMPipeline=lambda model, device: _FakeThinkingLeakPipeline(),
            GenerationConfig=_FakeGenerationConfig,
        ),
    )

    client = OpenVINOGroundedReplyClient.from_pretrained(model_dir=model_dir, device="CPU")
    result = client.generate_reply(
        transcript="Спасибо",
        visual_summary="Темная пещера.",
        citations=[],
        hybrid_summary={"planner_status": "grounding_unavailable"},
        degraded_flags=["hybrid_degraded"],
        preferred_language="ru",
    )

    assert result["answer_text"] == ""
    assert "grounded_reply_output_not_json" in result["degraded_flags"]
    assert "grounded_reply_reasoning_leak" in result["degraded_flags"]


def test_sanitize_grounded_reply_answer_text_rejects_reasoning_leak() -> None:
    answer_text, degraded_flags = sanitize_grounded_reply_answer_text(
        "<think> The user is asking what to do next."
    )

    assert answer_text == ""
    assert degraded_flags == ["grounded_reply_reasoning_leak"]


def test_sanitize_grounded_reply_answer_text_caps_to_single_sentence() -> None:
    answer_text, degraded_flags = sanitize_grounded_reply_answer_text(
        "Сначала открой книгу квестов. Потом посмотри на ближайшую задачу."
    )

    assert answer_text == "Сначала открой книгу квестов"
    assert degraded_flags == ["grounded_reply_answer_sentence_capped"]


def test_deterministic_grounded_reply_stub_keeps_answer_concise_for_missing_transcript() -> None:
    client = DeterministicGroundedReplyStub()

    result = client.generate_reply(
        transcript=".",
        visual_summary="Stub analysis: no real vision model invoked.",
        citations=[],
        hybrid_summary={"planner_status": "grounding_unavailable"},
        degraded_flags=["hybrid_degraded"],
        preferred_language="ru",
    )

    assert result["answer_text"].startswith("Режим с ограничениями.")
    assert "Голос не разобран." in result["answer_text"]
    assert "Контекст: grounding unavailable." in result["answer_text"]
    assert len(result["answer_text"]) < 100
