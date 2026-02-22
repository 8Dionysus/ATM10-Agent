from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.kag_build_baseline as kag_build


def _write_docs_jsonl(path: Path) -> None:
    rows = [
        {
            "id": "quest:steel_tools",
            "source": "ftbquests",
            "title": "Steel Age",
            "text": "Build metallurgic_infuser and craft steel tools.",
            "tags": ["quest", "mekanism"],
            "created_at": "2026-02-20T00:00:00+00:00",
        },
        {
            "id": "quest:ars_start",
            "source": "ftbquests",
            "title": "Ars Start",
            "text": "Find source gem and craft novice spellbook.",
            "tags": ["quest", "ars_nouveau"],
            "created_at": "2026-02-20T00:00:00+00:00",
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_kag_build_baseline_writes_graph_artifacts(tmp_path: Path) -> None:
    docs_path = tmp_path / "docs.jsonl"
    _write_docs_jsonl(docs_path)

    result = kag_build.run_kag_build_baseline(
        docs_in=docs_path,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 21, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    graph_payload = json.loads((run_dir / "kag_graph.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260222_210000-kag-build"
    assert run_payload["status"] == "ok"
    assert graph_payload["schema_version"] == "kag_baseline_v1"
    assert graph_payload["stats"]["doc_nodes"] == 2
    assert graph_payload["stats"]["entity_nodes"] > 0
    assert graph_payload["stats"]["mention_edges"] > 0


def test_kag_build_baseline_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["kag_build_baseline.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        kag_build.parse_args()
    assert exc.value.code == 0
