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
    assert sorted(response_payload["result"]["supported_profiles"]) == sorted(gateway.SUPPORTED_PROFILES)
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


def test_gateway_v1_local_retrieval_query_qdrant_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_retrieve_top_k_qdrant(
        query: str,
        *,
        collection: str,
        topk: int,
        candidate_k: int,
        reranker: str,
        reranker_model: str,
        reranker_max_length: int,
        reranker_runtime: str,
        reranker_device: str,
        host: str,
        port: int,
        vector_size: int,
        timeout_sec: float,
    ) -> list[dict[str, object]]:
        assert query == "steel tools"
        assert collection == "atm10_combo_a_fixture_gateway_smoke"
        assert host == "127.0.0.1"
        assert port == 6333
        assert vector_size == 64
        assert timeout_sec == 10.0
        assert topk == 3
        assert candidate_k == 10
        assert reranker == "none"
        assert reranker_model == "Qwen/Qwen3-Reranker-0.6B"
        assert reranker_runtime == "torch"
        assert reranker_device == "AUTO"
        assert reranker_max_length == 1024
        return [
            {
                "id": "doc:steel_tools",
                "source": "ftbquests",
                "title": "Steel Tools",
                "text": "Craft steel tools.",
                "score": 1.0,
                "citation": {
                    "id": "doc:steel_tools",
                    "source": "ftbquests",
                    "path": "tests/fixtures/retrieval_docs_sample.jsonl",
                },
            }
        ]

    monkeypatch.setattr(gateway, "retrieve_top_k_qdrant", _fake_retrieve_top_k_qdrant)

    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "retrieval_query",
            "payload": {
                "backend": "qdrant",
                "query": "steel tools",
                "collection": "atm10_combo_a_fixture_gateway_smoke",
                "host": "127.0.0.1",
                "port": 6333,
                "vector_size": 64,
                "topk": 3,
                "candidate_k": 10,
                "reranker": "none",
            },
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 2, 30, tzinfo=timezone.utc),
    )

    response_payload = result["response_payload"]
    assert result["ok"] is True
    assert response_payload["status"] == "ok"
    assert response_payload["result"]["backend"] == "qdrant"
    assert response_payload["result"]["results_count"] == 1


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


def test_gateway_v1_local_hybrid_query_combo_a_allows_missing_docs_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_run_hybrid_query(
        *,
        query: str,
        docs_path: Path | None,
        topk: int,
        candidate_k: int,
        reranker: str,
        reranker_model: str,
        reranker_runtime: str,
        reranker_device: str,
        reranker_max_length: int,
        max_entities_per_doc: int,
        runs_dir: Path,
        profile: str,
        retrieval_backend: str,
        kag_backend: str,
        qdrant_collection: str | None,
        qdrant_host: str,
        qdrant_port: int,
        qdrant_vector_size: int,
        qdrant_timeout_sec: float,
        neo4j_url: str | None,
        neo4j_database: str,
        neo4j_user: str,
        neo4j_password: str | None,
        neo4j_timeout_sec: float,
        neo4j_dataset_tag: str | None,
        now: datetime | None,
    ) -> dict[str, object]:
        assert query == "steel tools"
        assert docs_path is None
        assert profile == "combo_a"
        assert retrieval_backend == "qdrant"
        assert kag_backend == "neo4j"
        assert qdrant_collection == "atm10_combo_a_fixture_gateway_smoke"
        assert qdrant_host == "127.0.0.1"
        assert qdrant_port == 6333
        assert qdrant_vector_size == 64
        assert qdrant_timeout_sec == 10.0
        assert neo4j_url == "http://127.0.0.1:7474"
        assert neo4j_database == "neo4j"
        assert neo4j_user == "neo4j"
        assert neo4j_password is None
        assert neo4j_timeout_sec == 10.0
        assert neo4j_dataset_tag == "atm10_combo_a_fixture_gateway_smoke"
        assert now is not None
        run_dir = runs_dir / "20260227_100330-hybrid-query"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text("{}", encoding="utf-8")
        (run_dir / "hybrid_query_results.json").write_text("{}", encoding="utf-8")
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": {"status": "ok"},
            "results_payload": {
                "schema_version": "hybrid_query_results_v1",
                "query": query,
                "planner_mode": "retrieval_first_kag_expansion",
                "planner_status": "hybrid_merged",
                "degraded": False,
                "retrieval_backend": retrieval_backend,
                "kag_backend": kag_backend,
                "retrieval_results_count": 1,
                "kag_results_count": 1,
                "results_count": 1,
            },
        }

    monkeypatch.setattr(gateway, "run_hybrid_query", _fake_run_hybrid_query)

    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "hybrid_query",
            "payload": {
                "profile": "combo_a",
                "query": "steel tools",
                "retrieval_backend": "qdrant",
                "kag_backend": "neo4j",
                "collection": "atm10_combo_a_fixture_gateway_smoke",
                "host": "127.0.0.1",
                "port": 6333,
                "vector_size": 64,
                "neo4j_url": "http://127.0.0.1:7474",
                "neo4j_database": "neo4j",
                "neo4j_user": "neo4j",
                "neo4j_dataset_tag": "atm10_combo_a_fixture_gateway_smoke",
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
    assert response_payload["result"]["backend"] == "hybrid_combo_a"
    assert response_payload["result"]["profile"] == "combo_a"
    assert response_payload["result"]["retrieval_backend"] == "qdrant"
    assert response_payload["result"]["kag_backend"] == "neo4j"


def test_gateway_v1_local_hybrid_query_returns_ok_for_degraded_combo_a_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_run_hybrid_query(**kwargs) -> dict[str, object]:
        run_dir = kwargs["runs_dir"] / "20260227_100331-hybrid-query"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text("{}", encoding="utf-8")
        (run_dir / "hybrid_query_results.json").write_text("{}", encoding="utf-8")
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": {"status": "ok"},
            "results_payload": {
                "schema_version": "hybrid_query_results_v1",
                "query": kwargs["query"],
                "planner_mode": "retrieval_first_kag_expansion",
                "planner_status": "grounding_unavailable",
                "degraded": True,
                "retrieval_backend": kwargs["retrieval_backend"],
                "kag_backend": kwargs["kag_backend"],
                "retrieval_results_count": 0,
                "kag_results_count": 0,
                "results_count": 0,
            },
        }

    monkeypatch.setattr(gateway, "run_hybrid_query", _fake_run_hybrid_query)

    result = gateway.run_gateway_request(
        request_payload={
            "schema_version": "gateway_request_v1",
            "operation": "hybrid_query",
            "payload": {
                "profile": "combo_a",
                "query": "steel tools",
                "retrieval_backend": "qdrant",
                "kag_backend": "neo4j",
                "collection": "atm10_combo_a_fixture",
                "topk": 5,
                "candidate_k": 10,
                "reranker": "none",
                "neo4j_password": "fixture-password",
            },
        },
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 27, 10, 3, 31, tzinfo=timezone.utc),
    )

    response_payload = result["response_payload"]
    assert result["ok"] is True
    assert response_payload["status"] == "ok"
    assert response_payload["result"]["planner_status"] == "grounding_unavailable"
    assert response_payload["result"]["degraded"] is True


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
