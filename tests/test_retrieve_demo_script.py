from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import scripts.retrieve_demo as retrieve_demo


def test_retrieve_demo_writes_run_json_on_backend_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(retrieve_demo, "load_docs", lambda _path: [{"id": "doc-1"}])
    monkeypatch.setattr(
        retrieve_demo,
        "retrieve_top_k",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("backend exploded")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retrieve_demo.py",
            "--query",
            "steel tools",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--in",
            str(tmp_path / "docs.jsonl"),
        ],
    )

    exit_code = retrieve_demo.main()

    assert exit_code == 2
    run_dirs = list((tmp_path / "runs").glob("*"))
    assert len(run_dirs) == 1
    run_json_path = run_dirs[0] / "run.json"
    assert run_json_path.exists()

    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    assert run_payload["mode"] == "retrieve_demo"
    assert run_payload["status"] == "error"
    assert run_payload["error_code"] == "retrieval_backend_error"
    assert "backend exploded" in run_payload["error"]
