from __future__ import annotations

import copy
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

REDACTION_CHECKLIST_VERSION = "gateway_error_redaction_v1"
_REDACTED_VALUE = "[REDACTED]"

_SENSITIVE_KEY_MARKERS: tuple[str, ...] = (
    "password",
    "token",
    "secret",
    "apikey",
    "authorization",
    "cookie",
)

_SECRET_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(bearer\s+)([a-z0-9\-._~+/=]{8,})"),
    re.compile(
        r"(?i)\b((?:api[_-]?key|token|secret|password|authorization|cookie)\s*[:=]\s*)([^\s,;\"']+)"
    ),
    re.compile(
        r'(?i)("?(?:api[_-]?key|token|secret|password|authorization|cookie)"?\s*:\s*")([^"]+)(")'
    ),
)


def is_sensitive_key(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(name).lower())
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def redact_text_secrets(text: str) -> str:
    redacted = str(text)
    redacted = _SECRET_TEXT_PATTERNS[0].sub(r"\1" + _REDACTED_VALUE, redacted)
    redacted = _SECRET_TEXT_PATTERNS[1].sub(r"\1" + _REDACTED_VALUE, redacted)
    redacted = _SECRET_TEXT_PATTERNS[2].sub(r"\1" + _REDACTED_VALUE + r"\3", redacted)
    return redacted


def _redact_value(value: Any, *, path: str, fields_redacted: set[str]) -> Any:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, nested in value.items():
            key_text = str(key)
            key_path = f"{path}.{key_text}" if path else key_text
            if is_sensitive_key(key_text):
                output[key_text] = _REDACTED_VALUE
                fields_redacted.add(key_path)
                continue
            output[key_text] = _redact_value(nested, path=key_path, fields_redacted=fields_redacted)
        return output

    if isinstance(value, list):
        output_list: list[Any] = []
        for index, nested in enumerate(value):
            index_path = f"{path}[{index}]"
            output_list.append(_redact_value(nested, path=index_path, fields_redacted=fields_redacted))
        return output_list

    if isinstance(value, str):
        redacted_text = redact_text_secrets(value)
        if redacted_text != value:
            fields_redacted.add(path or "root")
        return redacted_text

    return value


def redact_payload(
    payload: Mapping[str, Any],
    *,
    enable_redaction: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_payload = copy.deepcopy(dict(payload))
    fields_redacted: set[str] = set()

    if enable_redaction:
        redacted_payload = _redact_value(source_payload, path="", fields_redacted=fields_redacted)
        result_payload = dict(redacted_payload)
    else:
        result_payload = source_payload

    metadata = {
        "checklist_version": REDACTION_CHECKLIST_VERSION,
        "applied": bool(enable_redaction),
        "fields_redacted": sorted(fields_redacted),
    }
    return result_payload, metadata


def redact_error_entry(payload: Mapping[str, Any], enable_redaction: bool = True) -> dict[str, Any]:
    result_payload, metadata = redact_payload(payload, enable_redaction=enable_redaction)
    result_payload["redaction"] = metadata
    return result_payload


def _rotated_jsonl_path(path: Path, index: int) -> Path:
    return path.with_name(f"{path.stem}.{index}{path.suffix}")


def rotate_jsonl(path: Path, max_bytes: int, max_files: int) -> bool:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be > 0.")
    if max_files <= 0:
        raise ValueError("max_files must be > 0.")
    if not path.exists() or not path.is_file():
        return False
    if path.stat().st_size < max_bytes:
        return False

    rotated_slots = max_files - 1
    if rotated_slots <= 0:
        path.unlink(missing_ok=True)
        return True

    oldest = _rotated_jsonl_path(path, rotated_slots)
    if oldest.exists():
        oldest.unlink()

    for index in range(rotated_slots - 1, 0, -1):
        source = _rotated_jsonl_path(path, index)
        if not source.exists():
            continue
        destination = _rotated_jsonl_path(path, index + 1)
        if destination.exists():
            destination.unlink()
        source.rename(destination)

    first_rotated = _rotated_jsonl_path(path, 1)
    if first_rotated.exists():
        first_rotated.unlink()
    path.rename(first_rotated)
    return True


def _is_older_than_retention(path: Path, cutoff_utc: datetime) -> bool:
    modified_at_utc = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return modified_at_utc < cutoff_utc


def cleanup_old_gateway_artifacts(
    runs_dir: Path,
    retention_days: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    if retention_days < 0:
        raise ValueError("retention_days must be >= 0.")
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff_utc = now.astimezone(timezone.utc) - timedelta(days=retention_days)
    if not runs_dir.exists():
        return {
            "runs_dir": str(runs_dir),
            "retention_days": retention_days,
            "removed_files_count": 0,
            "removed_dirs_count": 0,
            "warnings": [],
        }

    removed_files: list[str] = []
    removed_dirs: list[str] = []
    warnings: list[str] = []

    for file_path in sorted(runs_dir.glob("gateway_http_errors*.jsonl")):
        try:
            if not file_path.is_file():
                continue
            if not _is_older_than_retention(file_path, cutoff_utc):
                continue
            file_path.unlink(missing_ok=True)
            removed_files.append(str(file_path))
        except OSError as exc:
            warnings.append(f"file_cleanup_failed:{file_path}:{exc}")

    for artifact_dir in sorted(runs_dir.glob("*-gateway-v1*")):
        try:
            if not artifact_dir.is_dir():
                continue
            if not _is_older_than_retention(artifact_dir, cutoff_utc):
                continue
            shutil.rmtree(artifact_dir)
            removed_dirs.append(str(artifact_dir))
        except OSError as exc:
            warnings.append(f"dir_cleanup_failed:{artifact_dir}:{exc}")

    return {
        "runs_dir": str(runs_dir),
        "retention_days": retention_days,
        "removed_files_count": len(removed_files),
        "removed_dirs_count": len(removed_dirs),
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
        "warnings": warnings,
    }
