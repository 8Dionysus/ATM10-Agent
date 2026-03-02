from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import scripts.build_ops_contract_index as index_builder


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_ops_contract_index_classifies_fresh_stale_missing(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    now = datetime(2026, 3, 2, 12, 0, 0, tzinfo=timezone.utc)
    _write_json(
        runs_dir / "ci-smoke-phase-a" / "smoke_summary.json",
        {"status": "ok", "checked_at_utc": "2026-03-02T11:30:00+00:00"},
    )
    _write_json(
        runs_dir / "ci-smoke-retrieve" / "smoke_summary.json",
        {"status": "ok", "checked_at_utc": "2026-02-27T11:30:00+00:00"},
    )

    result = index_builder.run_build_ops_contract_index(
        profile="ci_smoke",
        runs_dir=runs_dir,
        summary_json=tmp_path / "ops_index.json",
        stale_after_hours=36.0,
        now=now,
    )
    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["schema_version"] == "ops_contract_index_v1"
    assert summary["status"] == "ok"
    assert summary["totals"]["source_count"] == 9
    assert summary["totals"]["freshness"]["fresh"] >= 1
    assert summary["totals"]["freshness"]["stale"] >= 1
    assert summary["totals"]["freshness"]["missing"] >= 1


def test_build_ops_contract_index_marks_invalid_json(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    broken = runs_dir / "ci-smoke-phase-a" / "smoke_summary.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("{bad", encoding="utf-8")

    result = index_builder.run_build_ops_contract_index(
        profile="ci_smoke",
        runs_dir=runs_dir,
        summary_json=tmp_path / "ops_index.json",
        stale_after_hours=36.0,
        now=datetime(2026, 3, 2, 12, 0, 0, tzinfo=timezone.utc),
    )
    summary = result["summary_payload"]
    assert summary["status"] == "ok"
    assert summary["totals"]["freshness"]["invalid"] >= 1
    assert summary["warnings"]


def test_build_ops_contract_index_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["build_ops_contract_index.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        index_builder.parse_args()
    assert exc.value.code == 0
