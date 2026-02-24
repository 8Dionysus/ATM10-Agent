from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import scripts.collect_smoke_run_summary as helper


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_collect_smoke_run_summary_phase_a_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs" / "ci-smoke-phase-a"
    run_dir = runs_dir / "20260224_170000"
    _write_json(run_dir / "run.json", {"mode": "phase_a_smoke", "vlm": {"resolved": "stub", "fallback_used": False}})
    _write_json(run_dir / "response.json", {"ok": True})
    summary_path = runs_dir / "smoke_summary.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect_smoke_run_summary.py",
            "--runs-dir",
            str(runs_dir),
            "--expected-mode",
            "phase_a_smoke",
            "--summary-json",
            str(summary_path),
        ],
    )
    exit_code = helper.main()
    assert exit_code == 0
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert summary["status"] == "ok"
    assert summary["observed"]["mode"] == "phase_a_smoke"
    assert summary["observed"]["vlm_resolved"] == "stub"


def test_collect_smoke_run_summary_retrieve_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs" / "ci-smoke-retrieve"
    run_dir = runs_dir / "20260224_170001"
    _write_json(run_dir / "run.json", {"mode": "retrieve_demo", "status": "ok"})
    _write_json(run_dir / "retrieval_results.json", {"results": [{"id": "a"}, {"id": "b"}], "count": 2})
    summary_path = runs_dir / "smoke_summary.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect_smoke_run_summary.py",
            "--runs-dir",
            str(runs_dir),
            "--expected-mode",
            "retrieve_demo",
            "--summary-json",
            str(summary_path),
        ],
    )
    exit_code = helper.main()
    assert exit_code == 0
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert summary["observed"]["results_count"] == 2
    assert summary["observed"]["retrieved_count"] == 2


def test_collect_smoke_run_summary_eval_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs" / "ci-smoke-eval"
    run_dir = runs_dir / "20260224_170002"
    _write_json(run_dir / "run.json", {"mode": "eval_retrieval", "status": "ok"})
    _write_json(
        run_dir / "eval_results.json",
        {
            "metrics": {
                "query_count": 3,
                "mean_recall_at_k": 1.0,
                "mean_mrr_at_k": 0.9,
                "hit_rate_at_k": 1.0,
            }
        },
    )
    summary_path = runs_dir / "smoke_summary.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect_smoke_run_summary.py",
            "--runs-dir",
            str(runs_dir),
            "--expected-mode",
            "eval_retrieval",
            "--summary-json",
            str(summary_path),
        ],
    )
    exit_code = helper.main()
    assert exit_code == 0
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert summary["observed"]["query_count"] == 3


def test_collect_smoke_run_summary_fails_on_mode_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs" / "ci-smoke-phase-a"
    run_dir = runs_dir / "20260224_170003"
    _write_json(run_dir / "run.json", {"mode": "phase_a_smoke"})
    _write_json(run_dir / "response.json", {"ok": True})
    summary_path = runs_dir / "smoke_summary.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect_smoke_run_summary.py",
            "--runs-dir",
            str(runs_dir),
            "--expected-mode",
            "retrieve_demo",
            "--summary-json",
            str(summary_path),
        ],
    )
    exit_code = helper.main()
    assert exit_code == 2
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["ok"] is False
    assert any("expected_mode" in item for item in summary["violations"])


def test_collect_smoke_run_summary_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["collect_smoke_run_summary.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        helper.parse_args()
    assert exc.value.code == 0
