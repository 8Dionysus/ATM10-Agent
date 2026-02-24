from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


MARKERS = ("config", "mods", "logs", "saves")


def _env_path(env: Mapping[str, str], key: str) -> Path | None:
    value = env.get(key)
    if not value:
        return None
    return Path(value).expanduser()


def resolve_minecraft_dir(env: Mapping[str, str]) -> tuple[Path, str]:
    from_env = _env_path(env, "MINECRAFT_DIR")
    if from_env is not None:
        return from_env, "env"

    appdata = env.get("APPDATA")
    if appdata:
        return Path(appdata) / ".minecraft", "appdata_fallback"

    return Path.home() / "AppData" / "Roaming" / ".minecraft", "home_fallback"


def _is_atm10_candidate(path: Path) -> bool:
    name = path.name.lower()
    return "atm10" in name or "all the mods 10" in name


def _candidate_sort_key(path: Path) -> tuple[int, float, str]:
    name = path.name.lower()
    score = 0
    if "atm10" in name:
        score += 2
    if "all the mods 10" in name:
        score += 1
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0
    return score, modified, name


def resolve_atm10_dir(minecraft_dir: Path, env: Mapping[str, str]) -> tuple[Path | None, str]:
    from_env = _env_path(env, "ATM10_DIR")
    if from_env is not None:
        return from_env, "env"

    versions_dir = minecraft_dir / "versions"
    if not versions_dir.is_dir():
        return None, "not_found"

    candidates = [
        child for child in versions_dir.iterdir() if child.is_dir() and _is_atm10_candidate(child)
    ]
    if not candidates:
        return None, "not_found"

    selected = max(candidates, key=_candidate_sort_key)
    return selected, "versions_scan"


def collect_markers(atm10_dir: Path | None) -> dict[str, bool]:
    if atm10_dir is None:
        return {name: False for name in MARKERS}
    return {name: (atm10_dir / name).is_dir() for name in MARKERS}


def _to_str(path: Path | None) -> str | None:
    return str(path) if path is not None else None


def build_report(env: Mapping[str, str], now: datetime | None = None) -> dict[str, Any]:
    minecraft_dir, minecraft_source = resolve_minecraft_dir(env)
    atm10_dir, atm10_source = resolve_atm10_dir(minecraft_dir, env)

    if now is None:
        now = datetime.now(timezone.utc)

    return {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "inputs": {
            "MINECRAFT_DIR": env.get("MINECRAFT_DIR"),
            "ATM10_DIR": env.get("ATM10_DIR"),
            "APPDATA": env.get("APPDATA"),
        },
        "discovery_sources": {
            "minecraft_dir": minecraft_source,
            "atm10_dir": atm10_source,
        },
        "paths": {
            "minecraft_dir": _to_str(minecraft_dir),
            "versions_dir": _to_str(minecraft_dir / "versions"),
            "atm10_dir": _to_str(atm10_dir),
        },
        "exists": {
            "minecraft_dir": minecraft_dir.is_dir(),
            "atm10_dir": atm10_dir.is_dir() if atm10_dir else False,
        },
        "markers": collect_markers(atm10_dir),
    }


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


def run_discovery(
    *,
    env: Mapping[str, str] | None = None,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> tuple[dict[str, Any], Path]:
    env_map = dict(os.environ if env is None else env)
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)

    report = build_report(env_map, now=now)
    report_path = run_dir / "instance_paths.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report, report_path


def _print_summary(report: Mapping[str, Any], report_path: Path) -> None:
    print(f"[discover_instance] artifact: {report_path}")
    print(f"minecraft_dir: {report['paths']['minecraft_dir']} (exists={report['exists']['minecraft_dir']})")
    print(f"atm10_dir: {report['paths']['atm10_dir']} (exists={report['exists']['atm10_dir']})")
    marker_bits = ", ".join(f"{name}={value}" for name, value in report["markers"].items())
    print(f"markers: {marker_bits}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover Minecraft and ATM10 paths and write artifact to runs/<timestamp>/instance_paths.json."
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
    report, report_path = run_discovery(runs_dir=args.runs_dir)
    _print_summary(report, report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
