from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.kag_query_neo4j as kag_query


def test_kag_query_neo4j_writes_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_query(*, url: str, database: str, user: str, password: str, query: str, topk: int, timeout_sec: float):
        assert url == "http://localhost:7474"
        assert database == "neo4j"
        assert user == "neo4j"
        assert password == "secret"
        assert query == "steel tools"
        assert topk == 3
        assert timeout_sec == 9.0
        return [
            {
                "score": 2.1,
                "id": "quest:steel_tools",
                "source": "ftbquests",
                "title": "Steel Age",
                "matched_entities": ["steel", "tools"],
                "citation": {
                    "id": "quest:steel_tools",
                    "source": "ftbquests",
                    "path": "docs.jsonl",
                },
            }
        ]

    monkeypatch.setattr(kag_query, "query_kag_neo4j", _fake_query)

    result = kag_query.run_kag_query_neo4j(
        query="steel tools",
        topk=3,
        neo4j_url="http://localhost:7474",
        neo4j_database="neo4j",
        neo4j_user="neo4j",
        neo4j_password="secret",
        timeout_sec=9.0,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 23, 10, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    results_payload = json.loads((run_dir / "kag_query_results.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260222_231000-kag-query-neo4j"
    assert run_payload["status"] == "ok"
    assert results_payload["count"] == 1
    assert results_payload["results"][0]["id"] == "quest:steel_tools"


def test_kag_query_neo4j_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["kag_query_neo4j.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        kag_query.parse_args()
    assert exc.value.code == 0
