from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.normalize_ftbquests as normalize_ftbquests


def test_normalize_ftbquests_main_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runs_dir = tmp_path / "runs"
    output_jsonl = tmp_path / "norm" / "quests.jsonl"
    quests_dir = tmp_path / "instance" / "config" / "ftbquests" / "quests"
    quests_dir.mkdir(parents=True)
    fixed_run_dir = runs_dir / "20260302_120500"

    def _fake_create_run_dir(base_runs_dir: Path, now: datetime) -> Path:
        assert base_runs_dir == runs_dir
        assert now.tzinfo == timezone.utc
        fixed_run_dir.mkdir(parents=True, exist_ok=False)
        return fixed_run_dir

    def _fake_resolve_minecraft_dir(env_map: dict[str, str]) -> tuple[Path, str]:
        assert isinstance(env_map, dict)
        return (tmp_path / "minecraft", "env")

    def _fake_resolve_atm10_dir(minecraft_dir: Path, env_map: dict[str, str]) -> tuple[Path, str]:
        assert minecraft_dir == tmp_path / "minecraft"
        assert isinstance(env_map, dict)
        return (tmp_path / "atm10", "discovery")

    def _fake_discover_quests_dir(*, minecraft_dir: Path, atm10_dir: Path | None) -> dict[str, object]:
        assert minecraft_dir == tmp_path / "minecraft"
        assert atm10_dir == tmp_path / "atm10"
        return {
            "selected": str(quests_dir),
            "found": True,
            "candidates": [str(quests_dir)],
        }

    def _fake_ingest_ftbquests_dir(
        *,
        quests_dir: Path,
        output_jsonl: Path,
        errors_jsonl: Path,
        now: datetime,
    ) -> dict[str, object]:
        assert quests_dir.exists()
        assert now.tzinfo == timezone.utc
        output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        output_jsonl.write_text(
            json.dumps(
                {
                    "id": "doc:test",
                    "source": "ftbquests",
                    "title": "Quest",
                    "text": "Do thing",
                    "path": "quest.snbt",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        errors_jsonl.parent.mkdir(parents=True, exist_ok=True)
        errors_jsonl.write_text("", encoding="utf-8")
        return {
            "output_jsonl": str(output_jsonl),
            "errors_jsonl": str(errors_jsonl),
            "docs_written": 1,
            "errors_logged": 0,
            "skipped_filtered": 0,
        }

    monkeypatch.setattr(normalize_ftbquests, "_create_run_dir", _fake_create_run_dir)
    monkeypatch.setattr(normalize_ftbquests, "resolve_minecraft_dir", _fake_resolve_minecraft_dir)
    monkeypatch.setattr(normalize_ftbquests, "resolve_atm10_dir", _fake_resolve_atm10_dir)
    monkeypatch.setattr(normalize_ftbquests, "discover_quests_dir", _fake_discover_quests_dir)
    monkeypatch.setattr(normalize_ftbquests, "ingest_ftbquests_dir", _fake_ingest_ftbquests_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "normalize_ftbquests.py",
            "--output",
            str(output_jsonl),
            "--runs-dir",
            str(runs_dir),
        ],
    )

    exit_code = normalize_ftbquests.main()
    paths_payload = json.loads((fixed_run_dir / "ftbquests_paths.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert output_jsonl.exists()
    assert (fixed_run_dir / "ingest_errors.jsonl").exists()
    assert paths_payload["quests_discovery"]["selected"] == str(quests_dir)
