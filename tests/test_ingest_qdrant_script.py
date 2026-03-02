from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.ingest_qdrant as ingest_qdrant


def test_ingest_qdrant_main_writes_run_and_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runs_dir = tmp_path / "runs"
    input_path = tmp_path / "docs"
    input_path.mkdir(parents=True)
    fixed_run_dir = runs_dir / "20260302_120000"

    def _fake_create_run_dir(base_runs_dir: Path, now: datetime) -> Path:
        assert base_runs_dir == runs_dir
        assert now.tzinfo == timezone.utc
        fixed_run_dir.mkdir(parents=True, exist_ok=False)
        return fixed_run_dir

    def _fake_load_docs(path: Path) -> list[dict[str, object]]:
        assert path == input_path
        return [
            {
                "id": "doc:test",
                "source": "fixture",
                "title": "Doc",
                "text": "Body",
                "path": "fixture.jsonl",
            }
        ]

    def _fake_ingest_docs_qdrant(
        docs: list[dict[str, object]],
        *,
        collection: str,
        host: str,
        port: int,
        vector_size: int,
        timeout_sec: float,
        batch_size: int,
    ) -> dict[str, object]:
        assert docs
        assert collection == "atm10-test"
        assert host == "127.0.0.1"
        assert port == 6333
        assert vector_size == 64
        assert timeout_sec == 10.0
        assert batch_size == 16
        return {
            "collection": collection,
            "docs_ingested": 1,
            "upsert_calls": 1,
            "host": host,
            "port": port,
        }

    monkeypatch.setattr(ingest_qdrant, "_create_run_dir", _fake_create_run_dir)
    monkeypatch.setattr(ingest_qdrant, "load_docs", _fake_load_docs)
    monkeypatch.setattr(ingest_qdrant, "ingest_docs_qdrant", _fake_ingest_docs_qdrant)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_qdrant.py",
            "--in",
            str(input_path),
            "--collection",
            "atm10-test",
            "--batch-size",
            "16",
            "--runs-dir",
            str(runs_dir),
        ],
    )

    exit_code = ingest_qdrant.main()
    run_payload = json.loads((fixed_run_dir / "run.json").read_text(encoding="utf-8"))
    summary_payload = json.loads((fixed_run_dir / "ingest_summary.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert run_payload["mode"] == "ingest_qdrant"
    assert run_payload["status"] == "ok"
    assert summary_payload["docs_ingested"] == 1
    assert summary_payload["upsert_calls"] == 1
