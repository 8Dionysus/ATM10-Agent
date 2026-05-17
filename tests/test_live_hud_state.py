from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import src.agent_core.live_hud_state as live_hud_state


def test_build_live_hud_state_preserves_error_when_ocr_fails_without_hook(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_bytes(b"not-a-real-image")

    def _raise_ocr_failure(**_kwargs):
        raise RuntimeError("tesseract crashed")

    monkeypatch.setattr(live_hud_state, "run_tesseract_ocr", _raise_ocr_failure)

    payload = live_hud_state.build_live_hud_state(
        screenshot_path=screenshot_path,
        hook_json=None,
        now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
    )

    assert payload["status"] == "error"
    assert payload["sources"]["ocr"]["status"] == "error"
    assert "ocr_failed" in payload["reason_codes"]
