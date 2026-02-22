from __future__ import annotations

from typing import Any

import pytest

import src.kag.neo4j_backend as neo4j_backend


def test_sync_kag_graph_neo4j_batches_rows(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def _fake_run_cypher(*, url: str, database: str, user: str, password: str, statement: str, parameters, timeout_sec: float):
        calls.append(
            {
                "url": url,
                "database": database,
                "user": user,
                "password": password,
                "statement": statement,
                "parameters": parameters,
                "timeout_sec": timeout_sec,
            }
        )
        return []

    monkeypatch.setattr(neo4j_backend, "_run_cypher", _fake_run_cypher)

    graph = {
        "nodes": {
            "docs": [
                {"id": "doc:1", "doc_id": "1", "source": "s", "title": "t1", "path": "p1"},
                {"id": "doc:2", "doc_id": "2", "source": "s", "title": "t2", "path": "p2"},
            ],
            "entities": [
                {"id": "ent:a", "entity": "a", "label": "a"},
                {"id": "ent:b", "entity": "b", "label": "b"},
            ],
        },
        "edges": {
            "mentions": [
                {"src": "doc:1", "dst": "ent:a", "weight": 1},
                {"src": "doc:2", "dst": "ent:b", "weight": 1},
            ],
            "cooccurs": [{"src": "ent:a", "dst": "ent:b", "weight": 2}],
        },
    }

    summary = neo4j_backend.sync_kag_graph_neo4j(
        graph,
        url="http://localhost:7474",
        database="neo4j",
        user="neo4j",
        password="secret",
        timeout_sec=5.0,
        batch_size=1,
        reset_graph=True,
    )

    assert summary["doc_nodes"] == 2
    assert summary["entity_nodes"] == 2
    assert summary["mention_edges"] == 2
    assert summary["cooccurs_edges"] == 1
    assert summary["query_calls"] == len(calls)
    assert calls[0]["statement"].startswith("CREATE CONSTRAINT kag_doc_id")
    assert calls[2]["statement"].startswith("CREATE FULLTEXT INDEX kag_doc_fulltext")
    assert calls[3]["statement"].startswith("MATCH (n) WHERE n:Doc OR n:Entity")


def test_query_kag_neo4j_combines_direct_and_expansion_scores(monkeypatch) -> None:
    def _fake_run_cypher(*, url: str, database: str, user: str, password: str, statement: str, parameters, timeout_sec: float):
        entities = parameters["entities"]
        assert entities == ["steel", "tools"]
        if "direct_score" in statement:
            return [
                {
                    "doc_id": "quest:steel_tools",
                    "source": "ftbquests",
                    "title": "Steel Age",
                    "path": "docs.jsonl",
                    "matched_entities": ["steel", "tools"],
                    "direct_score": 2.0,
                }
            ]
        if "lexical_score" in statement:
            assert parameters["query_text"] == "steel tools"
            return [
                {
                    "doc_id": "quest:steel_tools",
                    "source": "ftbquests",
                    "title": "Steel Age",
                    "path": "docs.jsonl",
                    "matched_lexical": ["steel", "tools"],
                    "lexical_score": 2.0,
                    "fulltext_score": 4.0,
                }
            ]
        return [
            {
                "doc_id": "quest:steel_tools",
                "source": "ftbquests",
                "title": "Steel Age",
                "path": "docs.jsonl",
                "expansion_score": 0.2,
            },
            {
                "doc_id": "quest:mek",
                "source": "ftbquests",
                "title": "Mekanism",
                "path": "docs.jsonl",
                "expansion_score": 0.1,
            },
        ]

    monkeypatch.setattr(neo4j_backend, "_run_cypher", _fake_run_cypher)

    results = neo4j_backend.query_kag_neo4j(
        url="http://localhost:7474",
        database="neo4j",
        user="neo4j",
        password="secret",
        query="steel tools",
        topk=2,
        timeout_sec=5.0,
    )

    assert len(results) == 2
    assert results[0]["id"] == "quest:steel_tools"
    assert results[0]["score"] == pytest.approx(3.9)
    assert results[0]["matched_entities"] == ["steel", "tools"]
    assert results[1]["id"] == "quest:mek"
    assert results[1]["score"] == 0.1


def test_query_kag_neo4j_single_token_prefers_chapter_filename_match(monkeypatch) -> None:
    def _fake_run_cypher(*, url: str, database: str, user: str, password: str, statement: str, parameters, timeout_sec: float):
        entities = parameters["entities"]
        assert entities == ["star"]
        if "direct_score" in statement:
            return [
                {
                    "doc_id": "ftbquests:chapters/welcome.snbt",
                    "source": "ftbquests",
                    "title": "welcome",
                    "path": "docs.jsonl",
                    "matched_entities": ["star"],
                    "direct_score": 1.0,
                },
                {
                    "doc_id": "ftbquests:data.snbt",
                    "source": "ftbquests",
                    "title": "data",
                    "path": "docs.jsonl",
                    "matched_entities": ["star"],
                    "direct_score": 1.0,
                },
            ]
        if "CALL db.index.fulltext.queryNodes" in statement:
            assert parameters["query_text"] == "star"
            return [
                {
                    "doc_id": "ftbquests:chapters/achapter_2r_6the_atm_star.snbt",
                    "source": "ftbquests",
                    "title": "achapter_2r_6the_atm_star",
                    "path": "docs.jsonl",
                    "matched_lexical": ["star"],
                    "lexical_score": 1.0,
                    "fulltext_score": 0.0,
                },
                {
                    "doc_id": "ftbquests:chapters/chapter_2_the_star.snbt",
                    "source": "ftbquests",
                    "title": "chapter_2_the_star",
                    "path": "docs.jsonl",
                    "matched_lexical": ["star"],
                    "lexical_score": 1.0,
                    "fulltext_score": 0.0,
                },
            ]
        return []

    monkeypatch.setattr(neo4j_backend, "_run_cypher", _fake_run_cypher)

    results = neo4j_backend.query_kag_neo4j(
        url="http://localhost:7474",
        database="neo4j",
        user="neo4j",
        password="secret",
        query="star",
        topk=4,
        timeout_sec=5.0,
    )

    assert [item["id"] for item in results] == [
        "ftbquests:chapters/chapter_2_the_star.snbt",
        "ftbquests:chapters/achapter_2r_6the_atm_star.snbt",
        "ftbquests:chapters/welcome.snbt",
        "ftbquests:data.snbt",
    ]
    assert results[0]["score"] == pytest.approx(1.15)


def test_query_kag_neo4j_skips_scan_fallback_for_multi_token_with_direct_hits(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_run_cypher(*, url: str, database: str, user: str, password: str, statement: str, parameters, timeout_sec: float):
        calls.append(statement)
        entities = parameters["entities"]
        assert entities == ["dynamics", "integrated"]
        if "direct_score" in statement:
            return [
                {
                    "doc_id": "ftbquests:chapters/integrated_dynamics.snbt",
                    "source": "ftbquests",
                    "title": "integrated_dynamics",
                    "path": "docs.jsonl",
                    "matched_entities": ["dynamics", "integrated"],
                    "direct_score": 2.0,
                }
            ]
        if "CALL db.index.fulltext.queryNodes" in statement:
            return []
        if "MATCH (d:Doc)" in statement:
            raise AssertionError("scan fallback must not run when direct hits already exist for multi-token query")
        return []

    monkeypatch.setattr(neo4j_backend, "_run_cypher", _fake_run_cypher)

    results = neo4j_backend.query_kag_neo4j(
        url="http://localhost:7474",
        database="neo4j",
        user="neo4j",
        password="secret",
        query="integrated dynamics",
        topk=5,
        timeout_sec=5.0,
    )

    assert len(results) == 1
    assert results[0]["id"] == "ftbquests:chapters/integrated_dynamics.snbt"
    assert any("CALL db.index.fulltext.queryNodes" in statement for statement in calls)


def test_query_kag_neo4j_skips_scan_fallback_for_single_token_with_aligned_direct_hit(monkeypatch) -> None:
    def _fake_run_cypher(*, url: str, database: str, user: str, password: str, statement: str, parameters, timeout_sec: float):
        entities = parameters["entities"]
        assert entities == ["endgame"]
        if "direct_score" in statement:
            return [
                {
                    "doc_id": "ftbquests:chapters/mi_endgame.snbt",
                    "source": "ftbquests",
                    "title": "mi_endgame",
                    "path": "docs.jsonl",
                    "matched_entities": ["endgame"],
                    "direct_score": 1.0,
                }
            ]
        if "CALL db.index.fulltext.queryNodes" in statement:
            return []
        if "MATCH (d:Doc)" in statement:
            raise AssertionError("scan fallback must not run when single-token direct hit is lexically aligned")
        return []

    monkeypatch.setattr(neo4j_backend, "_run_cypher", _fake_run_cypher)

    results = neo4j_backend.query_kag_neo4j(
        url="http://localhost:7474",
        database="neo4j",
        user="neo4j",
        password="secret",
        query="mi endgame",
        topk=5,
        timeout_sec=5.0,
    )

    assert len(results) == 1
    assert results[0]["id"] == "ftbquests:chapters/mi_endgame.snbt"
