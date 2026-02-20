from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from src.agent_core.vlm import VLMClient

DEFAULT_API_BASE = "https://api.openai.com/v1"
DEFAULT_VLM_MODEL = "gpt-4.1-mini"


def _post_json(*, url: str, payload: dict[str, Any], headers: dict[str, str], timeout_sec: float) -> dict[str, Any]:
    request = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_output_text(response_payload: dict[str, Any]) -> str:
    output_items = response_payload.get("output", [])
    if not isinstance(output_items, list):
        return ""

    chunks: list[str] = []
    for item in output_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        content_items = item.get("content", [])
        if not isinstance(content_items, list):
            continue
        for content_item in content_items:
            if not isinstance(content_item, dict):
                continue
            if content_item.get("type") != "output_text":
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text:
                chunks.append(text)
    return "\n".join(chunks).strip()


class OpenAIResponsesVLM(VLMClient):
    """Vision provider backed by OpenAI Responses API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_VLM_MODEL,
        api_base: str = DEFAULT_API_BASE,
        timeout_sec: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for provider=openai.")
        self._api_key = api_key
        self._model = model
        self._api_base = api_base.rstrip("/")
        self._timeout_sec = timeout_sec

    def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
        image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
        data_url = f"data:image/png;base64,{image_data}"

        payload: dict[str, Any] = {
            "model": self._model,
            "input": [
                {
                    "role": "developer",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Return only a JSON object with keys: summary (string) and "
                                "next_steps (array of short strings)."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url},
                    ],
                },
            ],
            "text": {"format": {"type": "json_object"}},
        }

        response_payload = _post_json(
            url=f"{self._api_base}/responses",
            payload=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout_sec=self._timeout_sec,
        )

        response_text = _extract_output_text(response_payload)
        parsed: dict[str, Any]
        if response_text:
            try:
                parsed_json = json.loads(response_text)
                if isinstance(parsed_json, dict):
                    parsed = parsed_json
                else:
                    parsed = {"summary": response_text, "next_steps": []}
            except json.JSONDecodeError:
                parsed = {"summary": response_text, "next_steps": []}
        else:
            parsed = {"summary": "", "next_steps": []}

        next_steps = parsed.get("next_steps", [])
        if not isinstance(next_steps, list):
            next_steps = []

        summary = parsed.get("summary", "")
        if not isinstance(summary, str):
            summary = str(summary)

        return {
            "provider": "openai_responses_api_v1",
            "model": self._model,
            "response_id": response_payload.get("id"),
            "summary": summary,
            "next_steps": [str(step) for step in next_steps],
            "raw_response_text": response_text,
        }
