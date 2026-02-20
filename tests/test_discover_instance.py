import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.discover_instance import run_discovery


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def test_run_discovery_creates_artifact_and_detects_markers(tmp_path: Path) -> None:
    appdata = tmp_path / "Roaming"
    minecraft_dir = appdata / ".minecraft"
    atm10_dir = minecraft_dir / "versions" / "All the Mods 10 - ATM10 Test"

    for marker in ("config", "mods", "logs", "saves"):
        _mkdir(atm10_dir / marker)

    runs_dir = tmp_path / "runs"
    now = datetime(2026, 2, 19, 12, 0, 0, tzinfo=timezone.utc)

    report, artifact_path = run_discovery(
        env={"APPDATA": str(appdata)},
        runs_dir=runs_dir,
        now=now,
    )

    assert artifact_path.exists()
    assert artifact_path.name == "instance_paths.json"
    assert artifact_path.parent.name == "20260219_120000"

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["paths"]["minecraft_dir"] == str(minecraft_dir)
    assert payload["paths"]["atm10_dir"] == str(atm10_dir)
    assert payload["exists"]["minecraft_dir"] is True
    assert payload["exists"]["atm10_dir"] is True
    assert payload["markers"] == {
        "config": True,
        "mods": True,
        "logs": True,
        "saves": True,
    }
    assert report == payload

