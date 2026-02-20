from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agent_core.vlm import VLMClient


class DeterministicStubVLM(VLMClient):
    """Deterministic provider for smoke tests and local dev loop."""

    def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
        return {
            "provider": "deterministic_stub_v1",
            "image_path": str(image_path),
            "prompt": prompt,
            "summary": "Stub analysis: no real vision model invoked.",
            "next_steps": [
                "Open quest book",
                "Pin nearest progression task",
            ],
        }

