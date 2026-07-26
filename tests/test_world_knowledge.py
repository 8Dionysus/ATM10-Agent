from __future__ import annotations

from atm10_agent.world import recall


def test_world_knowledge_keeps_authored_sources_above_derived_views() -> None:
    world = recall(query="steel tools", topk=3, world_docs=None)
    knowledge = world["knowledge"]

    assert world["status"] == "ok"
    assert knowledge["schema_version"] == "atm10_world_knowledge_v1"
    assert knowledge["authority"] == {
        "primary": "authored_world_sources",
        "derived": ["retrieval", "product_kag_relations"],
        "memory_role": "supporting_recall_only",
        "authority_ceiling": "bounded_retrieval_not_general_world_truth",
    }
    assert knowledge["sources"]
    assert {item["role"] for item in knowledge["sources"]} == {
        "authored_world_source"
    }
    assert knowledge["return_handles"] == [
        {
            "document_id": item["id"],
            "owner": item["source"],
            "locator": item["path"],
        }
        for item in world["citations"]
    ]
    assert knowledge["readiness"]["status"] == "bounded_ready"
    assert knowledge["readiness"]["handles_resolve_to_sources"] is True


def test_world_knowledge_reports_degraded_readiness_without_false_handles() -> None:
    world = recall(query="xylophonic_unfindable_zz", topk=3, world_docs=None)
    knowledge = world["knowledge"]

    assert world["status"] == "degraded"
    assert knowledge["sources"]
    assert knowledge["return_handles"] == []
    assert knowledge["readiness"]["status"] == "degraded"
    assert knowledge["readiness"]["handles_resolve_to_sources"] is False
    assert "does not establish source correctness" in knowledge["claim_limit"]
