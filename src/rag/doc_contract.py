from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

REQUIRED_FIELDS: tuple[str, ...] = ("id", "source", "title", "text", "tags", "created_at")


def _utc_iso(ts: datetime | None = None) -> str:
    if ts is None:
        ts = datetime.now(timezone.utc)
    return ts.astimezone(timezone.utc).isoformat()


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        tag = value.strip()
        return [tag] if tag else []
    if isinstance(value, Iterable):
        normalized: list[str] = []
        for item in value:
            tag = str(item).strip()
            if tag:
                normalized.append(tag)
        return normalized
    return []


def normalize_doc(record: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Normalize an arbitrary mapping into the project JSONL doc contract."""
    normalized = {
        "id": str(record.get("id", "")).strip(),
        "source": str(record.get("source", "")).strip(),
        "title": str(record.get("title", "")).strip(),
        "text": str(record.get("text", "")).strip(),
        "tags": _normalize_tags(record.get("tags")),
        "created_at": str(record.get("created_at") or _utc_iso(now)),
    }
    ensure_valid_doc(normalized)
    return normalized


def ensure_valid_doc(record: Mapping[str, Any]) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    for field in ("id", "source", "title", "text", "created_at"):
        value = record[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Field '{field}' must be a non-empty string.")

    tags = record["tags"]
    if not isinstance(tags, list) or any(not isinstance(item, str) for item in tags):
        raise ValueError("Field 'tags' must be a list of strings.")

    created_at = record["created_at"].replace("Z", "+00:00")
    try:
        datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise ValueError("Field 'created_at' must be ISO 8601.") from exc


def write_jsonl(records: Iterable[Mapping[str, Any]], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            normalized = normalize_doc(record)
            handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")
            count += 1
    return count

