"""Source-owned ATM10 world view with derived retrieval and relation handles."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


WORLD_KNOWLEDGE_SCHEMA_VERSION = "atm10_world_knowledge_v1"
WORLD_AUTHORITY_CEILING = "bounded_retrieval_not_general_world_truth"


def _source_handle(doc: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "document_id": str(doc.get("id", "")),
        "owner": str(doc.get("source", "")),
        "locator": str(doc.get("path") or doc.get("__path") or ""),
        "title": str(doc.get("title", "")),
        "created_at": str(doc.get("created_at", "")),
        "role": "authored_world_source",
    }


def build_world_knowledge_view(
    *,
    docs: Sequence[Mapping[str, Any]],
    retrieval: Sequence[Mapping[str, Any]],
    graph_results: Sequence[Mapping[str, Any]],
    citations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Describe owner sources and weaker derived views without replacing either."""

    sources = [_source_handle(doc) for doc in docs]
    source_ids = {item["document_id"] for item in sources}
    return_handles = [
        {
            "document_id": str(item.get("id", "")),
            "owner": str(item.get("source", "")),
            "locator": str(item.get("path", "")),
        }
        for item in citations
        if str(item.get("id", "")).strip()
    ]
    relation_context = [
        {
            "document_id": str(item.get("id", "")),
            "matched_entities": [
                str(entity) for entity in item.get("matched_entities", [])
            ],
            "score": item.get("score"),
            "role": "derived_relation_view",
        }
        for item in graph_results
        if str(item.get("id", "")).strip()
    ]
    handles_resolve = bool(return_handles) and all(
        handle["document_id"] in source_ids and handle["locator"]
        for handle in return_handles
    )
    ready = bool(retrieval) and handles_resolve

    return {
        "schema_version": WORLD_KNOWLEDGE_SCHEMA_VERSION,
        "authority": {
            "primary": "authored_world_sources",
            "derived": ["retrieval", "product_kag_relations"],
            "memory_role": "supporting_recall_only",
            "authority_ceiling": WORLD_AUTHORITY_CEILING,
        },
        "sources": sources,
        "derived_views": {
            "retrieval_result_count": len(retrieval),
            "relation_context": relation_context,
        },
        "return_handles": return_handles,
        "readiness": {
            "status": "bounded_ready" if ready else "degraded",
            "source_count": len(sources),
            "retrieval_result_count": len(retrieval),
            "return_handle_count": len(return_handles),
            "handles_resolve_to_sources": handles_resolve,
        },
        "claim_limit": (
            "Bounded readiness means this local query returned resolvable "
            "source handles; it does not establish source correctness, "
            "completeness, or general retrieval quality."
        ),
    }
