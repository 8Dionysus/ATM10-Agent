from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts.discover_instance import (
    build_report,
    candidate_instance_roots,
    resolve_atm10_dir,
    resolve_minecraft_dir,
    run_discovery,
)


def test_minecraft_dir_env_still_wins(tmp_path: Path) -> None:
    configured = tmp_path / "configured-minecraft"

    path, source = resolve_minecraft_dir(
        {"MINECRAFT_DIR": str(configured)},
        platform_name="linux",
        home=tmp_path,
    )

    assert path == configured
    assert source == "env"


def test_linux_defaults_to_home_dot_minecraft(tmp_path: Path) -> None:
    path, source = resolve_minecraft_dir({}, platform_name="linux", home=tmp_path)

    assert path == tmp_path / ".minecraft"
    assert source == "linux_home_fallback"


def test_windows_appdata_fallback_is_preserved(tmp_path: Path) -> None:
    appdata = tmp_path / "Roaming"

    path, source = resolve_minecraft_dir(
        {"APPDATA": str(appdata)},
        platform_name="win32",
        home=tmp_path,
    )

    assert path == appdata / ".minecraft"
    assert source == "appdata_fallback"


def test_atm10_dir_env_wins_without_scanning(tmp_path: Path) -> None:
    configured = tmp_path / "ATM10-explicit"
    minecraft_dir = tmp_path / ".minecraft"

    path, source = resolve_atm10_dir(
        minecraft_dir,
        {"ATM10_DIR": str(configured)},
        platform_name="linux",
        home=tmp_path,
    )

    assert path == configured
    assert source == "env"


def test_linux_xdg_prismlauncher_instances_are_scanned(tmp_path: Path) -> None:
    xdg_home = tmp_path / "xdg"
    instance = xdg_home / "PrismLauncher" / "instances" / "All the Mods 10 - Fedora"
    (instance / "mods").mkdir(parents=True)
    (instance / "config").mkdir()

    minecraft_dir = tmp_path / ".minecraft"
    path, source = resolve_atm10_dir(
        minecraft_dir,
        {"XDG_DATA_HOME": str(xdg_home)},
        platform_name="linux",
        home=tmp_path,
    )

    assert path == instance
    assert source == "xdg_prismlauncher_instances_scan"


def test_candidate_instance_roots_are_deduplicated(tmp_path: Path) -> None:
    minecraft_dir = tmp_path / ".minecraft"
    roots = candidate_instance_roots(
        minecraft_dir,
        {"XDG_DATA_HOME": str(tmp_path / ".local" / "share")},
        platform_name="linux",
        home=tmp_path,
    )

    root_paths = [path for path, _source in roots]
    assert len(root_paths) == len(set(root_paths))


def test_build_report_includes_platform_inputs_and_candidate_roots(tmp_path: Path) -> None:
    xdg_home = tmp_path / "xdg"
    instance = xdg_home / "PrismLauncher" / "instances" / "ATM10"
    (instance / "mods").mkdir(parents=True)

    report = build_report(
        {"XDG_DATA_HOME": str(xdg_home), "HOME": str(tmp_path)},
        now=datetime(2026, 4, 21, tzinfo=timezone.utc),
        platform_name="linux",
        home=tmp_path,
    )

    assert report["inputs"]["platform"] == "linux"
    assert report["inputs"]["XDG_DATA_HOME"] == str(xdg_home)
    assert report["paths"]["atm10_dir"] == str(instance)
    assert report["discovery_sources"]["atm10_dir"] == "xdg_prismlauncher_instances_scan"
    assert report["markers"]["mods"] is True
    assert report["paths"]["candidate_instance_roots"]


def test_run_discovery_writes_artifact_with_linux_context(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"

    report, report_path = run_discovery(
        env={"HOME": str(tmp_path)},
        runs_dir=runs_dir,
        now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        platform_name="linux",
        home=tmp_path,
    )

    assert report_path.is_file()
    assert report_path.parent == runs_dir / "20260421_120000"
    assert report["paths"]["minecraft_dir"] == str(tmp_path / ".minecraft")
