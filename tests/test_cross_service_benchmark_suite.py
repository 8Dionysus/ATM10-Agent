from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import scripts.cross_service_benchmark_suite as suite
from src.agent_core.service_sla import build_common_metrics, build_service_sla_summary


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_run_cross_service_benchmark_suite_writes_summary(tmp_path: Path) -> None:
    result = suite.run_cross_service_benchmark_suite(
        runs_dir=tmp_path / "runs",
        summary_json=tmp_path / "runs" / "ci-smoke-cross-service-suite" / "cross_service_benchmark_suite.json",
        now=datetime(2026, 3, 22, 19, 0, 0, tzinfo=timezone.utc),
        smoke_stub_voice_asr=True,
    )

    summary_payload = result["summary_payload"]
    assert result["ok"] is True
    assert summary_payload["schema_version"] == "cross_service_benchmark_suite_v1"
    assert summary_payload["status"] == "ok"
    assert summary_payload["overall_sla_status"] in {"pass", "breach"}
    assert sorted(summary_payload["services"].keys()) == ["kag_file", "retrieval", "voice_asr", "voice_tts"]
    assert any(row["source"] == "voice_asr" for row in summary_payload["summary_matrix"])
    assert Path(summary_payload["paths"]["summary_json"]).is_file()
    assert Path(summary_payload["paths"]["summary_md"]).is_file()


def test_run_cross_service_benchmark_suite_marks_child_breach_without_suite_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def _fake_retrieval(**kwargs):
        run_dir = kwargs["runs_dir"] / "fake-retrieval"
        run_dir.mkdir(parents=True, exist_ok=True)
        run_json_path = run_dir / "run.json"
        summary_path = run_dir / "service_sla_summary.json"
        _write_json(run_json_path, {"mode": "eval_retrieval", "paths": {"service_sla_summary_json": str(summary_path)}})
        _write_json(
            summary_path,
            build_service_sla_summary(
                service_name="retrieval",
                surface="eval",
                backend="in_memory",
                profile="baseline_first",
                policy="signal_only",
                status="error",
                metrics=build_common_metrics(sample_count=1, success_count=0, error_count=1, latency_values_ms=[]),
                quality={"mean_mrr_at_k": 0.0},
                breaches=["sample_errors_present"],
                paths={"service_sla_summary_json": summary_path},
            ),
        )
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": {"paths": {"service_sla_summary_json": str(summary_path)}},
            "eval_payload": {"error": "boom"},
        }

    monkeypatch.setattr(suite, "run_eval_retrieval", _fake_retrieval)

    result = suite.run_cross_service_benchmark_suite(
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 3, 22, 19, 15, 0, tzinfo=timezone.utc),
        smoke_stub_voice_asr=True,
    )

    assert result["ok"] is True
    assert result["summary_payload"]["status"] == "ok"
    assert result["summary_payload"]["overall_sla_status"] == "breach"
    assert "retrieval" in result["summary_payload"]["degraded_services"]


def test_run_cross_service_benchmark_suite_errors_when_summary_artifact_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def _fake_kag(**kwargs):
        run_dir = kwargs["runs_dir"] / "fake-kag"
        run_dir.mkdir(parents=True, exist_ok=True)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": {"paths": {"service_sla_summary_json": str(run_dir / "missing.json")}},
            "eval_payload": {"metrics": {}},
        }

    monkeypatch.setattr(suite, "run_eval_kag_file", _fake_kag)

    result = suite.run_cross_service_benchmark_suite(
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 3, 22, 19, 30, 0, tzinfo=timezone.utc),
        smoke_stub_voice_asr=True,
    )

    assert result["ok"] is False
    assert result["summary_payload"]["status"] == "error"
    assert "suite_orchestration" in result["summary_payload"]["degraded_services"]
