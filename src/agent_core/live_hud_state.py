from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

LIVE_HUD_STATE_SCHEMA = "live_hud_state_v1"


def _utc_now(now: datetime | None = None) -> str:
    effective_now = now or datetime.now(timezone.utc)
    return effective_now.astimezone(timezone.utc).isoformat()


def _build_source_entry(
    *,
    status: str,
    path: Path | None = None,
    detail: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "path": None if path is None else str(path),
        "detail": detail,
    }
    if isinstance(extra, Mapping):
        payload.update(dict(extra))
    return payload


def _dedupe_strings(values: list[str]) -> list[str]:
    observed: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        normalized = text.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        observed.append(text)
    return observed


def run_tesseract_ocr(
    *,
    image_path: Path,
    lang: str = "eng",
    psm: int = 6,
    oem: int = 1,
    timeout_sec: float = 20.0,
    tesseract_bin: str = "tesseract",
) -> str:
    if psm < 0:
        raise ValueError("psm must be >= 0.")
    if oem < 0:
        raise ValueError("oem must be >= 0.")

    resolved_tesseract = shutil.which(tesseract_bin)
    if not resolved_tesseract:
        raise RuntimeError(
            f"Tesseract binary is not available: {tesseract_bin!r}. "
            "Install Tesseract OCR and ensure it is in PATH."
        )

    command = [
        resolved_tesseract,
        str(image_path),
        "stdout",
        "--psm",
        str(psm),
        "--oem",
        str(oem),
        "-l",
        lang,
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise RuntimeError(f"Tesseract OCR failed with exit code {completed.returncode}: {stderr}")
    return completed.stdout


def load_hook_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Hook payload path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Hook payload path must be a file: {path}")

    raw_text = path.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise ValueError(f"Hook payload file is empty: {path}")

    parsed = json.loads(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError(f"Hook payload must be JSON object: {path}")
    return parsed


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for text in (str(item).strip() for item in value) if text]


def _normalize_quest_updates(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, Mapping):
            update_id = str(item.get("id", "")).strip()
            text = str(item.get("text", "")).strip()
            status = str(item.get("status", "")).strip()
        else:
            update_id = ""
            text = str(item).strip()
            status = ""
        if not update_id and not text and not status:
            continue
        normalized.append(
            {
                "id": update_id,
                "text": text,
                "status": status,
            }
        )
    return normalized


def _normalize_player_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, Any] = {}
    for key in ("dimension", "biome", "x", "y", "z", "health", "armor", "hunger"):
        if key in value:
            normalized[key] = value[key]
    return normalized


def normalize_hook_payload(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    event_ts = str(raw_payload.get("event_ts", "")).strip()
    source = str(raw_payload.get("source", "mod_hook")).strip() or "mod_hook"
    hud_lines = _normalize_string_list(raw_payload.get("hud_lines"))
    context_tags = _normalize_string_list(raw_payload.get("context_tags"))
    quest_updates = _normalize_quest_updates(raw_payload.get("quest_updates"))
    player_state = _normalize_player_state(raw_payload.get("player_state"))

    if not hud_lines and not quest_updates and not player_state:
        raise ValueError("Hook payload has no usable content (hud_lines/quest_updates/player_state).")

    return {
        "event_ts": event_ts or _utc_now(),
        "source": source,
        "hud_lines": hud_lines,
        "hud_text": "\n".join(hud_lines),
        "quest_updates": quest_updates,
        "player_state": player_state,
        "context_tags": context_tags,
    }


def build_live_hud_state(
    *,
    screenshot_path: Path,
    hook_json: Path | None = None,
    tesseract_bin: str = "tesseract",
    lang: str = "eng",
    psm: int = 6,
    oem: int = 1,
    timeout_sec: float = 20.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at_utc = _utc_now(now)
    reason_codes: list[str] = []
    sources: dict[str, Any] = {}

    screenshot_ok = screenshot_path.exists() and screenshot_path.is_file()
    if screenshot_ok:
        sources["screenshot"] = _build_source_entry(status="ok", path=screenshot_path)
    else:
        reason_codes.append("screenshot_missing")
        sources["screenshot"] = _build_source_entry(
            status="error",
            path=screenshot_path,
            detail="Screenshot artifact is missing.",
        )

    hook_payload: dict[str, Any] | None = None
    if hook_json is None:
        reason_codes.append("mod_hook_not_configured")
        sources["mod_hook"] = _build_source_entry(status="not_configured")
    else:
        try:
            hook_payload = normalize_hook_payload(load_hook_payload(hook_json))
            sources["mod_hook"] = _build_source_entry(
                status="ok",
                path=hook_json,
                extra={
                    "source": hook_payload.get("source"),
                    "event_ts": hook_payload.get("event_ts"),
                    "hud_line_count": len(hook_payload.get("hud_lines", [])),
                },
            )
        except FileNotFoundError as exc:
            reason_codes.append("mod_hook_missing")
            sources["mod_hook"] = _build_source_entry(
                status="missing",
                path=hook_json,
                detail=str(exc),
            )
        except (ValueError, json.JSONDecodeError) as exc:
            reason_codes.append("mod_hook_invalid")
            sources["mod_hook"] = _build_source_entry(
                status="invalid",
                path=hook_json,
                detail=str(exc),
            )
        except Exception as exc:
            reason_codes.append("mod_hook_failed")
            sources["mod_hook"] = _build_source_entry(
                status="error",
                path=hook_json,
                detail=str(exc),
            )

    ocr_lines: list[str] = []
    ocr_text = ""
    if screenshot_ok:
        try:
            ocr_text = run_tesseract_ocr(
                image_path=screenshot_path,
                lang=lang,
                psm=psm,
                oem=oem,
                timeout_sec=timeout_sec,
                tesseract_bin=tesseract_bin,
            )
            ocr_lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
            if ocr_lines:
                sources["ocr"] = _build_source_entry(
                    status="ok",
                    path=screenshot_path,
                    extra={"line_count": len(ocr_lines)},
                )
            else:
                reason_codes.append("ocr_no_text")
                sources["ocr"] = _build_source_entry(
                    status="empty",
                    path=screenshot_path,
                    detail="OCR completed without non-empty lines.",
                    extra={"line_count": 0},
                )
        except RuntimeError as exc:
            detail = str(exc)
            if "Tesseract binary is not available" in detail:
                reason_codes.append("ocr_unavailable")
                status = "unavailable"
            else:
                reason_codes.append("ocr_failed")
                status = "error"
            sources["ocr"] = _build_source_entry(
                status=status,
                path=screenshot_path,
                detail=detail,
            )
        except Exception as exc:
            reason_codes.append("ocr_failed")
            sources["ocr"] = _build_source_entry(
                status="error",
                path=screenshot_path,
                detail=str(exc),
            )
    else:
        sources["ocr"] = _build_source_entry(
            status="not_started",
            path=screenshot_path,
            detail="OCR skipped because screenshot artifact is missing.",
        )

    hud_lines = _dedupe_strings(
        [
            *(
                list(hook_payload.get("hud_lines", []))
                if isinstance(hook_payload, Mapping)
                else []
            ),
            *ocr_lines,
        ]
    )
    quest_updates = (
        list(hook_payload.get("quest_updates", []))
        if isinstance(hook_payload, Mapping)
        else []
    )
    player_state = (
        dict(hook_payload.get("player_state", {}))
        if isinstance(hook_payload, Mapping)
        else {}
    )
    context_tags = _dedupe_strings(
        list(hook_payload.get("context_tags", []))
        if isinstance(hook_payload, Mapping)
        else []
    )
    text_preview = ""
    if hud_lines:
        text_preview = " ".join(hud_lines[:3])[:240]
    elif ocr_text.strip():
        text_preview = " ".join(ocr_text.split())[:240]

    status = "error"
    if screenshot_ok and (
        str(sources["ocr"].get("status")) in {"ok", "empty", "unavailable"}
        or str(sources["mod_hook"].get("status")) in {"ok", "not_configured", "missing", "invalid"}
    ):
        status = "ok" if hud_lines or quest_updates or player_state else "partial"

    return {
        "schema_version": LIVE_HUD_STATE_SCHEMA,
        "checked_at_utc": checked_at_utc,
        "status": status,
        "screenshot_path": str(screenshot_path),
        "sources": sources,
        "hud_lines": hud_lines,
        "quest_updates": quest_updates,
        "player_state": player_state,
        "context_tags": context_tags,
        "text_preview": text_preview,
        "hud_line_count": len(hud_lines),
        "quest_update_count": len(quest_updates),
        "has_player_state": bool(player_state),
        "reason_codes": _dedupe_strings(reason_codes),
    }
