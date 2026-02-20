from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.discover_instance import resolve_atm10_dir, resolve_minecraft_dir
from src.rag.ftbquests_ingest import discover_quests_dir, ingest_ftbquests_dir


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S")
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
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Locate FTB Quests files and normalize quest docs into JSONL contract."
    )
    parser.add_argument(
        "--quests-dir",
        type=Path,
        default=None,
        help="Optional direct path to config/ftbquests/quests.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "ftbquests_norm" / "quests.jsonl",
        help="Output JSONL path (default: data/ftbquests_norm/quests.jsonl).",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base directory for run artifacts (default: runs).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)
    run_dir = _create_run_dir(args.runs_dir, now=now)
    errors_path = run_dir / "ingest_errors.jsonl"
    paths_artifact = run_dir / "ftbquests_paths.json"

    env_map = dict(os.environ)
    minecraft_dir, _ = resolve_minecraft_dir(env_map)
    atm10_dir, _ = resolve_atm10_dir(minecraft_dir, env_map)

    discovered = discover_quests_dir(
        minecraft_dir=minecraft_dir,
        atm10_dir=atm10_dir,
    )

    selected_quests_dir: Path | None
    if args.quests_dir is not None:
        selected_quests_dir = args.quests_dir
        discovered["selected"] = str(selected_quests_dir)
        discovered["found"] = selected_quests_dir.is_dir()
        if str(selected_quests_dir) not in discovered["candidates"]:
            discovered["candidates"] = [str(selected_quests_dir), *discovered["candidates"]]
    else:
        selected_raw = discovered["selected"]
        selected_quests_dir = Path(selected_raw) if selected_raw else None

    _write_json(
        paths_artifact,
        {
            "timestamp_utc": now.isoformat(),
            "minecraft_dir": str(minecraft_dir),
            "atm10_dir": str(atm10_dir) if atm10_dir else None,
            "quests_discovery": discovered,
        },
    )

    if selected_quests_dir is None or not selected_quests_dir.is_dir():
        errors_path.parent.mkdir(parents=True, exist_ok=True)
        errors_path.write_text(
            json.dumps(
                {
                    "error": "quests_dir_not_found",
                    "details": "No existing config/ftbquests/quests directory found.",
                    "candidates": discovered["candidates"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"[normalize_ftbquests] quests dir not found. artifact: {paths_artifact}")
        print(f"[normalize_ftbquests] errors: {errors_path}")
        return 2

    summary = ingest_ftbquests_dir(
        quests_dir=selected_quests_dir,
        output_jsonl=args.output,
        errors_jsonl=errors_path,
        now=now,
    )

    print(f"[normalize_ftbquests] run_dir: {run_dir}")
    print(f"[normalize_ftbquests] paths_artifact: {paths_artifact}")
    print(f"[normalize_ftbquests] output_jsonl: {summary['output_jsonl']}")
    print(f"[normalize_ftbquests] errors_jsonl: {summary['errors_jsonl']}")
    print(f"[normalize_ftbquests] docs_written={summary['docs_written']}, errors_logged={summary['errors_logged']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
