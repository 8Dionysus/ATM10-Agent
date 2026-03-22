from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.kag import build_kag_graph, query_kag_graph
from src.rag.retrieval import load_docs, retrieve_top_k

HYBRID_QUERY_RESULTS_SCHEMA = "hybrid_query_results_v1"
DEFAULT_HYBRID_PLANNER_MODE = "retrieval_first_kag_expansion"
DEFAULT_RRF_K = 60


def _citation_id(item: Mapping[str, Any]) -> str:
    citation = item.get("citation")
    if isinstance(citation, Mapping):
        citation_id = str(citation.get("id", "")).strip()
        if citation_id:
            return citation_id
    return str(item.get("id", "")).strip()


def _citation_source(item: Mapping[str, Any]) -> str:
    citation = item.get("citation")
    if isinstance(citation, Mapping):
        citation_source = str(citation.get("source", "")).strip()
        if citation_source:
            return citation_source
    return str(item.get("source", "")).strip()


def _citation_path(item: Mapping[str, Any]) -> str:
    citation = item.get("citation")
    if isinstance(citation, Mapping):
        citation_path = str(citation.get("path", "")).strip()
        if citation_path:
            return citation_path
    return ""


def _planner_source(retrieval_rank: int | None, kag_rank: int | None) -> str:
    if retrieval_rank is not None and kag_rank is not None:
        return "retrieval_and_kag"
    if retrieval_rank is not None:
        return "retrieval_only"
    return "kag_only"


def merge_hybrid_results(
    retrieval_results: list[Mapping[str, Any]],
    kag_results: list[Mapping[str, Any]],
    *,
    topk: int,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[dict[str, Any]]:
    if topk <= 0:
        return []

    rows: dict[str, dict[str, Any]] = {}
    for rank, item in enumerate(retrieval_results, start=1):
        doc_id = _citation_id(item)
        if not doc_id:
            continue
        row = rows.setdefault(
            doc_id,
            {
                "id": doc_id,
                "source": _citation_source(item),
                "title": str(item.get("title", "")),
                "text": item.get("text"),
                "citation": {
                    "id": doc_id,
                    "source": _citation_source(item),
                    "path": _citation_path(item),
                },
                "retrieval_rank": None,
                "kag_rank": None,
                "retrieval_score": None,
                "kag_score": None,
                "matched_entities": [],
            },
        )
        row["retrieval_rank"] = rank
        row["retrieval_score"] = item.get("score")
        if not str(row.get("title", "")).strip():
            row["title"] = str(item.get("title", ""))
        if row.get("text") in (None, ""):
            row["text"] = item.get("text")
        citation = row.get("citation")
        citation = citation if isinstance(citation, dict) else {}
        if not citation.get("source"):
            citation["source"] = _citation_source(item)
        if not citation.get("path"):
            citation["path"] = _citation_path(item)
        row["citation"] = citation

    for rank, item in enumerate(kag_results, start=1):
        doc_id = _citation_id(item)
        if not doc_id:
            continue
        row = rows.setdefault(
            doc_id,
            {
                "id": doc_id,
                "source": _citation_source(item),
                "title": str(item.get("title", "")),
                "text": None,
                "citation": {
                    "id": doc_id,
                    "source": _citation_source(item),
                    "path": _citation_path(item),
                },
                "retrieval_rank": None,
                "kag_rank": None,
                "retrieval_score": None,
                "kag_score": None,
                "matched_entities": [],
            },
        )
        row["kag_rank"] = rank
        row["kag_score"] = item.get("score")
        if not str(row.get("title", "")).strip():
            row["title"] = str(item.get("title", ""))
        citation = row.get("citation")
        citation = citation if isinstance(citation, dict) else {}
        if not citation.get("source"):
            citation["source"] = _citation_source(item)
        if not citation.get("path"):
            citation["path"] = _citation_path(item)
        row["citation"] = citation
        matched_entities = item.get("matched_entities")
        if isinstance(matched_entities, list):
            row["matched_entities"] = [str(value) for value in matched_entities]

    merged: list[dict[str, Any]] = []
    for doc_id, row in rows.items():
        retrieval_rank = row.get("retrieval_rank")
        kag_rank = row.get("kag_rank")
        fusion_score = 0.0
        if isinstance(retrieval_rank, int):
            fusion_score += 1.0 / float(rrf_k + retrieval_rank)
        if isinstance(kag_rank, int):
            fusion_score += 1.0 / float(rrf_k + kag_rank)

        merged.append(
            {
                "rrf_score": round(fusion_score, 8),
                "id": doc_id,
                "source": row.get("source"),
                "title": row.get("title"),
                "text": row.get("text"),
                "citation": row.get("citation"),
                "retrieval_rank": retrieval_rank,
                "kag_rank": kag_rank,
                "retrieval_score": row.get("retrieval_score"),
                "kag_score": row.get("kag_score"),
                "planner_source": _planner_source(retrieval_rank, kag_rank),
                "matched_entities": row.get("matched_entities") or [],
            }
        )

    merged.sort(
        key=lambda item: (
            -float(item["rrf_score"]),
            item["retrieval_rank"] if isinstance(item.get("retrieval_rank"), int) else 10_000,
            item["kag_rank"] if isinstance(item.get("kag_rank"), int) else 10_000,
            str(item.get("id", "")),
        )
    )
    return merged[:topk]


def execute_hybrid_baseline_query(
    *,
    query: str,
    docs_path: Path,
    topk: int,
    candidate_k: int,
    reranker: str,
    reranker_model: str,
    reranker_runtime: str,
    reranker_device: str,
    reranker_max_length: int,
    max_entities_per_doc: int,
) -> dict[str, Any]:
    if not str(query).strip():
        raise ValueError("query must be non-empty string")
    if topk <= 0:
        raise ValueError("topk must be >= 1")
    if candidate_k <= 0:
        raise ValueError("candidate_k must be >= 1")
    if reranker_max_length <= 0:
        raise ValueError("reranker_max_length must be >= 1")
    if max_entities_per_doc <= 0:
        raise ValueError("max_entities_per_doc must be >= 1")

    docs = load_docs(docs_path)
    retrieval_results = retrieve_top_k(
        query,
        docs,
        topk=topk,
        candidate_k=candidate_k,
        reranker=reranker,
        reranker_model=reranker_model,
        reranker_max_length=reranker_max_length,
        reranker_runtime=reranker_runtime,
        reranker_device=reranker_device,
    )
    retrieval_results_payload = [dict(item) for item in retrieval_results]
    retrieval_results_count = len(retrieval_results_payload)

    if retrieval_results_count == 0:
        return {
            "schema_version": HYBRID_QUERY_RESULTS_SCHEMA,
            "planner_mode": DEFAULT_HYBRID_PLANNER_MODE,
            "planner_status": "retrieval_empty",
            "degraded": False,
            "warnings": [],
            "retrieval_results": retrieval_results_payload,
            "retrieval_results_count": 0,
            "kag_results": [],
            "kag_results_count": 0,
            "merged_results": [],
            "results_count": 0,
            "graph_payload": None,
        }

    kag_results_payload: list[dict[str, Any]] = []
    warnings: list[str] = []
    degraded = False
    planner_status = "hybrid_merged"
    graph_payload: dict[str, Any] | None = None

    try:
        graph_payload = build_kag_graph(docs, max_entities_per_doc=max_entities_per_doc)
        kag_results = query_kag_graph(graph_payload, query=query, topk=topk)
        kag_results_payload = [dict(item) for item in kag_results]
        if not kag_results_payload:
            degraded = True
            planner_status = "retrieval_only_fallback"
            warnings.append("kag stage returned no expansion results; using retrieval-only fallback")
    except Exception as exc:
        degraded = True
        planner_status = "retrieval_only_fallback"
        warnings.append(f"kag stage fallback: {exc}")

    merged_results = merge_hybrid_results(
        retrieval_results_payload,
        [] if degraded else kag_results_payload,
        topk=topk,
    )
    return {
        "schema_version": HYBRID_QUERY_RESULTS_SCHEMA,
        "planner_mode": DEFAULT_HYBRID_PLANNER_MODE,
        "planner_status": planner_status,
        "degraded": degraded,
        "warnings": warnings,
        "retrieval_results": retrieval_results_payload,
        "retrieval_results_count": retrieval_results_count,
        "kag_results": [] if degraded else kag_results_payload,
        "kag_results_count": 0 if degraded else len(kag_results_payload),
        "merged_results": merged_results,
        "results_count": len(merged_results),
        "graph_payload": graph_payload,
    }
