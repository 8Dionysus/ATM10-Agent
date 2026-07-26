"""File-backed world and product-KAG stage."""

from __future__ import annotations

from contextlib import nullcontext
from importlib import resources
from pathlib import Path
from typing import Any, ContextManager

from atm10_agent.kag import build_kag_graph, query_kag_graph
from atm10_agent.rag.retrieval import load_docs, retrieve_top_k


def _world_path(path: Path | None) -> ContextManager[Path]:
    if path is not None:
        return nullcontext(path)
    resource = resources.files("atm10_agent").joinpath("data/default_world.jsonl")
    return resources.as_file(resource)


def recall(*, query: str, topk: int, world_docs: Path | None) -> dict[str, Any]:
    with _world_path(world_docs) as docs_path:
        docs = load_docs(docs_path)
        retrieval = retrieve_top_k(query, docs, topk=topk, candidate_k=max(topk, 10))
        graph = build_kag_graph(docs)
        graph_results = query_kag_graph(graph, query=query, topk=topk)

    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in [*retrieval, *graph_results]:
        raw_citation = item.get("citation")
        if not isinstance(raw_citation, dict):
            continue
        citation = {
            "id": str(raw_citation.get("id", "")),
            "source": str(raw_citation.get("source", "")),
            "path": str(raw_citation.get("path", "")),
        }
        key = (citation["id"], citation["source"])
        if not citation["id"] or key in seen:
            continue
        seen.add(key)
        citations.append(citation)

    degraded = not retrieval
    return {
        "schema_version": "atm10_world_v1",
        "status": "degraded" if degraded else "ok",
        "degraded": degraded,
        "degradation_reason": "no_retrieval_match" if degraded else None,
        "backend": "file",
        "query": query,
        "document_count": len(docs),
        "retrieval": retrieval,
        "product_kag": graph_results,
        "citations": citations,
    }
