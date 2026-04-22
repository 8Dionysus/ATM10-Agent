from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

MARKERS = ("config", "mods", "logs", "saves")


def _env_path(env: Mapping[str, str], key: str) -> Path | None:
    value = env.get(key)
    if not value:
        return None
    return Path(value).expanduser()


def _runtime_platform(platform_name: str | None = None) -> str:
    return (platform_name or sys.platform).lower()


def _home_path(env: Mapping[str, str], home: Path | None = None) -> Path:
    if home is not None:
        return home
    from_env = env.get("HOME") or env.get("USERPROFILE")
    if from_env:
        return Path(from_env).expanduser()
    return Path.home()


def _xdg_data_home(env: Mapping[str, str], home: Path) -> Path:
    from_env = env.get("XDG_DATA_HOME")
    if from_env:
        return Path(from_env).expanduser()
    return home / ".local" / "share"


def _dedupe_roots(roots: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
    seen: set[str] = set()
    result: list[tuple[Path, str]] = []
    for path, source in roots:
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        result.append((path.expanduser(), source))
    return result


def resolve_minecraft_dir(
    env: Mapping[str, str],
    *,
    platform_name: str | None = None,
    home: Path | None = None,
) -> tuple[Path, str]:
    """Resolve the base Minecraft directory with env-first, OS-aware fallbacks."""

    from_env = _env_path(env, "MINECRAFT_DIR")
    if from_env is not None:
        return from_env, "env"

    platform = _runtime_platform(platform_name)
    home_path = _home_path(env, home=home)

    if platform.startswith("win"):
        appdata = env.get("APPDATA")
        if appdata:
            return Path(appdata) / ".minecraft", "appdata_fallback"
        return home_path / "AppData" / "Roaming" / ".minecraft", "home_fallback"

    if platform == "darwin":
        return home_path / "Library" / "Application Support" / "minecraft", "macos_home_fallback"

    return home_path / ".minecraft", "linux_home_fallback"


def candidate_instance_roots(
    minecraft_dir: Path,
    env: Mapping[str, str],
    *,
    platform_name: str | None = None,
    home: Path | None = None,
) -> list[tuple[Path, str]]:
    """Return ordered roots to scan for ATM10 instances.

    The order is intentionally env/base-Minecraft first, then launcher-specific
    comfort fallbacks. This keeps explicit operator configuration stronger than
    launcher heuristics.
    """

    platform = _runtime_platform(platform_name)
    home_path = _home_path(env, home=home)
    roots: list[tuple[Path, str]] = [
        (minecraft_dir / "versions", "versions_scan"),
        (minecraft_dir / "instances", "minecraft_instances_scan"),
    ]

    if platform.startswith("linux"):
        xdg_home = _xdg_data_home(env, home_path)
        roots.extend(
            [
                (xdg_home / "PrismLauncher" / "instances", "xdg_prismlauncher_instances_scan"),
                (xdg_home / "PolyMC" / "instances", "xdg_polymc_instances_scan"),
                (xdg_home / "com.modrinth.theseus" / "profiles", "xdg_modrinth_profiles_scan"),
                (
                    home_path / ".var" / "app" / "org.prismlauncher.PrismLauncher" / "data" / "PrismLauncher" / "instances",
                    "flatpak_prismlauncher_instances_scan",
                ),
                (
                    home_path / ".var" / "app" / "com.modrinth.ModrinthApp" / "data" / "com.modrinth.theseus" / "profiles",
                    "flatpak_modrinth_profiles_scan",
                ),
                (home_path / "curseforge" / "minecraft" / "Instances", "home_curseforge_instances_scan"),
                (home_path / "Games" / "CurseForge" / "Instances", "home_games_curseforge_instances_scan"),
            ]
        )
    elif platform.startswith("win"):
        appdata = env.get("APPDATA")
        localappdata = env.get("LOCALAPPDATA")
        if appdata:
            roots.append((Path(appdata) / "CurseForge" / "minecraft" / "Instances", "appdata_curseforge_instances_scan"))
        if localappdata:
            roots.append((Path(localappdata) / "Programs" / "CurseForge" / "minecraft" / "Instances", "localappdata_curseforge_instances_scan"))
    elif platform == "darwin":
        roots.extend(
            [
                (home_path / "Library" / "Application Support" / "PrismLauncher" / "instances", "macos_prismlauncher_instances_scan"),
                (home_path / "Library" / "Application Support" / "com.modrinth.theseus" / "profiles", "macos_modrinth_profiles_scan"),
            ]
        )

    return _dedupe_roots(roots)


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


def _scan_atm10_candidates(roots: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    for root, source in roots:
        if not root.is_dir():
            continue
        if _is_atm10_candidate(root):
            candidates.append((root, source))
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and _is_atm10_candidate(child):
                candidates.append((child, source))
    return candidates


def resolve_atm10_dir(
    minecraft_dir: Path,
    env: Mapping[str, str],
    *,
    platform_name: str | None = None,
    home: Path | None = None,
) -> tuple[Path | None, str]:
    from_env = _env_path(env, "ATM10_DIR")
    if from_env is not None:
        return from_env, "env"

    roots = candidate_instance_roots(
        minecraft_dir,
        env,
        platform_name=platform_name,
        home=home,
    )
    candidates = _scan_atm10_candidates(roots)
    if not candidates:
        return None, "not_found"

    selected, source = max(candidates, key=lambda item: _candidate_sort_key(item[0]))
    return selected, source


def collect_markers(atm10_dir: Path | None) -> dict[str, bool]:
    if atm10_dir is None:
        return {name: False for name in MARKERS}
    return {name: (atm10_dir / name).is_dir() for name in MARKERS}


def _to_str(path: Path | None) -> str | None:
    return str(path) if path is not None else None


def build_report(
    env: Mapping[str, str],
    now: datetime | None = None,
    *,
    platform_name: str | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    platform = _runtime_platform(platform_name)
    home_path = _home_path(env, home=home)
    minecraft_dir, minecraft_source = resolve_minecraft_dir(
        env,
        platform_name=platform,
        home=home_path,
    )
    candidate_roots = candidate_instance_roots(
        minecraft_dir,
        env,
        platform_name=platform,
        home=home_path,
    )
    atm10_dir, atm10_source = resolve_atm10_dir(
        minecraft_dir,
        env,
        platform_name=platform,
        home=home_path,
    )
    if now is None:
        now = datetime.now(timezone.utc)

    return {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "inputs": {
            "platform": platform,
            "MINECRAFT_DIR": env.get("MINECRAFT_DIR"),
            "ATM10_DIR": env.get("ATM10_DIR"),
            "APPDATA": env.get("APPDATA"),
            "LOCALAPPDATA": env.get("LOCALAPPDATA"),
            "HOME": env.get("HOME"),
            "USERPROFILE": env.get("USERPROFILE"),
            "XDG_DATA_HOME": env.get("XDG_DATA_HOME"),
        },
        "discovery_sources": {
            "minecraft_dir": minecraft_source,
            "atm10_dir": atm10_source,
        },
        "paths": {
            "minecraft_dir": _to_str(minecraft_dir),
            "versions_dir": _to_str(minecraft_dir / "versions"),
            "candidate_instance_roots": [
                {"path": _to_str(path), "source": source}
                for path, source in candidate_roots
            ],
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
    platform_name: str | None = None,
    home: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    env_map = dict(os.environ if env is None else env)
    if now is None:
        now = datetime.now(timezone.utc)
    run_dir = _create_run_dir(runs_dir, now=now)
    report = build_report(
        env_map,
        now=now,
        platform_name=platform_name,
        home=home,
    )
    report_path = run_dir / "instance_paths.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report, report_path


def _print_summary(report: Mapping[str, Any], report_path: Path) -> None:
    print(f"[discover_instance] artifact: {report_path}")
    print(f"platform: {report['inputs']['platform']}")
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
