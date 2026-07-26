from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class VLMClient(Protocol):
    """Minimal VLM interface for image analysis."""

    def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, Any]:
        """Return JSON-serializable analysis payload."""
        ...

