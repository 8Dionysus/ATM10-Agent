from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.agent_core.io_voice import VoiceRuntimeUnavailableError
from src.agent_core.openvino_genai_compat import build_generation_config

DEFAULT_GROUNDED_REPLY_MODEL_DIR = Path("models") / "qwen3-8b-int4-cw-ov"


def _load_openvino_genai() -> Any:
    try:
        import openvino_genai as ov_genai
    except Exception as exc:  # pragma: no cover - dependency presence
        raise VoiceRuntimeUnavailableError(
            "OpenVINO GenAI runtime is not installed. Install dependency: openvino-genai."
        ) from exc
    return ov_genai


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


def _parse_reply_json(response_text: str) -> dict[str, Any]:
    normalized_response = _strip_reasoning_markup(response_text)
    if not normalized_response.strip():
        return {"answer_text": "", "cited_entities": [], "degraded_flags": []}
    try:
        payload = json.loads(_extract_json_candidate(normalized_response))
    except json.JSONDecodeError:
        return {"answer_text": normalized_response.strip(), "cited_entities": [], "degraded_flags": []}
    if not isinstance(payload, dict):
        return {"answer_text": normalized_response.strip(), "cited_entities": [], "degraded_flags": []}

    answer_text = payload.get("answer_text", "")
    cited_entities = payload.get("cited_entities", [])
    degraded_flags = payload.get("degraded_flags", [])
    if not isinstance(answer_text, str):
        answer_text = str(answer_text)
    if not isinstance(cited_entities, list):
        cited_entities = []
    if not isinstance(degraded_flags, list):
        degraded_flags = []
    return {
        "answer_text": answer_text.strip(),
        "cited_entities": [str(item) for item in cited_entities if str(item).strip()],
        "degraded_flags": [str(item) for item in degraded_flags if str(item).strip()],
    }


def _strip_reasoning_markup(response_text: str) -> str:
    normalized = str(response_text or "").strip()
    while normalized.startswith("<think>"):
        end_index = normalized.find("</think>")
        if end_index < 0:
            return normalized
        normalized = normalized[end_index + len("</think>") :].lstrip()
    return normalized


def _extract_json_candidate(response_text: str) -> str:
    start_index = response_text.find("{")
    end_index = response_text.rfind("}")
    if start_index >= 0 and end_index > start_index:
        return response_text[start_index : end_index + 1]
    return response_text


def _normalize_preferred_reply_language(
    preferred_language: str | None,
) -> str:
    normalized = str(preferred_language or "").strip().lower()
    if normalized.startswith("en"):
        return "en"
    return "ru"


def build_grounded_reply_prompt(
    *,
    transcript: str,
    visual_summary: str | None,
    citations: list[Mapping[str, Any]],
    hybrid_summary: Mapping[str, Any] | None,
    degraded_flags: list[str],
    preferred_language: str | None = None,
) -> str:
    rendered_citations: list[str] = []
    for item in citations[:5]:
        citation = item.get("citation")
        citation = citation if isinstance(citation, Mapping) else {}
        rendered_citations.append(
            json.dumps(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "source": citation.get("source"),
                    "path": citation.get("path"),
                    "matched_entities": item.get("matched_entities", []),
                    "planner_source": item.get("planner_source"),
                },
                ensure_ascii=False,
            )
        )

    hybrid_summary_payload = dict(hybrid_summary or {})
    prompt_payload = {
        "transcript": transcript.strip(),
        "visual_summary": (visual_summary or "").strip(),
        "hybrid_summary": hybrid_summary_payload,
        "citations": rendered_citations,
        "degraded_flags": degraded_flags,
        "preferred_answer_language": _normalize_preferred_reply_language(preferred_language),
    }
    return (
        "You are a local ATM10 observer copilot speaking to the player during live gameplay. "
        "Return only a JSON object with keys answer_text (string), "
        "cited_entities (array of short strings), degraded_flags (array of short strings). "
        "Do not emit chain-of-thought, reasoning, or <think> tags. "
        "Keep answer_text short, actionable, and player-facing. "
        "Use Russian by default unless preferred_answer_language is en. "
        "Do not mention internal diagnostics, provider details, or grounding failures unless you cannot give a useful gameplay answer at all. "
        "Do not fabricate citations, and keep the answer grounded in the supplied transcript, screen summary, and citations.\n\n"
        f"{json.dumps(prompt_payload, ensure_ascii=False, indent=2)}"
    )


class OpenVINOGroundedReplyClient:
    """Local OpenVINO GenAI LLM provider for grounded observer replies."""

    def __init__(
        self,
        *,
        pipeline: Any,
        model_dir: Path,
        device: str,
        max_new_tokens: int = 256,
        temperature: float = 0.1,
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
        model_dir: str | Path = DEFAULT_GROUNDED_REPLY_MODEL_DIR,
        device: str = "NPU",
        max_new_tokens: int = 256,
        temperature: float = 0.1,
    ) -> "OpenVINOGroundedReplyClient":
        resolved_model_dir = Path(model_dir)
        if not resolved_model_dir.exists():
            raise FileNotFoundError(f"Grounded reply model directory does not exist: {resolved_model_dir}")

        normalized_device = str(device).strip().upper()
        if normalized_device not in {"CPU", "GPU", "NPU"}:
            raise ValueError("device must be one of: CPU, GPU, NPU.")

        ov_genai = _load_openvino_genai()
        pipeline = ov_genai.LLMPipeline(str(resolved_model_dir), normalized_device)
        return cls(
            pipeline=pipeline,
            model_dir=resolved_model_dir,
            device=normalized_device,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )

    def generate_reply(
        self,
        *,
        transcript: str,
        visual_summary: str | None,
        citations: list[Mapping[str, Any]],
        hybrid_summary: Mapping[str, Any] | None,
        degraded_flags: list[str] | None = None,
        preferred_language: str | None = None,
    ) -> dict[str, Any]:
        prompt = build_grounded_reply_prompt(
            transcript=transcript,
            visual_summary=visual_summary,
            citations=citations,
            hybrid_summary=hybrid_summary,
            degraded_flags=list(degraded_flags or []),
            preferred_language=preferred_language,
        )
        ov_genai = _load_openvino_genai()
        generation_config = build_generation_config(
            ov_genai,
            max_new_tokens=self._max_new_tokens,
            temperature=self._temperature,
        )
        result = self._pipeline.generate(prompt, generation_config=generation_config)
        response_text = _extract_output_text(result)
        parsed = _parse_reply_json(response_text)
        return {
            "provider": "openvino_genai_grounded_reply_v1",
            "model": self._model_dir.name,
            "device": self._device,
            "prompt": prompt,
            "answer_text": parsed["answer_text"],
            "cited_entities": parsed["cited_entities"],
            "degraded_flags": parsed["degraded_flags"],
            "raw_response_text": response_text,
        }


class DeterministicGroundedReplyStub:
    """Deterministic local stub for smoke tests and artifact coverage."""

    @staticmethod
    def _has_usable_transcript(text: str) -> bool:
        normalized = str(text or "").strip()
        return any(char.isalnum() for char in normalized)

    @staticmethod
    def _humanize_status(status: str) -> str:
        normalized = str(status or "").strip().replace("_", " ")
        return normalized or "unknown"

    def generate_reply(
        self,
        *,
        transcript: str,
        visual_summary: str | None,
        citations: list[Mapping[str, Any]],
        hybrid_summary: Mapping[str, Any] | None,
        degraded_flags: list[str] | None = None,
        preferred_language: str | None = None,
    ) -> dict[str, Any]:
        cited_entities: list[str] = []
        for item in citations[:3]:
            title = str(item.get("title", "")).strip()
            if title:
                cited_entities.append(title)
        transcript_text = str(transcript or "").strip()
        answer_parts: list[str] = []
        normalized_language = _normalize_preferred_reply_language(preferred_language)
        if hybrid_summary is not None:
            planner_status = str(hybrid_summary.get("planner_status", "")).strip()
        else:
            planner_status = ""
        degraded = [str(item) for item in (degraded_flags or []) if str(item).strip()]
        if degraded:
            answer_parts.append("Режим с ограничениями." if normalized_language == "ru" else "Pilot degraded.")
        if self._has_usable_transcript(transcript_text):
            if normalized_language == "ru":
                answer_parts.append(f"Я услышал: {transcript_text}.")
            else:
                answer_parts.append(f"Heard: {transcript_text}.")
        else:
            answer_parts.append(
                "Голос не разобран."
                if normalized_language == "ru"
                else "Microphone transcript unavailable."
            )
        if planner_status:
            if normalized_language == "ru":
                answer_parts.append(f"Контекст: {self._humanize_status(planner_status)}.")
            else:
                answer_parts.append(f"Hybrid: {self._humanize_status(planner_status)}.")
        elif cited_entities:
            if normalized_language == "ru":
                answer_parts.append(f"Опора: {', '.join(cited_entities[:2])}.")
            else:
                answer_parts.append(f"Refs: {', '.join(cited_entities[:2])}.")
        elif isinstance(visual_summary, str) and visual_summary.strip() and "Stub analysis:" not in visual_summary:
            if normalized_language == "ru":
                answer_parts.append(f"На экране: {visual_summary.strip()}.")
            else:
                answer_parts.append(f"Screen: {visual_summary.strip()}.")
        return {
            "provider": "deterministic_grounded_reply_stub_v1",
            "model": "stub",
            "device": "local",
            "prompt": "",
            "answer_text": " ".join(answer_parts).strip(),
            "cited_entities": cited_entities,
            "degraded_flags": degraded,
            "raw_response_text": "",
        }
