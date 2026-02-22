from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import scripts.kag_sync_neo4j as kag_sync


def _write_graph_payload(path: Path) -> None:
    payload = {
        "schema_version": "kag_baseline_v1",
        "generated_at_utc": "2026-02-22T21:10:00+00:00",
        "stats": {"doc_nodes": 1, "entity_nodes": 2, "mention_edges": 2, "cooccurs_edges": 1},
        "nodes": {
            "docs": [
                {
                    "id": "doc:quest:steel_tools",
                    "doc_id": "quest:steel_tools",
                    "source": "ftbquests",
                    "title": "Steel",
                    "path": "docs.jsonl",
                }
            ],
            "entities": [
                {"id": "ent:steel", "entity": "steel", "label": "steel"},
                {"id": "ent:tools", "entity": "tools", "label": "tools"},
            ],
        },
        "edges": {
            "mentions": [
                {"src": "doc:quest:steel_tools", "dst": "ent:steel", "type": "mentions", "weight": 1},
                {"src": "doc:quest:steel_tools", "dst": "ent:tools", "type": "mentions", "weight": 1},
            ],
            "cooccurs": [{"src": "ent:steel", "dst": "ent:tools", "type": "cooccurs", "weight": 1}],
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_kag_sync_neo4j_writes_run_and_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    graph_path = tmp_path / "kag_graph.json"
    _write_graph_payload(graph_path)

    captured: dict[str, Any] = {}

    def _fake_sync(graph_payload, *, url: str, database: str, user: str, password: str, timeout_sec: float, batch_size: int, reset_graph: bool):
        captured["schema_version"] = graph_payload.get("schema_version")
        captured["url"] = url
        captured["database"] = database
        captured["user"] = user
        captured["password"] = password
        captured["timeout_sec"] = timeout_sec
        captured["batch_size"] = batch_size
        captured["reset_graph"] = reset_graph
        return {
            "url": url,
            "database": database,
            "reset_graph": reset_graph,
            "doc_nodes": 1,
            "entity_nodes": 2,
            "mention_edges": 2,
            "cooccurs_edges": 1,
            "query_calls": 6,
        }

    monkeypatch.setattr(kag_sync, "sync_kag_graph_neo4j", _fake_sync)

    result = kag_sync.run_kag_sync_neo4j(
        graph_path=graph_path,
        neo4j_url="http://localhost:7474",
        neo4j_database="neo4j",
        neo4j_user="neo4j",
        neo4j_password="secret",
        reset_graph=True,
        timeout_sec=12.0,
        batch_size=100,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 23, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    summary_payload = json.loads((run_dir / "neo4j_sync_summary.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260222_230000-kag-sync-neo4j"
    assert run_payload["status"] == "ok"
    assert summary_payload["doc_nodes"] == 1
    assert captured["schema_version"] == "kag_baseline_v1"
    assert captured["url"] == "http://localhost:7474"
    assert captured["database"] == "neo4j"
    assert captured["user"] == "neo4j"
    assert captured["password"] == "secret"
    assert captured["timeout_sec"] == 12.0
    assert captured["batch_size"] == 100
    assert captured["reset_graph"] is True


def test_kag_sync_neo4j_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["kag_sync_neo4j.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        kag_sync.parse_args()
    assert exc.value.code == 0
