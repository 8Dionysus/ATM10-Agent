from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.gateway_v1_local as gateway


def _fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / name


def test_gateway_v1_local_health_ok(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "health",
            "payload": {},
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    response_payload = json.loads((run_dir / "response.json").read_text(encoding="utf-8"))
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert response_payload["schema_version"] == "gateway_response_v1"
    assert response_payload["operation"] == "health"
    assert response_payload["status"] == "ok"
    assert sorted(response_payload["result"]["supported_operations"]) == sorted(gateway.SUPPORTED_OPERATIONS)
    assert run_payload["status"] == "ok"
    assert (run_dir / "request.json").exists()


def test_gateway_v1_local_invalid_schema_returns_error(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_bad",
            "operation": "health",
            "payload": {},
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 1, 0, tzinfo=timezone.utc),
    )
    response_payload = result["response_payload"]
    assert result["ok"] is False
    assert response_payload["status"] == "error"
    assert response_payload["error_code"] == "invalid_request"
    assert "schema_version" in str(response_payload["error"])


def test_gateway_v1_local_missing_request_json_still_writes_artifacts(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_json=tmp_path / "missing_request.json",
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 1, 30, tzinfo=timezone.utc),
    )
    run_dir = result["run_dir"]
    assert result["ok"] is False
    assert result["response_payload"]["error_code"] == "invalid_request"
    assert (run_dir / "run.json").exists()
    assert (run_dir / "response.json").exists()
    assert (run_dir / "request.json").exists()


def test_gateway_v1_local_retrieval_query_ok(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "retrieval_query",
            "payload": {
                "query": "mekanism steel",
                "docs_path": str(_fixture_path("retrieval_docs_sample.jsonl")),
                "topk": 3,
                "candidate_k": 10,
                "reranker": "none",
            },
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 2, 0, tzinfo=timezone.utc),
    )

    response_payload = result["response_payload"]
    assert result["ok"] is True
    assert response_payload["status"] == "ok"
    assert response_payload["result"]["results_count"] >= 1
    child_run_dir = Path(response_payload["artifacts"]["child_runs"]["retrieval_query"])
    assert (child_run_dir / "run.json").exists()
    assert (child_run_dir / "retrieval_results.json").exists()


def test_gateway_v1_local_kag_query_file_ok(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "kag_query",
            "payload": {
                "backend": "file",
                "docs_in": str(_fixture_path("kag_neo4j_docs_sample.jsonl")),
                "query": "steel tools",
                "topk": 5,
            },
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 3, 0, tzinfo=timezone.utc),
    )

    response_payload = result["response_payload"]
    assert result["ok"] is True
    assert response_payload["status"] == "ok"
    assert response_payload["result"]["backend"] == "file"
    assert "kag_build_baseline" in response_payload["artifacts"]["child_runs"]
    assert "kag_query_demo" in response_payload["artifacts"]["child_runs"]


def test_gateway_v1_local_hybrid_query_ok(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "hybrid_query",
            "payload": {
                "query": "steel tools",
                "docs_path": str(_fixture_path("retrieval_docs_sample.jsonl")),
                "topk": 5,
                "candidate_k": 10,
                "reranker": "none",
            },
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 3, 30, tzinfo=timezone.utc),
    )

    response_payload = result["response_payload"]
    assert result["ok"] is True
    assert response_payload["status"] == "ok"
    assert response_payload["result"]["backend"] == "hybrid_baseline"
    assert response_payload["result"]["planner_mode"] == "retrieval_first_kag_expansion"
    assert response_payload["result"]["results_count"] >= 1
    child_run_dir = Path(response_payload["artifacts"]["child_runs"]["hybrid_query"])
    assert (child_run_dir / "run.json").exists()
    assert (child_run_dir / "hybrid_query_results.json").exists()


def test_gateway_v1_local_automation_dry_run_ok(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "automation_dry_run",
            "payload": {"plan_json": str(_fixture_path("automation_plan_quest_book.json"))},
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 4, 0, tzinfo=timezone.utc),
    )

    response_payload = result["response_payload"]
    assert result["ok"] is True
    assert response_payload["status"] == "ok"
    assert response_payload["result"]["action_count"] == 3
    assert response_payload["result"]["step_count"] == 4
    assert "automation_dry_run" in response_payload["artifacts"]["child_runs"]


def test_gateway_v1_local_safe_action_smoke_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured_audit: dict[str, object] = {}

    def _fake_run_safe_action(action_key: str, runs_dir: Path, *, timeout_sec: float = 300.0) -> dict[str, object]:
        assert action_key == "gateway_local_core"
        assert timeout_sec == 45.0
        return {
            "schema_version": "gateway_operator_safe_action_run_v1",
            "timestamp_utc": "2026-02-27T10:04:30+00:00",
            "action_key": action_key,
            "action_runs_dir": str(runs_dir / "ui-safe-gateway-core"),
            "summary_json": str(runs_dir / "ui-safe-gateway-core" / "gateway_smoke_summary.json"),
            "exit_code": 0,
            "status": "ok",
            "ok": True,
            "summary_status": "ok",
            "error": None,
        }

    def _fake_append_safe_action_audit(runs_dir: Path, entry: dict[str, object]) -> None:
        captured_audit["runs_dir"] = str(runs_dir)
        captured_audit["entry"] = dict(entry)

    monkeypatch.setattr(gateway, "run_safe_action", _fake_run_safe_action)
    monkeypatch.setattr(gateway, "append_safe_action_audit", _fake_append_safe_action_audit)

    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "safe_action_smoke",
            "payload": {
                "action_key": "gateway_local_core",
                "confirm": True,
                "timeout_sec": 45.0,
            },
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 4, 30, tzinfo=timezone.utc),
    )

    response_payload = result["response_payload"]
    assert result["ok"] is True
    assert response_payload["status"] == "ok"
    assert response_payload["result"]["schema_version"] == "gateway_operator_safe_action_run_v1"
    assert response_payload["result"]["action_key"] == "gateway_local_core"
    assert response_payload["result"]["smoke_only"] is True
    assert "safe_action_smoke" in response_payload["artifacts"]["child_runs"]
    assert captured_audit["runs_dir"] == str(tmp_path / "runs")


def test_gateway_v1_local_safe_action_smoke_requires_confirm(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "safe_action_smoke",
            "payload": {
                "action_key": "gateway_local_core",
                "confirm": False,
            },
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 4, 45, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["response_payload"]["status"] == "error"
    assert result["response_payload"]["error_code"] == "invalid_request"
    assert "payload.confirm must be true" in str(result["response_payload"]["error"])


def test_gateway_v1_local_kag_query_missing_query_fails(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "kag_query",
            "payload": {"backend": "file"},
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 5, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is False
    assert result["response_payload"]["status"] == "error"
    assert result["response_payload"]["error_code"] == "invalid_request"


def test_gateway_v1_local_hybrid_query_requires_docs_path(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "hybrid_query",
            "payload": {"query": "steel tools"},
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 5, 15, tzinfo=timezone.utc),
    )
    assert result["ok"] is False
    assert result["response_payload"]["status"] == "error"
    assert result["response_payload"]["error_code"] == "invalid_request"
    assert "payload.docs_path" in str(result["response_payload"]["error"])


def test_gateway_v1_local_redacts_sensitive_fields_in_request_artifact(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "kag_query",
            "payload": {
                "backend": "neo4j",
                "query": "steel tools",
                "topk": 1,
                "neo4j_password": "SUPER_SECRET_VALUE",
            },
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 5, 30, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    request_payload = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert request_payload["payload"]["neo4j_password"] == "[REDACTED]"
    request_redaction = run_payload["request_redaction"]
    assert request_redaction["applied"] is True
    assert "payload.neo4j_password" in request_redaction["fields_redacted"]


def test_gateway_v1_local_rejects_untrusted_reranker_model_by_default(tmp_path: Path) -> None:
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "retrieval_query",
            "payload": {
                "query": "mekanism steel",
                "docs_path": str(_fixture_path("retrieval_docs_sample.jsonl")),
                "reranker": "qwen3",
                "reranker_model": "evil/custom-model",
            },
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 5, 45, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["response_payload"]["error_code"] == "invalid_request"
    assert "reranker_model is not allowed" in str(result["response_payload"]["error"])


def test_gateway_v1_local_allows_untrusted_reranker_model_with_env_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATM10_ALLOW_UNTRUSTED_RERANKER_MODEL", "true")

    def _fake_retrieve_top_k(
        query: str,
        docs: list[dict[str, object]],
        *,
        topk: int,
        candidate_k: int,
        reranker: str,
        reranker_model: str,
        reranker_max_length: int,
        reranker_runtime: str,
        reranker_device: str,
    ) -> list[dict[str, object]]:
        assert query == "mekanism steel"
        assert topk == 3
        assert candidate_k == 10
        assert reranker == "qwen3"
        assert reranker_model == "evil/custom-model"
        assert reranker_max_length == 1024
        assert reranker_runtime == "torch"
        assert reranker_device == "AUTO"
        assert docs
        return [
            {
                "score": 1.0,
                "id": "doc:guide/steel_tools",
                "source": "ftbquests",
                "title": "Steel Tools",
                "text": "Use steel tools.",
                "citation": {
                    "id": "doc:guide/steel_tools",
                    "source": "ftbquests",
                    "path": "tests/fixtures/retrieval_docs_sample.jsonl",
                },
            }
        ]

    monkeypatch.setattr(gateway, "retrieve_top_k", _fake_retrieve_top_k)
    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "retrieval_query",
            "payload": {
                "query": "mekanism steel",
                "docs_path": str(_fixture_path("retrieval_docs_sample.jsonl")),
                "reranker": "qwen3",
                "reranker_model": "evil/custom-model",
            },
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 6, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    assert result["response_payload"]["status"] == "ok"
    assert result["response_payload"]["result"]["results_count"] == 1


def test_gateway_v1_local_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["gateway_v1_local.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        gateway.parse_args()
    assert exc.value.code == 0
