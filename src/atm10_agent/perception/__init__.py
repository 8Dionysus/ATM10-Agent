"""Perception stage for the deterministic companion baseline."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from atm10_agent.agent_core.vlm_stub import DeterministicStubVLM


_PLACEHOLDER_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sUP4A0AAAAASUVORK5CYII="
)


def perceive(*, image_path: Path | None, prompt: str, run_dir: Path) -> dict[str, Any]:
    selected_path = image_path
    source = "provided_image"
    if selected_path is None:
        selected_path = run_dir / "perception-placeholder.png"
        selected_path.write_bytes(base64.b64decode(_PLACEHOLDER_PNG))
        source = "deterministic_placeholder"
    elif not selected_path.is_file():
        raise FileNotFoundError(f"image_path does not exist: {selected_path}")

    payload = DeterministicStubVLM().analyze_image(image_path=selected_path, prompt=prompt)
    return {
        "schema_version": "atm10_perception_v1",
        "status": "ok",
        "provider": payload["provider"],
        "source": source,
        "image_path": str(selected_path),
        "summary": payload["summary"],
        "next_steps": list(payload["next_steps"]),
    }
