"""Windows-first screen capture with an explicit, inspectable fallback chain.

The module is import-safe on every supported platform. Optional Windows
dependencies are loaded only when capture is requested so the portable ATM10
core remains dependency-free.
"""

from __future__ import annotations

import ctypes
import sys
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


DXCAM_BACKEND = "dxgi"
DXCAM_OUTPUT_COLOR = "BGRA"
DXCAM_PROCESSOR_BACKEND = "numpy"

_DXCAM_CAMERA_CACHE: dict[tuple[int, str], Any] = {}
_DXCAM_CAMERA_LOCK = threading.Lock()


def parse_capture_region(raw_value: str | None) -> tuple[int, int, int, int] | None:
    """Parse ``x,y,width,height`` without silently accepting invalid geometry."""

    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    if not normalized:
        return None
    pieces = [item.strip() for item in normalized.split(",")]
    if len(pieces) != 4:
        raise ValueError("capture region must use x,y,w,h format.")
    try:
        x, y, width, height = (int(item) for item in pieces)
    except ValueError as exc:
        raise ValueError("capture region values must be integers.") from exc
    if width <= 0 or height <= 0:
        raise ValueError("capture region width and height must be > 0.")
    return x, y, width, height


def _format_region(region: tuple[int, int, int, int] | None) -> list[int] | None:
    return None if region is None else [int(value) for value in region]


def _normalize_window_bounds(
    window_bounds: Mapping[str, Any] | Sequence[int] | None,
) -> list[int] | None:
    if isinstance(window_bounds, Mapping):
        try:
            return [
                int(window_bounds.get("left")),
                int(window_bounds.get("top")),
                int(window_bounds.get("right")),
                int(window_bounds.get("bottom")),
            ]
        except (TypeError, ValueError):
            return None
    if isinstance(window_bounds, Sequence) and not isinstance(
        window_bounds,
        (str, bytes, bytearray),
    ):
        if len(window_bounds) != 4:
            return None
        try:
            return [int(item) for item in window_bounds]
        except (TypeError, ValueError):
            return None
    return None


def enumerate_display_monitors() -> list[tuple[int, int, int, int]]:
    """Return Windows monitor bounds in logical desktop coordinates."""

    if sys.platform != "win32":
        raise RuntimeError("monitor enumeration is only supported on Windows")

    from ctypes import wintypes

    monitors: list[tuple[int, int, int, int]] = []

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    monitor_enum_proc = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    def _callback(_monitor: int, _hdc: int, rect_ptr: Any, _data: int) -> int:
        rect = rect_ptr.contents
        monitors.append((int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)))
        return 1

    callback = monitor_enum_proc(_callback)
    ctypes.windll.user32.EnumDisplayMonitors(0, 0, callback, 0)
    return monitors


def _resolve_capture_bbox(
    *,
    monitor_index: int | None,
    region: tuple[int, int, int, int] | None,
) -> tuple[int, int, int, int] | None:
    if region is not None:
        x, y, width, height = region
        return x, y, x + width, y + height
    if monitor_index is None:
        return None
    monitors = enumerate_display_monitors()
    if monitor_index < 0 or monitor_index >= len(monitors):
        raise ValueError(
            f"capture monitor index {monitor_index} is out of range for "
            f"{len(monitors)} monitor(s)."
        )
    return monitors[monitor_index]


def _dxcam_monitor_target(
    *,
    monitor_index: int | None,
    region: tuple[int, int, int, int] | None,
) -> tuple[int, tuple[int, int, int, int], tuple[int, int, int, int]]:
    monitors = enumerate_display_monitors()
    capture_bbox = _resolve_capture_bbox(monitor_index=monitor_index, region=region)
    if capture_bbox is None:
        raise RuntimeError("DXcam capture requires an explicit monitor or region.")

    if monitor_index is not None:
        if monitor_index < 0 or monitor_index >= len(monitors):
            raise ValueError(
                f"capture monitor index {monitor_index} is out of range for "
                f"{len(monitors)} monitor(s)."
            )
        monitor_bbox = monitors[monitor_index]
        monitor_left, monitor_top, monitor_right, monitor_bottom = monitor_bbox
        capture_left, capture_top, capture_right, capture_bottom = capture_bbox
        if not (
            capture_left >= monitor_left
            and capture_top >= monitor_top
            and capture_right <= monitor_right
            and capture_bottom <= monitor_bottom
        ):
            raise RuntimeError("capture target must fit inside the selected monitor.")
        return monitor_index, monitor_bbox, capture_bbox

    left, top, right, bottom = capture_bbox
    for output_index, monitor_bbox in enumerate(monitors):
        monitor_left, monitor_top, monitor_right, monitor_bottom = monitor_bbox
        if (
            left >= monitor_left
            and top >= monitor_top
            and right <= monitor_right
            and bottom <= monitor_bottom
        ):
            return output_index, monitor_bbox, capture_bbox
    raise RuntimeError("capture region must fit inside one monitor.")


def _get_dxcam_camera(*, output_index: int) -> Any:
    cache_key = (int(output_index), DXCAM_BACKEND)
    with _DXCAM_CAMERA_LOCK:
        camera = _DXCAM_CAMERA_CACHE.get(cache_key)
        if camera is not None:
            return camera
        try:
            import dxcam
        except Exception as exc:  # pragma: no cover - depends on Windows extra
            raise RuntimeError("DXcam is required for low-latency monitor capture.") from exc
        camera = dxcam.create(
            output_idx=int(output_index),
            output_color=DXCAM_OUTPUT_COLOR,
            processor_backend=DXCAM_PROCESSOR_BACKEND,
            backend=DXCAM_BACKEND,
            max_buffer_len=1,
        )
        if camera is None:
            raise RuntimeError(
                f"DXcam could not create a capture device for monitor {output_index}."
            )
        _DXCAM_CAMERA_CACHE[cache_key] = camera
        return camera


def _capture_with_dxcam(
    *,
    monitor_index: int | None,
    region: tuple[int, int, int, int] | None,
) -> tuple[Any, dict[str, Any]]:
    try:
        import numpy as np
        from PIL import Image
    except Exception as exc:  # pragma: no cover - depends on Windows extra
        raise RuntimeError("The ATM10 Windows extra is required for DXcam capture.") from exc

    output_index, monitor_bbox, capture_bbox = _dxcam_monitor_target(
        monitor_index=monitor_index,
        region=region,
    )
    monitor_left, monitor_top, monitor_right, monitor_bottom = monitor_bbox
    logical_monitor_width = int(monitor_right - monitor_left)
    logical_monitor_height = int(monitor_bottom - monitor_top)
    if logical_monitor_width <= 0 or logical_monitor_height <= 0:
        raise RuntimeError("capture monitor has invalid logical bounds.")

    camera = _get_dxcam_camera(output_index=output_index)
    native_width = int(getattr(camera, "width", 0) or 0)
    native_height = int(getattr(camera, "height", 0) or 0)
    if native_width <= 0 or native_height <= 0:
        raise RuntimeError("DXcam reported invalid native monitor dimensions.")

    native_region: tuple[int, int, int, int] | None = None
    expected_width = logical_monitor_width
    expected_height = logical_monitor_height
    if region is not None:
        capture_left, capture_top, capture_right, capture_bottom = capture_bbox
        scale_x = native_width / float(logical_monitor_width)
        scale_y = native_height / float(logical_monitor_height)
        native_left = max(
            0,
            min(native_width, int(np.floor((capture_left - monitor_left) * scale_x))),
        )
        native_top = max(
            0,
            min(native_height, int(np.floor((capture_top - monitor_top) * scale_y))),
        )
        native_right = max(
            native_left + 1,
            min(native_width, int(np.ceil((capture_right - monitor_left) * scale_x))),
        )
        native_bottom = max(
            native_top + 1,
            min(native_height, int(np.ceil((capture_bottom - monitor_top) * scale_y))),
        )
        native_region = (native_left, native_top, native_right, native_bottom)
        expected_width = int(capture_right - capture_left)
        expected_height = int(capture_bottom - capture_top)

    frame = camera.grab(region=native_region, new_frame_only=False)
    if frame is None:
        raise RuntimeError("DXcam returned no frame.")
    if getattr(frame, "ndim", 0) != 3 or int(frame.shape[2]) < 3:
        raise RuntimeError("DXcam returned an unexpected frame shape.")

    rgb_frame = np.ascontiguousarray(frame[:, :, [2, 1, 0]])
    image = Image.fromarray(rgb_frame, mode="RGB")
    return image, {
        "capture_mode": "region" if region is not None else "monitor",
        "capture_backend": f"dxcam_{DXCAM_BACKEND}",
        "monitor_index": monitor_index,
        "resolved_monitor_index": int(output_index),
        "region": _format_region(region),
        "bbox": list(capture_bbox),
        "expected_width": int(expected_width),
        "expected_height": int(expected_height),
        "native_region": list(native_region) if native_region is not None else None,
        "native_width": native_width,
        "native_height": native_height,
    }


def _capture_with_pillow(
    *,
    monitor_index: int | None,
    region: tuple[int, int, int, int] | None,
    window_handle: int | None,
    window_title: str | None,
    window_bounds: Mapping[str, Any] | Sequence[int] | None,
) -> tuple[Any, dict[str, Any]]:
    try:
        from PIL import ImageGrab
    except Exception as exc:  # pragma: no cover - depends on Windows extra
        raise RuntimeError("Pillow ImageGrab is required for screen capture.") from exc

    normalized_window_bounds = _normalize_window_bounds(window_bounds)
    if window_handle is not None and region is None:
        bbox = tuple(normalized_window_bounds) if normalized_window_bounds is not None else None
        image = ImageGrab.grab(window=int(window_handle))
        return image, {
            "capture_mode": "window",
            "capture_backend": "pillow_imagegrab_window",
            "monitor_index": monitor_index,
            "resolved_monitor_index": monitor_index,
            "region": _format_region(region),
            "bbox": list(bbox) if bbox is not None else None,
            "window_handle": int(window_handle),
            "window_title": str(window_title).strip() if window_title is not None else None,
            "window_bounds": normalized_window_bounds,
        }

    bbox = _resolve_capture_bbox(monitor_index=monitor_index, region=region)
    image = ImageGrab.grab(bbox=bbox, all_screens=True)
    return image, {
        "capture_mode": (
            "region" if region is not None else ("monitor" if monitor_index is not None else "desktop")
        ),
        "capture_backend": "pillow_imagegrab_desktop",
        "monitor_index": monitor_index,
        "resolved_monitor_index": monitor_index,
        "region": _format_region(region),
        "bbox": list(bbox) if bbox is not None else None,
        "window_handle": None,
        "window_title": None,
        "window_bounds": None,
    }


def capture_screen_image(
    *,
    output_path: Path,
    monitor_index: int | None = None,
    region: tuple[int, int, int, int] | None = None,
    window_handle: int | None = None,
    window_title: str | None = None,
    window_bounds: Mapping[str, Any] | Sequence[int] | None = None,
) -> dict[str, Any]:
    """Capture one image and return the selected backend plus fallback evidence."""

    if sys.platform != "win32":
        raise RuntimeError("live screen capture is currently implemented for Windows only.")
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - depends on Windows extra
        raise RuntimeError("Pillow is required for screen capture.") from exc

    normalized_window_bounds = _normalize_window_bounds(window_bounds)
    use_window_capture = window_handle is not None and region is None
    backend_errors: list[dict[str, str]] = []

    if use_window_capture:
        image, payload = _capture_with_pillow(
            monitor_index=monitor_index,
            region=region,
            window_handle=window_handle,
            window_title=window_title,
            window_bounds=window_bounds,
        )
    elif monitor_index is not None or region is not None:
        try:
            image, payload = _capture_with_dxcam(
                monitor_index=monitor_index,
                region=region,
            )
        except Exception as exc:
            backend_errors.append(
                {"backend": f"dxcam_{DXCAM_BACKEND}", "error": str(exc)}
            )
            image, payload = _capture_with_pillow(
                monitor_index=monitor_index,
                region=region,
                window_handle=None,
                window_title=None,
                window_bounds=None,
            )
    else:
        image, payload = _capture_with_pillow(
            monitor_index=None,
            region=None,
            window_handle=None,
            window_title=None,
            window_bounds=None,
        )

    raw_width = int(image.width)
    raw_height = int(image.height)
    resized_from: list[int] | None = None
    expected_width: int | None = None
    expected_height: int | None = None
    if use_window_capture and normalized_window_bounds is not None:
        expected_width = max(0, normalized_window_bounds[2] - normalized_window_bounds[0])
        expected_height = max(0, normalized_window_bounds[3] - normalized_window_bounds[1])
    elif payload.get("expected_width") is not None and payload.get("expected_height") is not None:
        expected_width = max(0, int(payload["expected_width"]))
        expected_height = max(0, int(payload["expected_height"]))

    if (
        expected_width
        and expected_height
        and (raw_width != expected_width or raw_height != expected_height)
    ):
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize((expected_width, expected_height), resampling)
        resized_from = [raw_width, raw_height]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    response_payload = {
        **payload,
        "width": int(image.width),
        "height": int(image.height),
        "raw_width": raw_width,
        "raw_height": raw_height,
        "resized_from": resized_from,
        "screenshot_path": str(output_path),
    }
    response_payload.pop("expected_width", None)
    response_payload.pop("expected_height", None)
    if backend_errors:
        response_payload["backend_errors"] = backend_errors
    return response_payload
