from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

import scripts.gateway_v1_http_service as gateway_http
from scripts.gateway_v1_local import run_gateway_request


def _fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / name


def _build_requests() -> list[dict[str, object]]:
    return [
        {
            "schema_version": "gateway_request_v1",
            "operation": "health",
            "payload": {},
        },
        {
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
        {
            "schema_version": "gateway_request_v1",
            "operation": "kag_query",
            "payload": {
                "backend": "file",
                "docs_in": str(_fixture_path("kag_neo4j_docs_sample.jsonl")),
                "query": "steel tools",
                "topk": 5,
            },
        },
        {
            "schema_version": "gateway_request_v1",
            "operation": "automation_dry_run",
            "payload": {
                "plan_json": str(_fixture_path("automation_plan_quest_book.json")),
            },
        },
    ]


def _assert_semantic_result_parity(operation: str, cli_result: dict[str, object], http_result: dict[str, object]) -> None:
    if operation == "health":
        assert sorted(http_result["supported_operations"]) == sorted(cli_result["supported_operations"])
        return
    if operation == "retrieval_query":
        for field in ("query", "backend", "results_count", "topk", "candidate_k", "reranker"):
            assert http_result[field] == cli_result[field]
        return
    if operation == "kag_query":
        for field in ("backend", "query", "topk", "results_count"):
            assert http_result[field] == cli_result[field]
        return
    if operation == "automation_dry_run":
        for field in ("action_count", "step_count", "dry_run_only"):
            assert http_result[field] == cli_result[field]
        return
    raise AssertionError(f"unsupported operation in parity matrix: {operation}")


def test_gateway_v1_contract_parity_matrix_cli_vs_http(tmp_path: Path) -> None:
    app = gateway_http.create_app(runs_dir=tmp_path / "runs-http")
    requests = _build_requests()
    with TestClient(app) as client:
        for request_payload in requests:
            cli_payload = run_gateway_request(
                request_payload=request_payload,
                runs_dir=tmp_path / "runs-cli",
            )["response_payload"]
            response = client.post("/v1/gateway", json=request_payload)
            http_payload = response.json()

            assert response.status_code == gateway_http.map_gateway_http_status(http_payload)
            for field in ("schema_version", "operation", "status", "error_code"):
                assert http_payload[field] == cli_payload[field]
            assert isinstance(http_payload["result"], dict)
            assert isinstance(cli_payload["result"], dict)
            _assert_semantic_result_parity(
                str(request_payload["operation"]),
                cli_result=cli_payload["result"],
                http_result=http_payload["result"],
            )
