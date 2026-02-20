import json
from datetime import datetime, timezone
from pathlib import Path

from src.rag.ftbquests_ingest import (
    candidate_quests_dirs,
    discover_quests_dir,
    ingest_ftbquests_dir,
)


def test_discover_quests_dir_prefers_atm10_path(tmp_path: Path) -> None:
    minecraft_dir = tmp_path / ".minecraft"
    atm10_dir = minecraft_dir / "versions" / "ATM10"
    atm10_quests = atm10_dir / "config" / "ftbquests" / "quests"
    minecraft_quests = minecraft_dir / "config" / "ftbquests" / "quests"

    atm10_quests.mkdir(parents=True, exist_ok=True)
    minecraft_quests.mkdir(parents=True, exist_ok=True)

    candidates = candidate_quests_dirs(minecraft_dir=minecraft_dir, atm10_dir=atm10_dir)
    assert candidates[0] == atm10_quests
    assert candidates[1] == minecraft_quests

    discovered = discover_quests_dir(minecraft_dir=minecraft_dir, atm10_dir=atm10_dir)
    assert discovered["found"] is True
    assert discovered["selected"] == str(atm10_quests)


def test_ingest_ftbquests_writes_jsonl_and_errors(tmp_path: Path) -> None:
    quests_dir = tmp_path / "quests"
    quests_dir.mkdir(parents=True, exist_ok=True)

    fixtures_dir = Path("tests") / "fixtures" / "ftbquests_raw"
    (quests_dir / "good_quest.json").write_text(
        (fixtures_dir / "good_quest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (quests_dir / "bad_quest.json").write_text(
        (fixtures_dir / "bad_quest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (quests_dir / "notes.txt").write_text("unsupported", encoding="utf-8")

    output_jsonl = tmp_path / "data" / "ftbquests_norm" / "quests.jsonl"
    errors_jsonl = tmp_path / "runs" / "20260219_150000" / "ingest_errors.jsonl"
    now = datetime(2026, 2, 19, 15, 0, 0, tzinfo=timezone.utc)

    summary = ingest_ftbquests_dir(
        quests_dir=quests_dir,
        output_jsonl=output_jsonl,
        errors_jsonl=errors_jsonl,
        now=now,
    )

    assert summary["docs_written"] == 1
    assert summary["errors_logged"] == 2
    assert summary["skipped_filtered"] == 0
    assert output_jsonl.exists()
    assert errors_jsonl.exists()

    docs = [json.loads(line) for line in output_jsonl.read_text(encoding="utf-8").splitlines()]
    assert len(docs) == 1
    doc = docs[0]
    assert doc["id"] == "ftbquests:good_quest.json"
    assert doc["source"] == "ftbquests"
    assert doc["title"] == "Iron Progression"
    assert "Craft iron tools" in doc["text"]
    assert doc["created_at"] == "2026-02-19T15:00:00+00:00"

    errors = [json.loads(line) for line in errors_jsonl.read_text(encoding="utf-8").splitlines()]
    assert len(errors) == 2
    error_types = {entry["error"] for entry in errors}
    assert error_types == {"parse_error", "unsupported_extension"}


def test_ingest_ftbquests_accepts_snbt_files(tmp_path: Path) -> None:
    quests_dir = tmp_path / "quests"
    quests_dir.mkdir(parents=True, exist_ok=True)
    (quests_dir / "allthemodium.snbt").write_text(
        '{ id: "4293754F9B2D05F0" filename: "allthemodium" tasks: [{ type: "item" item: { id: "minecraft:iron_ingot" } }] }',
        encoding="utf-8",
    )
    (quests_dir / "readme.txt").write_text("unsupported", encoding="utf-8")

    output_jsonl = tmp_path / "data" / "ftbquests_norm" / "quests.jsonl"
    errors_jsonl = tmp_path / "runs" / "20260220_010000" / "ingest_errors.jsonl"
    now = datetime(2026, 2, 20, 1, 0, 0, tzinfo=timezone.utc)

    summary = ingest_ftbquests_dir(
        quests_dir=quests_dir,
        output_jsonl=output_jsonl,
        errors_jsonl=errors_jsonl,
        now=now,
    )

    assert summary["docs_written"] == 1
    assert summary["errors_logged"] == 1
    assert summary["skipped_filtered"] == 0

    docs = [json.loads(line) for line in output_jsonl.read_text(encoding="utf-8").splitlines()]
    assert len(docs) == 1
    doc = docs[0]
    assert doc["id"] == "ftbquests:allthemodium.snbt"
    assert doc["title"] == "allthemodium"
    assert "filename:allthemodium" in doc["text"]
    assert "id:minecraft:iron_ingot" in doc["text"]
    assert "snbt" in doc["tags"]
    assert doc["created_at"] == "2026-02-20T01:00:00+00:00"


def test_ingest_ftbquests_skips_lang_and_reward_tables_by_default(tmp_path: Path) -> None:
    quests_dir = tmp_path / "quests"
    (quests_dir / "chapters").mkdir(parents=True, exist_ok=True)
    (quests_dir / "lang" / "en_us" / "chapters").mkdir(parents=True, exist_ok=True)
    (quests_dir / "reward_tables").mkdir(parents=True, exist_ok=True)

    (quests_dir / "chapters" / "main.snbt").write_text(
        '{ id: "AAA" filename: "main" tasks: [{ type: "item" item: { id: "minecraft:iron_ingot" } }] }',
        encoding="utf-8",
    )
    (quests_dir / "lang" / "en_us" / "chapters" / "main.snbt").write_text(
        '{ id: "BBB" filename: "main_localized" }',
        encoding="utf-8",
    )
    (quests_dir / "reward_tables" / "basic.snbt").write_text(
        '{ id: "CCC" filename: "basic_rewards" }',
        encoding="utf-8",
    )

    output_jsonl = tmp_path / "data" / "ftbquests_norm" / "quests.jsonl"
    errors_jsonl = tmp_path / "runs" / "20260220_020000" / "ingest_errors.jsonl"
    now = datetime(2026, 2, 20, 2, 0, 0, tzinfo=timezone.utc)

    summary = ingest_ftbquests_dir(
        quests_dir=quests_dir,
        output_jsonl=output_jsonl,
        errors_jsonl=errors_jsonl,
        now=now,
    )

    assert summary["docs_written"] == 1
    assert summary["errors_logged"] == 0
    assert summary["skipped_filtered"] == 2

    docs = [json.loads(line) for line in output_jsonl.read_text(encoding="utf-8").splitlines()]
    assert len(docs) == 1
    assert docs[0]["id"] == "ftbquests:chapters/main.snbt"


def test_ingest_ftbquests_extracts_unquoted_snbt_signals(tmp_path: Path) -> None:
    quests_dir = tmp_path / "quests"
    quests_dir.mkdir(parents=True, exist_ok=True)
    (quests_dir / "chapters").mkdir(parents=True, exist_ok=True)
    (quests_dir / "chapters" / "mekanism.snbt").write_text(
        "{ filename: mekanism tasks:[{ type:item item:{ id:mekanism:steel_casing } }] dimension:allthemodium:the_other }",
        encoding="utf-8",
    )

    output_jsonl = tmp_path / "data" / "ftbquests_norm" / "quests.jsonl"
    errors_jsonl = tmp_path / "runs" / "20260220_030000" / "ingest_errors.jsonl"
    now = datetime(2026, 2, 20, 3, 0, 0, tzinfo=timezone.utc)

    summary = ingest_ftbquests_dir(
        quests_dir=quests_dir,
        output_jsonl=output_jsonl,
        errors_jsonl=errors_jsonl,
        now=now,
    )

    assert summary["docs_written"] == 1
    assert summary["errors_logged"] == 0

    docs = [json.loads(line) for line in output_jsonl.read_text(encoding="utf-8").splitlines()]
    assert len(docs) == 1
    text = docs[0]["text"]
    assert "filename:mekanism" in text
    assert "type:item" in text
    assert "id:mekanism:steel_casing" in text
    assert "dimension:allthemodium:the_other" in text
