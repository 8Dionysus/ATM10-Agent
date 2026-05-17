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


def test_seed_combo_a_fixture_data_can_split_qdrant_and_neo4j_docs(monkeypatch, tmp_path) -> None:
    loaded_paths: list[object] = []
    captured: dict[str, object] = {}

    monkeypatch.setattr(combo_a_profile, "resolve_neo4j_password", lambda password: "secret")

    def fake_load_docs(path):
        loaded_paths.append(path)
        return [{"id": str(path), "text": f"text from {path}"}]

    def fake_ingest_docs_qdrant(docs, **kwargs):
        captured["qdrant_docs"] = docs
        return {"docs_ingested": len(docs)}

    def fake_build_kag_graph(docs, *, max_entities_per_doc):
        captured["neo4j_docs"] = docs
        return {"nodes": {"docs": []}, "edges": {}}

    def fake_sync_kag_graph_neo4j(graph_payload, **kwargs):
        captured["graph_payload"] = graph_payload
        return {"doc_nodes": 0}

    monkeypatch.setattr(combo_a_profile, "load_docs", fake_load_docs)
    monkeypatch.setattr(combo_a_profile, "ingest_docs_qdrant", fake_ingest_docs_qdrant)
    monkeypatch.setattr(combo_a_profile, "build_kag_graph", fake_build_kag_graph)
    monkeypatch.setattr(combo_a_profile, "sync_kag_graph_neo4j", fake_sync_kag_graph_neo4j)

    result = combo_a_profile.seed_combo_a_fixture_data(
        scope="cross_service_suite",
        docs_path=tmp_path / "legacy.jsonl",
        qdrant_docs_path=tmp_path / "retrieval.jsonl",
        neo4j_docs_path=tmp_path / "kag.jsonl",
        runs_dir=tmp_path / "runs",
        neo4j_password="secret",
    )

    assert result["ok"] is True
    assert loaded_paths == [tmp_path / "retrieval.jsonl", tmp_path / "kag.jsonl"]
    assert captured["qdrant_docs"] == [{"id": str(tmp_path / "retrieval.jsonl"), "text": f"text from {tmp_path / 'retrieval.jsonl'}"}]
    assert captured["neo4j_docs"] == [{"id": str(tmp_path / "kag.jsonl"), "text": f"text from {tmp_path / 'kag.jsonl'}"}]


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
