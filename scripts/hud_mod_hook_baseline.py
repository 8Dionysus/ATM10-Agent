from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-hud-hook")
    run_dir = runs_dir / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    suffix = 1
    while True:
        candidate = runs_dir / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_hook_payload(path: Path) -> dict[str, Any]:
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
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


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


def _normalize_hook_payload(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    event_ts = str(raw_payload.get("event_ts", "")).strip()
    source = str(raw_payload.get("source", "mod_hook")).strip() or "mod_hook"
    hud_lines = _normalize_string_list(raw_payload.get("hud_lines"))
    context_tags = _normalize_string_list(raw_payload.get("context_tags"))
    quest_updates = _normalize_quest_updates(raw_payload.get("quest_updates"))
    player_state = _normalize_player_state(raw_payload.get("player_state"))

    if not hud_lines and not quest_updates and not player_state:
        raise ValueError("Hook payload has no usable content (hud_lines/quest_updates/player_state).")

    return {
        "event_ts": event_ts or datetime.now(timezone.utc).isoformat(),
        "source": source,
        "hud_lines": hud_lines,
        "hud_text": "\n".join(hud_lines),
        "quest_updates": quest_updates,
        "player_state": player_state,
        "context_tags": context_tags,
    }


def run_hud_mod_hook_baseline(
    *,
    hook_json: Path,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    hook_raw_path = run_dir / "hook_raw.json"
    hook_normalized_path = run_dir / "hook_normalized.json"
    hud_text_path = run_dir / "hud_text.txt"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "hud_mod_hook_baseline",
        "status": "started",
        "request": {
            "hook_json": str(hook_json),
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "hook_raw_json": str(hook_raw_path),
            "hook_normalized_json": str(hook_normalized_path),
            "hud_text_txt": str(hud_text_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        raw_payload = _load_hook_payload(hook_json)
        normalized_payload = _normalize_hook_payload(raw_payload)

        _write_json(hook_raw_path, raw_payload)
        _write_json(hook_normalized_path, normalized_payload)
        hud_text_path.write_text(str(normalized_payload["hud_text"]), encoding="utf-8")

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "source": normalized_payload["source"],
            "event_ts": normalized_payload["event_ts"],
            "hud_line_count": len(normalized_payload["hud_lines"]),
            "quest_update_count": len(normalized_payload["quest_updates"]),
            "has_player_state": bool(normalized_payload["player_state"]),
        }
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "hook_payload": normalized_payload,
            "ok": True,
        }
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, FileNotFoundError):
            run_payload["error_code"] = "input_path_missing"
        elif isinstance(exc, (ValueError, json.JSONDecodeError)):
            run_payload["error_code"] = "invalid_hook_payload"
        else:
            run_payload["error_code"] = "hud_mod_hook_failed"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "hook_payload": None,
            "ok": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HUD mod-hook baseline: ingest hook JSON and write normalized HUD artifacts."
    )
    parser.add_argument("--hook-json", type=Path, required=True, help="Path to hook payload JSON.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_hud_mod_hook_baseline(
        hook_json=args.hook_json,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[hud_mod_hook_baseline] run_dir: {run_dir}")
    print(f"[hud_mod_hook_baseline] run_json: {run_dir / 'run.json'}")
    print(f"[hud_mod_hook_baseline] hook_raw_json: {run_dir / 'hook_raw.json'}")
    print(f"[hud_mod_hook_baseline] hook_normalized_json: {run_dir / 'hook_normalized.json'}")
    print(f"[hud_mod_hook_baseline] hud_text_txt: {run_dir / 'hud_text.txt'}")
    if not result["ok"]:
        print(f"[hud_mod_hook_baseline] error: {result['run_payload']['error']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
