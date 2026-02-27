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


def test_gateway_v1_local_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["gateway_v1_local.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        gateway.parse_args()
    assert exc.value.code == 0
