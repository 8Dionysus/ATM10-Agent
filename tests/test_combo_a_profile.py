from __future__ import annotations

import src.agent_core.combo_a_profile as combo_a_profile


def test_profile_backends_and_docs_path_requirement() -> None:
    assert combo_a_profile.profile_backends("baseline_first") == ("in_memory", "file")
    assert combo_a_profile.profile_backends("combo_a") == ("qdrant", "neo4j")
    assert combo_a_profile.docs_path_required(retrieval_backend="in_memory", kag_backend="file") is True
    assert combo_a_profile.docs_path_required(retrieval_backend="qdrant", kag_backend="neo4j") is False


def test_combo_a_fixture_scope_helpers_normalize_scope() -> None:
    assert combo_a_profile.combo_a_fixture_collection("Gateway Smoke") == "atm10_combo_a_fixture_gateway_smoke"
    assert combo_a_profile.combo_a_fixture_dataset_tag("HTTP-Smoke") == "atm10_combo_a_fixture_http_smoke"


def test_probe_qdrant_service_not_configured() -> None:
    payload = combo_a_profile.probe_qdrant_service(qdrant_url=None, timeout_sec=0.1)

    assert payload["service_name"] == "qdrant"
    assert payload["configured"] is False
    assert payload["status"] == "not_configured"


def test_probe_neo4j_service_reports_missing_auth_when_url_is_configured(monkeypatch) -> None:
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    payload = combo_a_profile.probe_neo4j_service(
        neo4j_url="http://127.0.0.1:7474",
        neo4j_database="neo4j",
        neo4j_user="neo4j",
        neo4j_password=None,
        timeout_sec=0.1,
    )

    assert payload["service_name"] == "neo4j"
    assert payload["configured"] is True
    assert payload["status"] == "missing_auth"
    assert "Neo4j password is required" in str(payload["error"])
