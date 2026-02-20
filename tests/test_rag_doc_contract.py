import json
from datetime import datetime, timezone
from pathlib import Path

from src.rag.doc_contract import REQUIRED_FIELDS, ensure_valid_doc, normalize_doc


def test_fixture_records_follow_contract() -> None:
    fixture_path = Path("tests/fixtures/rag_docs_sample.jsonl")
    lines = fixture_path.read_text(encoding="utf-8").splitlines()
    assert lines

    for line in lines:
        payload = json.loads(line)
        for field in REQUIRED_FIELDS:
            assert field in payload
        ensure_valid_doc(payload)


def test_normalize_doc_sets_defaults_and_types() -> None:
    now = datetime(2026, 2, 19, 13, 0, 0, tzinfo=timezone.utc)
    payload = normalize_doc(
        {
            "id": "quest:test",
            "source": "ftbquests",
            "title": "  Test title  ",
            "text": "  Test body ",
            "tags": "quest",
        },
        now=now,
    )

    assert payload["id"] == "quest:test"
    assert payload["source"] == "ftbquests"
    assert payload["title"] == "Test title"
    assert payload["text"] == "Test body"
    assert payload["tags"] == ["quest"]
    assert payload["created_at"] == "2026-02-19T13:00:00+00:00"

