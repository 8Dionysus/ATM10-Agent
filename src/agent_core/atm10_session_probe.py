from __future__ import annotations

import ctypes
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ATM10_SESSION_PROBE_SCHEMA = "atm10_session_probe_v1"
_ATM10_HEURISTIC_THRESHOLD = 4
_SESSION_PROBE_BACKENDS = ("windows_win32", "linux_manual", "unsupported")


def list_session_probe_backend_ids() -> tuple[str, ...]:
    return _SESSION_PROBE_BACKENDS


def _utc_now(now: datetime | None = None) -> str:
    effective_now = now or datetime.now(timezone.utc)
    return effective_now.astimezone(timezone.utc).isoformat()


def _platform_name(platform_name: str | None = None) -> str:
    return str(platform_name or sys.platform).strip().lower()


def select_session_probe_backend_id(
    *,
    platform_name: str | None = None,
    backend_name: str | None = None,
) -> str:
    explicit_backend = str(backend_name or "").strip().lower()
    if explicit_backend:
        if explicit_backend not in _SESSION_PROBE_BACKENDS:
            available = ", ".join(_SESSION_PROBE_BACKENDS)
            raise KeyError(f"unknown session_probe_backend={explicit_backend!r}; expected one of: {available}")
        return explicit_backend

    platform = _platform_name(platform_name)
    if platform == "win32":
        return "windows_win32"
    if platform.startswith("linux"):
        return "linux_manual"
    return "unsupported"


def _normalize_capture_bbox(value: Sequence[int] | None) -> list[int] | None:
    if value is None:
        return None
    if len(value) != 4:
        return None
    try:
        return [int(item) for item in value]
    except Exception:
        return None


def _window_bounds_payload(bounds: Sequence[int] | None) -> dict[str, int] | None:
    normalized = _normalize_capture_bbox(bounds)
    if normalized is None:
        return None
    left, top, right, bottom = normalized
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
    }


def _bbox_intersects(bounds_a: Sequence[int] | None, bounds_b: Sequence[int] | None) -> bool | None:
    normalized_a = _normalize_capture_bbox(bounds_a)
    normalized_b = _normalize_capture_bbox(bounds_b)
    if normalized_a is None or normalized_b is None:
        return None
    left_a, top_a, right_a, bottom_a = normalized_a
    left_b, top_b, right_b, bottom_b = normalized_b
    return not (
        right_a <= left_b
        or right_b <= left_a
        or bottom_a <= top_b
        or bottom_b <= top_a
    )


def _capture_target_kind(capture_target_kind: str | None) -> str:
    normalized = str(capture_target_kind or "").strip().lower()
    if normalized in {"monitor", "region", "desktop", "window"}:
        return normalized
    return "unknown"


def _atm10_heuristic_score(*, window_title: str, process_name: str) -> int:
    title = window_title.strip().lower()
    process = process_name.strip().lower()
    score = 0
    if "atm10" in title or "atm 10" in title or "all the mods 10" in title:
        score += 4
    elif "all the mods" in title:
        score += 4
    if "minecraft" in title:
        score += 3
    if any(token in process for token in ("minecraft", "prismlauncher", "multimc", "curseforge")):
        score += 2
    if process in {"java.exe", "javaw.exe"} or "javaw" in process or process.endswith("\\java.exe"):
        score += 1
    return score


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(candidate.get("heuristic_score", 0)),
        1 if candidate.get("foreground") else 0,
        len(str(candidate.get("window_title", ""))),
    )


def _build_probe_payload(
    *,
    checked_at_utc: str,
    capture_target_kind: str,
    capture_bbox: Sequence[int] | None,
    candidate: dict[str, Any] | None,
    reason_codes: list[str],
    status: str,
    atm10_probable: bool,
    capture_intersects_window: bool | None,
) -> dict[str, Any]:
    return {
        "schema_version": ATM10_SESSION_PROBE_SCHEMA,
        "checked_at_utc": checked_at_utc,
        "status": status,
        "window_found": candidate is not None,
        "process_name": None if candidate is None else candidate.get("process_name"),
        "window_title": None if candidate is None else candidate.get("window_title"),
        "foreground": bool(candidate.get("foreground")) if candidate is not None else False,
        "window_bounds": None if candidate is None else _window_bounds_payload(candidate.get("window_bounds")),
        "capture_target_kind": capture_target_kind,
        "capture_bbox": _normalize_capture_bbox(capture_bbox),
        "capture_intersects_window": capture_intersects_window,
        "atm10_probable": bool(atm10_probable),
        "reason_codes": list(reason_codes),
    }


def _foreground_window_handle() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _resolve_process_name(pid: int) -> str:
    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return ""
    try:
        buffer_size = ctypes.c_ulong(260)
        buffer = ctypes.create_unicode_buffer(buffer_size.value)
        query_ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(
            handle,
            0,
            buffer,
            ctypes.byref(buffer_size),
        )
        if not query_ok:
            return ""
        return Path(buffer.value).name
    except Exception:
        return ""
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _enumerate_visible_windows(*, platform_name: str | None = None) -> list[dict[str, Any]]:
    if _platform_name(platform_name) != "win32":
        return []
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    user32 = ctypes.windll.user32
    windows: list[dict[str, Any]] = []
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd: int, _lparam: int) -> int:
        if not bool(user32.IsWindowVisible(hwnd)):
            return 1
        if bool(user32.IsIconic(hwnd)):
            return 1
        title_length = int(user32.GetWindowTextLengthW(hwnd))
        if title_length <= 0:
            return 1
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)
        window_title = title_buffer.value.strip()
        if not window_title:
            return 1
        rect = RECT()
        if not bool(user32.GetWindowRect(hwnd, ctypes.byref(rect))):
            return 1
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = _resolve_process_name(int(pid.value))
        windows.append(
            {
                "hwnd": int(hwnd),
                "window_title": window_title,
                "process_name": process_name,
                "window_bounds": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)],
            }
        )
        return 1

    user32.EnumWindows(enum_proc(_callback), 0)
    return windows


def find_best_atm10_window(*, platform_name: str | None = None) -> dict[str, Any] | None:
    if _platform_name(platform_name) != "win32":
        return None
    foreground_hwnd = _foreground_window_handle()
    candidates: list[dict[str, Any]] = []
    for window in _enumerate_visible_windows(platform_name=platform_name):
        candidate = dict(window)
        candidate["foreground"] = int(candidate.get("hwnd", 0)) == foreground_hwnd
        candidate["heuristic_score"] = _atm10_heuristic_score(
            window_title=str(candidate.get("window_title", "")),
            process_name=str(candidate.get("process_name", "")),
        )
        if int(candidate["heuristic_score"]) >= _ATM10_HEURISTIC_THRESHOLD:
            candidates.append(candidate)
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_sort_key, reverse=True)[0]


def _probe_windows_win32(
    *,
    checked_at_utc: str,
    capture_target_kind: str,
    capture_bbox: Sequence[int] | None,
    platform_name: str | None,
) -> dict[str, Any]:
    best_candidate = find_best_atm10_window(platform_name=platform_name)
    if best_candidate is None:
        return _build_probe_payload(
            checked_at_utc=checked_at_utc,
            capture_target_kind=capture_target_kind,
            capture_bbox=capture_bbox,
            candidate=None,
            reason_codes=["atm10_window_not_found"],
            status="attention",
            atm10_probable=False,
            capture_intersects_window=None,
        )

    capture_intersects_window = _bbox_intersects(
        best_candidate.get("window_bounds"),
        capture_bbox,
    )
    reason_codes: list[str] = []
    atm10_probable = True
    status = "ok"
    if capture_intersects_window is False:
        reason_codes.append("capture_target_miss")
        atm10_probable = False
        status = "attention"
    if not bool(best_candidate.get("foreground")):
        reason_codes.append("atm10_window_not_foreground")
        status = "attention"

    return _build_probe_payload(
        checked_at_utc=checked_at_utc,
        capture_target_kind=capture_target_kind,
        capture_bbox=capture_bbox,
        candidate=best_candidate,
        reason_codes=reason_codes,
        status=status,
        atm10_probable=atm10_probable,
        capture_intersects_window=capture_intersects_window,
    )


def _probe_linux_manual(
    *,
    checked_at_utc: str,
    capture_target_kind: str,
    capture_bbox: Sequence[int] | None,
) -> dict[str, Any]:
    reason_codes = ["window_identity_unavailable", "manual_capture_source_required"]
    if capture_target_kind == "unknown":
        reason_codes.append("capture_target_kind_unknown")

    return _build_probe_payload(
        checked_at_utc=checked_at_utc,
        capture_target_kind=capture_target_kind,
        capture_bbox=capture_bbox,
        candidate=None,
        reason_codes=reason_codes,
        status="attention",
        atm10_probable=False,
        capture_intersects_window=None,
    )


def _probe_unsupported(
    *,
    checked_at_utc: str,
    capture_target_kind: str,
    capture_bbox: Sequence[int] | None,
) -> dict[str, Any]:
    return _build_probe_payload(
        checked_at_utc=checked_at_utc,
        capture_target_kind=capture_target_kind,
        capture_bbox=capture_bbox,
        candidate=None,
        reason_codes=["platform_not_supported"],
        status="error",
        atm10_probable=False,
        capture_intersects_window=None,
    )


def probe_atm10_session(
    *,
    capture_target_kind: str,
    capture_bbox: Sequence[int] | None = None,
    now: datetime | None = None,
    platform_name: str | None = None,
    backend_name: str | None = None,
) -> dict[str, Any]:
    checked_at_utc = _utc_now(now)
    normalized_capture_target_kind = _capture_target_kind(capture_target_kind)
    normalized_capture_bbox = _normalize_capture_bbox(capture_bbox)
    backend_id = select_session_probe_backend_id(
        platform_name=platform_name,
        backend_name=backend_name,
    )

    if backend_id == "windows_win32":
        return _probe_windows_win32(
            checked_at_utc=checked_at_utc,
            capture_target_kind=normalized_capture_target_kind,
            capture_bbox=normalized_capture_bbox,
            platform_name=platform_name,
        )
    if backend_id == "linux_manual":
        return _probe_linux_manual(
            checked_at_utc=checked_at_utc,
            capture_target_kind=normalized_capture_target_kind,
            capture_bbox=normalized_capture_bbox,
        )
    return _probe_unsupported(
        checked_at_utc=checked_at_utc,
        capture_target_kind=normalized_capture_target_kind,
        capture_bbox=normalized_capture_bbox,
    )
