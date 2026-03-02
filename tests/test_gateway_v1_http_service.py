from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

import scripts.gateway_v1_http_service as gateway_http
from scripts.gateway_v1_local import run_gateway_request


def _fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / name


def _set_mtime(path: Path, dt: datetime) -> None:
    ts = dt.timestamp()
    os.utime(path, (ts, ts))


def test_gateway_v1_http_service_healthz_ok(tmp_path: Path) -> None:
    policy = gateway_http.GatewayHTTPPolicy(
        max_request_body_bytes=10_000,
        max_json_depth=4,
        max_string_length=64,
        max_array_items=10,
        max_object_keys=10,
        operation_timeout_sec=9.0,
        error_log_max_bytes=4_096,
        error_log_max_files=7,
        artifact_retention_days=30,
        enable_error_redaction=False,
    )
    app = gateway_http.create_app(runs_dir=tmp_path / "runs", policy=policy)
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "gateway_v1_http_service"
    assert payload["policy"] == {
        "max_request_body_bytes": 10_000,
        "max_json_depth": 4,
        "max_string_length": 64,
        "max_array_items": 10,
        "max_object_keys": 10,
        "operation_timeout_sec": 9.0,
        "error_log_max_bytes": 4_096,
        "error_log_max_files": 7,
        "artifact_retention_days": 30,
        "enable_error_redaction": False,
    }


@pytest.mark.parametrize(
    "request_payload, expected_operation",
    [
        (
            {
                "schema_version": "gateway_request_v1",
                "operation": "health",
                "payload": {},
            },
            "health",
        ),
        (
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
            "retrieval_query",
        ),
        (
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
            "kag_query",
        ),
        (
            {
                "schema_version": "gateway_request_v1",
                "operation": "automation_dry_run",
                "payload": {
                    "plan_json": str(_fixture_path("automation_plan_quest_book.json")),
                },
            },
            "automation_dry_run",
        ),
    ],
)
def test_gateway_v1_http_service_gateway_happy_path(
    tmp_path: Path,
    request_payload: dict[str, object],
    expected_operation: str,
) -> None:
    app = gateway_http.create_app(runs_dir=tmp_path / "runs")
    with TestClient(app) as client:
        response = client.post("/v1/gateway", json=request_payload)
    payload = response.json()
    assert response.status_code == 200
    assert payload["schema_version"] == "gateway_response_v1"
    assert payload["operation"] == expected_operation
    assert payload["status"] == "ok"
    assert payload["error_code"] is None
    assert payload["result"] is not None


def test_gateway_v1_http_service_invalid_schema_returns_400(tmp_path: Path) -> None:
    app = gateway_http.create_app(runs_dir=tmp_path / "runs")
    with TestClient(app) as client:
        response = client.post(
            "/v1/gateway",
            json={
                "schema_version": "gateway_request_bad",
                "operation": "health",
                "payload": {},
            },
        )
    payload = response.json()
    assert response.status_code == 400
    assert payload["schema_version"] == "gateway_response_v1"
    assert payload["status"] == "error"
    assert payload["error_code"] == "invalid_request"


def test_gateway_v1_http_service_non_object_body_returns_400(tmp_path: Path) -> None:
    app = gateway_http.create_app(runs_dir=tmp_path / "runs")
    with TestClient(app) as client:
        response = client.post("/v1/gateway", json=["not-an-object"])
    payload = response.json()
    assert response.status_code == 400
    assert payload["schema_version"] == "gateway_response_v1"
    assert payload["status"] == "error"
    assert payload["error_code"] == "invalid_request"


def test_gateway_v1_http_service_payload_too_large_returns_413(tmp_path: Path) -> None:
    policy = gateway_http.GatewayHTTPPolicy(max_request_body_bytes=120)
    app = gateway_http.create_app(runs_dir=tmp_path / "runs", policy=policy)
    huge_payload = {
        "schema_version": "gateway_request_v1",
        "operation": "health",
        "payload": {"blob": "x" * 10_000},
    }
    with TestClient(app) as client:
        response = client.post("/v1/gateway", json=huge_payload)
    payload = response.json()
    assert response.status_code == 413
    assert payload["status"] == "error"
    assert payload["error_code"] == "payload_too_large"


def test_gateway_v1_http_service_payload_limit_depth_returns_413(tmp_path: Path) -> None:
    policy = gateway_http.GatewayHTTPPolicy(max_json_depth=3)
    app = gateway_http.create_app(runs_dir=tmp_path / "runs", policy=policy)
    payload = {
        "schema_version": "gateway_request_v1",
        "operation": "health",
        "payload": {"deep": {"a": {"b": {"c": 1}}}},
    }
    with TestClient(app) as client:
        response = client.post("/v1/gateway", json=payload)
    body = response.json()
    assert response.status_code == 413
    assert body["error_code"] == "payload_limit_exceeded"


def test_gateway_v1_http_service_payload_limit_string_returns_413(tmp_path: Path) -> None:
    policy = gateway_http.GatewayHTTPPolicy(max_string_length=8)
    app = gateway_http.create_app(runs_dir=tmp_path / "runs", policy=policy)
    payload = {
        "schema_version": "gateway_request_v1",
        "operation": "health",
        "payload": {"value": "0123456789"},
    }
    with TestClient(app) as client:
        response = client.post("/v1/gateway", json=payload)
    body = response.json()
    assert response.status_code == 413
    assert body["error_code"] == "payload_limit_exceeded"


def test_gateway_v1_http_service_payload_limit_array_returns_413(tmp_path: Path) -> None:
    policy = gateway_http.GatewayHTTPPolicy(max_array_items=2)
    app = gateway_http.create_app(runs_dir=tmp_path / "runs", policy=policy)
    payload = {
        "schema_version": "gateway_request_v1",
        "operation": "health",
        "payload": {"items": [1, 2, 3]},
    }
    with TestClient(app) as client:
        response = client.post("/v1/gateway", json=payload)
    body = response.json()
    assert response.status_code == 413
    assert body["error_code"] == "payload_limit_exceeded"


def test_gateway_v1_http_service_payload_limit_object_returns_413(tmp_path: Path) -> None:
    policy = gateway_http.GatewayHTTPPolicy(max_object_keys=2)
    app = gateway_http.create_app(runs_dir=tmp_path / "runs", policy=policy)
    payload = {
        "schema_version": "gateway_request_v1",
        "operation": "health",
        "payload": {"a": 1, "b": 2, "c": 3},
    }
    with TestClient(app) as client:
        response = client.post("/v1/gateway", json=payload)
    body = response.json()
    assert response.status_code == 413
    assert body["error_code"] == "payload_limit_exceeded"


def test_gateway_v1_http_service_timeout_returns_504(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _slow_dispatch(*args, **kwargs):
        time.sleep(0.05)
        return {
            "ok": True,
            "run_dir": tmp_path / "runs" / "slow",
            "run_payload": {},
            "response_payload": {
                "schema_version": "gateway_response_v1",
                "operation": "health",
                "status": "ok",
                "error_code": None,
                "error": None,
                "result": {"supported_operations": []},
                "artifacts": {"run_dir": "", "run_json": "", "child_runs": {}},
            },
        }

    monkeypatch.setattr(gateway_http, "run_gateway_request", _slow_dispatch)
    policy = gateway_http.GatewayHTTPPolicy(operation_timeout_sec=0.001)
    app = gateway_http.create_app(runs_dir=tmp_path / "runs", policy=policy)
    with TestClient(app) as client:
        response = client.post(
            "/v1/gateway",
            json={
                "schema_version": "gateway_request_v1",
                "operation": "health",
                "payload": {},
            },
        )
    payload = response.json()
    assert response.status_code == 504
    assert payload["status"] == "error"
    assert payload["error_code"] == "operation_timeout"


def test_gateway_v1_http_service_internal_error_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("sensitive boom")

    monkeypatch.setattr(gateway_http, "run_gateway_request", _boom)
    app = gateway_http.create_app(runs_dir=tmp_path / "runs")
    with TestClient(app) as client:
        response = client.post(
            "/v1/gateway",
            json={
                "schema_version": "gateway_request_v1",
                "operation": "health",
                "payload": {},
            },
        )
    payload = response.json()
    assert response.status_code == 500
    assert payload["status"] == "error"
    assert payload["error_code"] == "internal_error_sanitized"
    assert payload["error"] == "internal service error"
    assert "boom" not in payload["error"]
    assert "traceback" not in json.dumps(payload).lower()

    log_path = tmp_path / "runs" / "gateway_http_errors.jsonl"
    assert log_path.exists()
    last_log = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert last_log["error_code"] == "internal_error_sanitized"
    assert last_log["request_context"]["operation"] == "health"
    assert last_log["request_body_bytes"] > 0
    assert "RuntimeError: sensitive boom" in last_log["traceback"]
    assert last_log["redaction"]["checklist_version"] == "gateway_error_redaction_v1"
    assert last_log["redaction"]["applied"] is True
    assert "fields_redacted" in last_log["redaction"]
    assert last_log["retention_policy"] == {
        "artifact_retention_days": 14,
        "error_log_max_bytes": 1_048_576,
        "error_log_max_files": 5,
    }


def test_gateway_v1_http_service_internal_error_log_rotation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("token=very-long-secret-token-for-rotation-check")

    monkeypatch.setattr(gateway_http, "run_gateway_request", _boom)
    policy = gateway_http.GatewayHTTPPolicy(error_log_max_bytes=350, error_log_max_files=3)
    app = gateway_http.create_app(runs_dir=tmp_path / "runs", policy=policy)
    with TestClient(app) as client:
        for _ in range(12):
            response = client.post(
                "/v1/gateway",
                json={
                    "schema_version": "gateway_request_v1",
                    "operation": "health",
                    "payload": {},
                },
            )
            assert response.status_code == 500

    log_files = sorted((tmp_path / "runs").glob("gateway_http_errors*.jsonl"))
    assert 1 <= len(log_files) <= 3
    assert any(path.name.endswith(".1.jsonl") for path in log_files)


def test_gateway_v1_http_service_startup_retention_cleanup(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)

    old_time = datetime.now(timezone.utc) - timedelta(days=30)
    old_error_log = runs_dir / "gateway_http_errors.1.jsonl"
    old_error_log.write_text("{\"old\":true}\n", encoding="utf-8")
    old_gateway_run_dir = runs_dir / "20250101_010101-gateway-v1"
    old_gateway_run_dir.mkdir(parents=True)
    old_other_run_dir = runs_dir / "20250101_010101-phase-a"
    old_other_run_dir.mkdir(parents=True)

    _set_mtime(old_error_log, old_time)
    _set_mtime(old_gateway_run_dir, old_time)
    _set_mtime(old_other_run_dir, old_time)

    app = gateway_http.create_app(
        runs_dir=runs_dir,
        policy=gateway_http.GatewayHTTPPolicy(artifact_retention_days=14),
    )
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert not old_error_log.exists()
    assert not old_gateway_run_dir.exists()
    assert old_other_run_dir.exists()


def test_gateway_v1_http_service_contract_compat_with_cli(tmp_path: Path) -> None:
    request_payload = {
        "schema_version": "gateway_request_v1",
        "operation": "automation_dry_run",
        "payload": {"plan_json": str(_fixture_path("automation_plan_quest_book.json"))},
    }
    cli = run_gateway_request(
        request_payload=request_payload,
        runs_dir=tmp_path / "runs-cli",
        now=datetime(2026, 2, 27, 22, 30, 0, tzinfo=timezone.utc),
    )["response_payload"]

    app = gateway_http.create_app(runs_dir=tmp_path / "runs-http")
    with TestClient(app) as client:
        http_response = client.post("/v1/gateway", json=request_payload)
    http_payload = http_response.json()

    assert http_response.status_code == gateway_http.map_gateway_http_status(http_payload)
    for field in ("schema_version", "operation", "status", "error_code"):
        assert http_payload[field] == cli[field]
    assert http_payload["result"]["action_count"] == cli["result"]["action_count"]
    assert http_payload["result"]["step_count"] == cli["result"]["step_count"]
    assert http_payload["result"]["dry_run_only"] == cli["result"]["dry_run_only"]


def test_gateway_v1_http_service_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["gateway_v1_http_service.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        gateway_http.parse_args()
    assert exc.value.code == 0
