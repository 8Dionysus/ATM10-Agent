from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.rag.doc_contract import normalize_doc


def candidate_quests_dirs(*, minecraft_dir: Path | None, atm10_dir: Path | None) -> list[Path]:
    candidates: list[Path] = []
    for base in (atm10_dir, minecraft_dir):
        if base is None:
            continue
        candidates.append(base / "config" / "ftbquests" / "quests")
    return _dedupe_paths(candidates)


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def select_existing_quests_dir(candidates: Iterable[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def discover_quests_dir(*, minecraft_dir: Path | None, atm10_dir: Path | None) -> dict[str, Any]:
    candidates = candidate_quests_dirs(minecraft_dir=minecraft_dir, atm10_dir=atm10_dir)
    selected = select_existing_quests_dir(candidates)
    return {
        "candidates": [str(path) for path in candidates],
        "selected": str(selected) if selected else None,
        "found": selected is not None,
    }


def _extract_title(payload: Any, fallback: str) -> str:
    if isinstance(payload, Mapping):
        for key in ("title", "name"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return fallback


def _extract_text(payload: Any) -> str:
    if isinstance(payload, Mapping):
        for key in ("description", "text", "subtitle"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return json.dumps(payload, ensure_ascii=False)


def _error_record(file_path: Path, error: str, details: str) -> dict[str, str]:
    return {"file": str(file_path), "error": error, "details": details}


def _iter_files(quests_dir: Path) -> Iterable[Path]:
    for file_path in sorted(quests_dir.rglob("*")):
        if file_path.is_file():
            yield file_path


def ingest_ftbquests_dir(
    *,
    quests_dir: Path,
    output_jsonl: Path,
    errors_jsonl: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    docs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for file_path in _iter_files(quests_dir):
        if file_path.suffix.lower() != ".json":
            errors.append(_error_record(file_path, "unsupported_extension", file_path.suffix.lower()))
            continue

        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(_error_record(file_path, "parse_error", str(exc)))
            continue

        relative = file_path.relative_to(quests_dir)
        doc = normalize_doc(
            {
                "id": f"ftbquests:{relative.as_posix()}",
                "source": "ftbquests",
                "title": _extract_title(payload, fallback=file_path.stem),
                "text": _extract_text(payload),
                "tags": ["quest", "ftbquests"],
                "created_at": now.astimezone(timezone.utc).isoformat(),
            },
            now=now,
        )
        docs.append(doc)

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8", newline="\n") as handle:
        for doc in docs:
            handle.write(json.dumps(doc, ensure_ascii=False) + "\n")

    errors_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with errors_jsonl.open("w", encoding="utf-8", newline="\n") as handle:
        for error in errors:
            handle.write(json.dumps(error, ensure_ascii=False) + "\n")

    return {
        "quests_dir": str(quests_dir),
        "output_jsonl": str(output_jsonl),
        "errors_jsonl": str(errors_jsonl),
        "docs_written": len(docs),
        "errors_logged": len(errors),
    }

