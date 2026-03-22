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


def test_run_cross_service_benchmark_suite_combo_a_uses_live_profile_paths(
    monkeypatch,
    tmp_path: Path,
) -> None:
    seed_calls: dict[str, object] = {}
    retrieval_calls: dict[str, object] = {}
    kag_calls: dict[str, object] = {}
    live_calls: list[tuple[str, str]] = []

    def _fake_seed(**kwargs):
        seed_calls.update(kwargs)
        run_dir = kwargs["runs_dir"] / "seed-run"
        run_dir.mkdir(parents=True, exist_ok=True)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": {"status": "ok"},
            "summary_payload": {
                "qdrant": {
                    "collection": "atm10_combo_a_fixture_cross_service_suite",
                    "vector_size": 64,
                },
                "neo4j": {
                    "dataset_tag": "atm10_combo_a_fixture_cross_service_suite",
                },
            },
        }

    def _fake_live_service(service_name: str, backend: str):
        def _runner(**kwargs):
            live_calls.append((service_name, str(kwargs["service_url"])))
            run_dir = kwargs["runs_dir"] / f"{service_name}-run"
            run_dir.mkdir(parents=True, exist_ok=True)
            summary_path = run_dir / "service_sla_summary.json"
            _write_json(
                summary_path,
                build_service_sla_summary(
                    service_name=service_name,
                    surface="benchmark",
                    backend=backend,
                    profile="combo_a",
                    policy="signal_only",
                    status="ok",
                    metrics=build_common_metrics(sample_count=2, success_count=2, latency_values_ms=[10.0, 12.0]),
                    quality={"text_similarity_avg" if service_name == "voice_asr" else "non_empty_audio_rate": 1.0},
                    paths={"service_sla_summary_json": summary_path},
                ),
            )
            return {
                "ok": True,
                "run_dir": run_dir,
                "run_payload": {"paths": {"service_sla_summary_json": str(summary_path)}},
            }

        return _runner

    def _fake_retrieval(**kwargs):
        retrieval_calls.update(kwargs)
        run_dir = kwargs["runs_dir"] / "retrieval-run"
        run_dir.mkdir(parents=True, exist_ok=True)
        summary_path = run_dir / "service_sla_summary.json"
        _write_json(
            summary_path,
            build_service_sla_summary(
                service_name="retrieval",
                surface="eval",
                backend="qdrant",
                profile="combo_a",
                policy="signal_only",
                status="ok",
                metrics=build_common_metrics(sample_count=2, success_count=2, latency_values_ms=[5.0, 6.0]),
                quality={"mean_mrr_at_k": 1.0},
                paths={"service_sla_summary_json": summary_path},
            ),
        )
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": {"paths": {"service_sla_summary_json": str(summary_path)}},
        }

    def _fake_kag(**kwargs):
        kag_calls.update(kwargs)
        run_dir = kwargs["runs_dir"] / "kag-run"
        run_dir.mkdir(parents=True, exist_ok=True)
        summary_path = run_dir / "service_sla_summary.json"
        _write_json(
            summary_path,
            build_service_sla_summary(
                service_name="kag_neo4j",
                surface="eval",
                backend="neo4j",
                profile="combo_a",
                policy="signal_only",
                status="ok",
                metrics=build_common_metrics(sample_count=2, success_count=2, latency_values_ms=[7.0, 8.0]),
                quality={"mean_mrr_at_k": 1.0},
                paths={"service_sla_summary_json": summary_path},
            ),
        )
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": {"paths": {"service_sla_summary_json": str(summary_path)}},
        }

    monkeypatch.setattr(suite, "seed_combo_a_fixture_data", _fake_seed)
    monkeypatch.setattr(
        suite,
        "run_live_voice_asr_service_benchmark",
        _fake_live_service("voice_asr", "voice_runtime_service"),
    )
    monkeypatch.setattr(
        suite,
        "run_live_tts_service_benchmark",
        _fake_live_service("voice_tts", "tts_runtime_service"),
    )
    monkeypatch.setattr(suite, "run_eval_retrieval", _fake_retrieval)
    monkeypatch.setattr(suite, "run_eval_kag_neo4j", _fake_kag)

    result = suite.run_cross_service_benchmark_suite(
        profile="combo_a",
        runs_dir=tmp_path / "runs",
        summary_json=tmp_path / "runs" / "nightly-combo-a-cross-service-suite" / "cross_service_benchmark_suite.json",
        voice_service_url="http://127.0.0.1:8765",
        tts_service_url="http://127.0.0.1:8780",
        qdrant_url="http://127.0.0.1:6333",
        neo4j_url="http://127.0.0.1:7474",
        neo4j_database="neo4j",
        neo4j_user="neo4j",
        neo4j_password="secret",
        now=datetime(2026, 3, 22, 19, 45, 0, tzinfo=timezone.utc),
    )

    summary_payload = result["summary_payload"]
    assert result["ok"] is True
    assert summary_payload["profile"] == "combo_a"
    assert sorted(summary_payload["services"].keys()) == ["kag_neo4j", "retrieval", "voice_asr", "voice_tts"]
    assert summary_payload["overall_sla_status"] == "pass"
    assert summary_payload["paths"]["combo_a_seed_run_dir"].endswith("seed-run")
    assert seed_calls["scope"] == "cross_service_suite"
    assert retrieval_calls["backend"] == "qdrant"
    assert retrieval_calls["collection"] == "atm10_combo_a_fixture_cross_service_suite"
    assert kag_calls["neo4j_dataset_tag"] == "atm10_combo_a_fixture_cross_service_suite"
    assert ("voice_asr", "http://127.0.0.1:8765") in live_calls
    assert ("voice_tts", "http://127.0.0.1:8780") in live_calls
