from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import testclient as fastapi_testclient

import scripts.gateway_v1_http_smoke as gateway_http_smoke


def test_gateway_v1_http_smoke_core_ok(tmp_path: Path) -> None:
    summary_path = tmp_path / "runs" / "ci-smoke-gateway-http-core" / "gateway_http_smoke_summary.json"
    result = gateway_http_smoke.run_gateway_v1_http_smoke(
        scenario="core",
        runs_dir=tmp_path / "runs" / "ci-smoke-gateway-http-core",
        summary_json=summary_path,
        now=datetime(2026, 2, 27, 23, 0, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is True
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["status"] == "ok"
    assert summary_payload["profile"] == "baseline_first"
    assert summary_payload["surface"] == "http"
    assert summary_payload["scenario"] == "core"
    assert summary_payload["started_at_utc"]
    assert summary_payload["finished_at_utc"]
    assert summary_payload["duration_ms"] >= 0
    assert summary_payload["request_count"] == 3
    assert summary_payload["failed_requests_count"] == 0
    assert summary_payload["latency_p50_ms"] is not None
    assert summary_payload["latency_p95_ms"] is not None
    assert summary_payload["latency_max_ms"] is not None
    assert summary_payload["error_buckets"]["none"] == 3
    assert all(item["latency_ms"] >= 0 for item in summary_payload["requests"])
    assert all(item["ok"] is True for item in summary_payload["requests"])
    assert all(item["http_status"] == item["expected_http_status"] for item in summary_payload["requests"])


def test_gateway_v1_http_smoke_automation_ok(tmp_path: Path) -> None:
    summary_path = (
        tmp_path / "runs" / "ci-smoke-gateway-http-automation" / "gateway_http_smoke_summary.json"
    )
    result = gateway_http_smoke.run_gateway_v1_http_smoke(
        scenario="automation",
        runs_dir=tmp_path / "runs" / "ci-smoke-gateway-http-automation",
        summary_json=summary_path,
        now=datetime(2026, 2, 27, 23, 1, 0, tzinfo=timezone.utc),
    )
    assert result["ok"] is True
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["status"] == "ok"
    assert summary_payload["profile"] == "baseline_first"
    assert summary_payload["surface"] == "http"
    assert summary_payload["scenario"] == "automation"
    assert summary_payload["started_at_utc"]
    assert summary_payload["finished_at_utc"]
    assert summary_payload["duration_ms"] >= 0
    assert summary_payload["request_count"] == 1
    assert summary_payload["failed_requests_count"] == 0
    assert summary_payload["latency_p50_ms"] is not None
    assert summary_payload["latency_p95_ms"] is not None
    assert summary_payload["latency_max_ms"] is not None
    assert summary_payload["error_buckets"]["none"] == 1
    assert summary_payload["requests"][0]["latency_ms"] >= 0
    assert summary_payload["requests"][0]["operation"] == "automation_dry_run"
    assert summary_payload["requests"][0]["http_status"] == summary_payload["requests"][0]["expected_http_status"]


def test_gateway_v1_http_smoke_hybrid_ok(tmp_path: Path) -> None:
    summary_path = tmp_path / "runs" / "ci-smoke-gateway-http-hybrid" / "gateway_http_smoke_summary.json"
    result = gateway_http_smoke.run_gateway_v1_http_smoke(
        scenario="hybrid",
        runs_dir=tmp_path / "runs" / "ci-smoke-gateway-http-hybrid",
        summary_json=summary_path,
        now=datetime(2026, 2, 27, 23, 1, 30, tzinfo=timezone.utc),
    )
    assert result["ok"] is True
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["status"] == "ok"
    assert summary_payload["profile"] == "baseline_first"
    assert summary_payload["surface"] == "http"
    assert summary_payload["scenario"] == "hybrid"
    assert summary_payload["request_count"] == 1
    assert summary_payload["failed_requests_count"] == 0
    assert summary_payload["error_buckets"]["none"] == 1
    assert summary_payload["requests"][0]["operation"] == "hybrid_query"
    assert summary_payload["requests"][0]["http_status"] == summary_payload["requests"][0]["expected_http_status"]


def test_gateway_v1_http_smoke_combo_a_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary_path = tmp_path / "runs" / "ci-smoke-gateway-http-combo-a" / "gateway_http_smoke_summary.json"

    def _fake_seed(**kwargs):
        run_dir = kwargs["runs_dir"] / "seed-run"
        run_dir.mkdir(parents=True, exist_ok=True)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": {"status": "ok"},
            "summary_payload": {
                "qdrant": {"collection": "atm10_combo_a_fixture_gateway_http_smoke", "vector_size": 64},
                "neo4j": {"dataset_tag": "atm10_combo_a_fixture_gateway_http_smoke"},
                "paths": {"run_dir": str(run_dir)},
            },
        }

    class _FakeResponse:
        def __init__(self, operation: str) -> None:
            self.status_code = 200
            self._operation = operation

        def json(self) -> dict[str, object]:
            return {
                "schema_version": "gateway_response_v1",
                "operation": self._operation,
                "status": "ok",
                "error_code": None,
                "result": {},
                "artifacts": {
                    "run_dir": str(tmp_path / "gateway-http-runs" / self._operation),
                    "run_json": str(tmp_path / "gateway-http-runs" / self._operation / "run.json"),
                },
            }

    class _FakeTestClient:
        def __init__(self, app) -> None:
            self.app = app

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, path: str, json: dict[str, object]):
            assert path == "/v1/gateway"
            return _FakeResponse(str(json["operation"]))

    monkeypatch.setattr(gateway_http_smoke, "seed_combo_a_fixture_data", _fake_seed)
    monkeypatch.setattr(gateway_http_smoke, "create_app", lambda **kwargs: {"app": "ok", **kwargs})
    monkeypatch.setattr(gateway_http_smoke, "map_gateway_http_status", lambda payload: 200)
    monkeypatch.setattr(fastapi_testclient, "TestClient", _FakeTestClient)

    result = gateway_http_smoke.run_gateway_v1_http_smoke(
        scenario="combo_a",
        runs_dir=tmp_path / "runs" / "ci-smoke-gateway-http-combo-a",
        summary_json=summary_path,
        combo_a_neo4j_password="secret",
        now=datetime(2026, 2, 27, 23, 1, 45, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["status"] == "ok"
    assert summary_payload["profile"] == "combo_a"
    assert summary_payload["surface"] == "http"
    assert summary_payload["scenario"] == "combo_a"
    assert summary_payload["request_count"] == 4
    assert summary_payload["failed_requests_count"] == 0
    assert summary_payload["combo_a_seed"]["qdrant"]["collection"] == "atm10_combo_a_fixture_gateway_http_smoke"
    assert summary_payload["combo_a_seed"]["neo4j"]["dataset_tag"] == "atm10_combo_a_fixture_gateway_http_smoke"
    assert [item["operation"] for item in summary_payload["requests"]] == [
        "health",
        "retrieval_query",
        "kag_query",
        "hybrid_query",
    ]


def test_gateway_v1_http_smoke_invalid_scenario_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        gateway_http_smoke.run_gateway_v1_http_smoke(
            scenario="unsupported",
            runs_dir=tmp_path / "runs",
            now=datetime(2026, 2, 27, 23, 2, 0, tzinfo=timezone.utc),
        )


def test_gateway_v1_http_smoke_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["gateway_v1_http_smoke.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        gateway_http_smoke.parse_args()
    assert exc.value.code == 0
