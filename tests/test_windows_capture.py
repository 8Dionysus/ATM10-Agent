from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from atm10_agent.perception import windows_capture


def test_parse_capture_region() -> None:
    assert windows_capture.parse_capture_region("10,20,300,400") == (10, 20, 300, 400)
    assert windows_capture.parse_capture_region(" ") is None
    with pytest.raises(ValueError, match="width and height"):
        windows_capture.parse_capture_region("10,20,0,400")


def test_capture_uses_window_handle_and_resizes_to_logical_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import ImageGrab

    captured: dict[str, Any] = {}
    monkeypatch.setattr(windows_capture.sys, "platform", "win32")

    def _fake_grab(
        bbox: tuple[int, int, int, int] | None = None,
        include_layered_windows: bool = False,
        all_screens: bool = False,
        xdisplay: str | None = None,
        window: int | None = None,
    ) -> Image.Image:
        _ = include_layered_windows, xdisplay
        captured.update({"bbox": bbox, "all_screens": all_screens, "window": window})
        return Image.new("RGB", (640, 360), color=(20, 28, 40))

    monkeypatch.setattr(ImageGrab, "grab", _fake_grab)
    screenshot_path = tmp_path / "window.png"
    payload = windows_capture.capture_screen_image(
        output_path=screenshot_path,
        monitor_index=0,
        window_handle=4242,
        window_title="Minecraft 1.21.1 - ATM10",
        window_bounds=[0, 0, 320, 180],
    )

    assert captured == {"bbox": None, "all_screens": False, "window": 4242}
    assert payload["capture_mode"] == "window"
    assert payload["capture_backend"] == "pillow_imagegrab_window"
    assert payload["window_handle"] == 4242
    assert payload["window_title"] == "Minecraft 1.21.1 - ATM10"
    assert payload["bbox"] == [0, 0, 320, 180]
    assert payload["resized_from"] == [640, 360]
    with Image.open(screenshot_path) as image:
        assert image.size == (320, 180)


def test_capture_prefers_dxcam_and_resizes_to_logical_monitor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(windows_capture.sys, "platform", "win32")

    class _FakeCamera:
        width = 2880
        height = 1920

        def grab(
            self,
            region: tuple[int, int, int, int] | None = None,
            new_frame_only: bool = True,
        ) -> np.ndarray:
            seen.update(region=region, new_frame_only=new_frame_only)
            return np.zeros((1920, 2880, 4), dtype=np.uint8)

    monkeypatch.setattr(
        windows_capture,
        "enumerate_display_monitors",
        lambda: [(0, 0, 1152, 768)],
    )
    monkeypatch.setattr(
        windows_capture,
        "_get_dxcam_camera",
        lambda *, output_index: _FakeCamera(),
    )

    screenshot_path = tmp_path / "monitor.png"
    payload = windows_capture.capture_screen_image(
        output_path=screenshot_path,
        monitor_index=0,
    )

    assert seen == {"region": None, "new_frame_only": False}
    assert payload["capture_backend"] == "dxcam_dxgi"
    assert payload["bbox"] == [0, 0, 1152, 768]
    assert payload["resized_from"] == [2880, 1920]
    assert "backend_errors" not in payload
    with Image.open(screenshot_path) as image:
        assert image.size == (1152, 768)


def test_capture_scales_logical_region_for_dxcam(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(windows_capture.sys, "platform", "win32")

    class _FakeCamera:
        width = 1920
        height = 1080

        def grab(
            self,
            region: tuple[int, int, int, int] | None = None,
            new_frame_only: bool = True,
        ) -> np.ndarray:
            seen.update(region=region, new_frame_only=new_frame_only)
            return np.zeros((100, 200, 4), dtype=np.uint8)

    monkeypatch.setattr(
        windows_capture,
        "enumerate_display_monitors",
        lambda: [(100, 50, 1060, 590)],
    )
    monkeypatch.setattr(
        windows_capture,
        "_get_dxcam_camera",
        lambda *, output_index: _FakeCamera(),
    )

    screenshot_path = tmp_path / "region.png"
    payload = windows_capture.capture_screen_image(
        output_path=screenshot_path,
        region=(110, 70, 100, 50),
    )

    assert seen == {"region": (20, 40, 220, 140), "new_frame_only": False}
    assert payload["capture_mode"] == "region"
    assert payload["resolved_monitor_index"] == 0
    assert payload["native_region"] == [20, 40, 220, 140]
    assert payload["resized_from"] == [200, 100]
    with Image.open(screenshot_path) as image:
        assert image.size == (100, 50)


def test_capture_records_dxcam_failure_and_falls_back_to_pillow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import ImageGrab

    captured: dict[str, Any] = {}
    monkeypatch.setattr(windows_capture.sys, "platform", "win32")
    monkeypatch.setattr(
        windows_capture,
        "enumerate_display_monitors",
        lambda: [(0, 0, 320, 180)],
    )

    def _fail_dxcam(*, output_index: int) -> Any:
        _ = output_index
        raise RuntimeError("dxcam failed")

    def _fake_grab(
        bbox: tuple[int, int, int, int] | None = None,
        include_layered_windows: bool = False,
        all_screens: bool = False,
        xdisplay: str | None = None,
        window: int | None = None,
    ) -> Image.Image:
        _ = include_layered_windows, xdisplay
        captured.update({"bbox": bbox, "all_screens": all_screens, "window": window})
        return Image.new("RGB", (320, 180), color=(12, 24, 36))

    monkeypatch.setattr(windows_capture, "_get_dxcam_camera", _fail_dxcam)
    monkeypatch.setattr(ImageGrab, "grab", _fake_grab)

    payload = windows_capture.capture_screen_image(
        output_path=tmp_path / "fallback.png",
        monitor_index=0,
    )

    assert captured == {"bbox": (0, 0, 320, 180), "all_screens": True, "window": None}
    assert payload["capture_backend"] == "pillow_imagegrab_desktop"
    assert payload["backend_errors"] == [
        {"backend": "dxcam_dxgi", "error": "dxcam failed"}
    ]


def test_module_is_import_safe_but_capture_is_windows_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(windows_capture.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="Windows only"):
        windows_capture.capture_screen_image(output_path=tmp_path / "capture.png")
