from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.kag_query_demo as kag_query


def _write_graph_payload(path: Path) -> None:
    payload = {
        "schema_version": "kag_baseline_v1",
        "generated_at_utc": "2026-02-22T21:10:00+00:00",
        "stats": {"doc_nodes": 2, "entity_nodes": 3, "mention_edges": 4, "cooccurs_edges": 1},
        "nodes": {
            "docs": [
                {"id": "doc:quest:steel_tools", "doc_id": "quest:steel_tools", "source": "ftbquests", "title": "Steel", "path": "docs.jsonl"},
                {"id": "doc:quest:ars_start", "doc_id": "quest:ars_start", "source": "ftbquests", "title": "Ars", "path": "docs.jsonl"},
            ],
            "entities": [
                {"id": "ent:steel", "entity": "steel", "label": "steel"},
                {"id": "ent:tools", "entity": "tools", "label": "tools"},
                {"id": "ent:ars_nouveau", "entity": "ars_nouveau", "label": "ars_nouveau"},
            ],
        },
        "edges": {
            "mentions": [
                {"src": "doc:quest:steel_tools", "dst": "ent:steel", "type": "mentions", "weight": 1},
                {"src": "doc:quest:steel_tools", "dst": "ent:tools", "type": "mentions", "weight": 1},
                {"src": "doc:quest:ars_start", "dst": "ent:ars_nouveau", "type": "mentions", "weight": 1},
            ],
            "cooccurs": [
                {"src": "ent:steel", "dst": "ent:tools", "type": "cooccurs", "weight": 1},
            ],
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_kag_query_demo_returns_ranked_results(tmp_path: Path) -> None:
    graph_path = tmp_path / "kag_graph.json"
    _write_graph_payload(graph_path)

    result = kag_query.run_kag_query_demo(
        graph_path=graph_path,
        query="steel tools",
        topk=3,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 21, 11, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    results_payload = json.loads((run_dir / "kag_query_results.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260222_211100-kag-query"
    assert run_payload["status"] == "ok"
    assert results_payload["count"] == 1
    assert results_payload["results"][0]["id"] == "quest:steel_tools"


def test_kag_query_demo_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["kag_query_demo.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        kag_query.parse_args()
    assert exc.value.code == 0
