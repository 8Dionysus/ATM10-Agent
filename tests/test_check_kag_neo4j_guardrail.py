from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import scripts.check_kag_neo4j_guardrail as guardrail


def _write_eval_results(path: Path, *, recall: float, mrr: float, hit_rate: float, latency_p95_ms: float) -> None:
    payload = {
        "metrics": {
            "query_count": 8,
            "topk": 5,
            "mean_recall_at_k": recall,
            "mean_mrr_at_k": mrr,
            "hit_rate_at_k": hit_rate,
            "latency_mean_ms": 70.0,
            "latency_p95_ms": latency_p95_ms,
            "latency_max_ms": 90.0,
        },
        "cases": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_check_kag_neo4j_guardrail_sample_profile_passes(tmp_path: Path) -> None:
    eval_path = tmp_path / "eval_results.json"
    _write_eval_results(eval_path, recall=1.0, mrr=0.85, hit_rate=1.0, latency_p95_ms=90.0)
    metrics = guardrail._load_metrics(eval_path)
    ok, errors = guardrail.check_guardrail(
        metrics=metrics,
        min_recall_at_k=1.0,
        min_mrr_at_k=0.8,
        min_hit_rate_at_k=1.0,
        max_latency_p95_ms=120.0,
    )
    assert ok is True
    assert errors == []


def test_check_kag_neo4j_guardrail_hard_profile_fails_on_mrr(tmp_path: Path) -> None:
    eval_path = tmp_path / "eval_results.json"
    _write_eval_results(eval_path, recall=1.0, mrr=0.88, hit_rate=1.0, latency_p95_ms=90.0)
    metrics = guardrail._load_metrics(eval_path)
    ok, errors = guardrail.check_guardrail(
        metrics=metrics,
        min_recall_at_k=1.0,
        min_mrr_at_k=0.9,
        min_hit_rate_at_k=1.0,
        max_latency_p95_ms=130.0,
    )
    assert ok is False
    assert any("mean_mrr_at_k" in item for item in errors)


def test_check_kag_neo4j_guardrail_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_kag_neo4j_guardrail.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        guardrail.parse_args()
    assert exc.value.code == 0
