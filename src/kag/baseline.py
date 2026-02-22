from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
import re
from typing import Any, Mapping, Sequence

from src.rag.doc_contract import ensure_valid_doc

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_NAMESPACED_RE = re.compile(r"[a-z0-9_]+:[a-z0-9_./-]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize_entities(text: str) -> list[str]:
    namespaced = {token.lower() for token in _NAMESPACED_RE.findall(text.lower())}
    words: set[str] = set()
    for token in _WORD_RE.findall(text):
        normalized = token.strip().lower()
        if not normalized:
            continue
        if normalized in _STOPWORDS:
            continue
        if normalized.isdigit():
            continue
        if len(normalized) < 3:
            continue
        words.add(normalized)
        if "_" in normalized:
            for part in normalized.split("_"):
                if part and part not in _STOPWORDS and len(part) >= 3 and not part.isdigit():
                    words.add(part)
    all_tokens = namespaced | words
    return sorted(all_tokens)


def tokenize_kag_entities(text: str) -> list[str]:
    return _tokenize_entities(text)


def _extract_doc_entities(doc: Mapping[str, Any], *, max_entities_per_doc: int) -> list[str]:
    full_text = " ".join(
        [
            str(doc.get("title", "")),
            str(doc.get("text", "")),
            " ".join(str(tag) for tag in doc.get("tags", [])),
        ]
    )
    tokens = _tokenize_entities(full_text)
    if max_entities_per_doc <= 0:
        raise ValueError("max_entities_per_doc must be > 0.")
    return tokens[:max_entities_per_doc]


def build_kag_graph(
    docs: Sequence[Mapping[str, Any]],
    *,
    max_entities_per_doc: int = 128,
) -> dict[str, Any]:
    if max_entities_per_doc <= 0:
        raise ValueError("max_entities_per_doc must be > 0.")

    doc_nodes: list[dict[str, Any]] = []
    entity_nodes_map: dict[str, dict[str, Any]] = {}
    mention_edges: list[dict[str, Any]] = []
    cooccurs_counter: dict[tuple[str, str], int] = {}

    for doc in docs:
        ensure_valid_doc(doc)
        doc_id = str(doc["id"])
        doc_node_id = f"doc:{doc_id}"
        doc_nodes.append(
            {
                "id": doc_node_id,
                "doc_id": doc_id,
                "source": str(doc["source"]),
                "title": str(doc["title"]),
                "path": str(doc.get("path") or doc.get("__path") or ""),
            }
        )
        doc_entities = _extract_doc_entities(doc, max_entities_per_doc=max_entities_per_doc)

        for entity in doc_entities:
            entity_node_id = f"ent:{entity}"
            if entity not in entity_nodes_map:
                entity_nodes_map[entity] = {
                    "id": entity_node_id,
                    "entity": entity,
                    "label": entity,
                }
            mention_edges.append(
                {
                    "src": doc_node_id,
                    "dst": entity_node_id,
                    "type": "mentions",
                    "weight": 1,
                }
            )

        for left, right in combinations(doc_entities, 2):
            key = (left, right) if left < right else (right, left)
            cooccurs_counter[key] = cooccurs_counter.get(key, 0) + 1

    entity_nodes = sorted(entity_nodes_map.values(), key=lambda item: item["entity"])
    cooccurs_edges = [
        {
            "src": f"ent:{left}",
            "dst": f"ent:{right}",
            "type": "cooccurs",
            "weight": weight,
        }
        for (left, right), weight in sorted(cooccurs_counter.items())
    ]

    return {
        "schema_version": "kag_baseline_v1",
        "generated_at_utc": _utc_now(),
        "stats": {
            "doc_nodes": len(doc_nodes),
            "entity_nodes": len(entity_nodes),
            "mention_edges": len(mention_edges),
            "cooccurs_edges": len(cooccurs_edges),
        },
        "nodes": {
            "docs": doc_nodes,
            "entities": entity_nodes,
        },
        "edges": {
            "mentions": mention_edges,
            "cooccurs": cooccurs_edges,
        },
    }


def query_kag_graph(
    graph_payload: Mapping[str, Any],
    *,
    query: str,
    topk: int = 5,
) -> list[dict[str, Any]]:
    if topk <= 0:
        return []
    if not query.strip():
        return []

    doc_nodes = graph_payload.get("nodes", {}).get("docs", [])
    mention_edges = graph_payload.get("edges", {}).get("mentions", [])
    cooccurs_edges = graph_payload.get("edges", {}).get("cooccurs", [])
    if not isinstance(doc_nodes, list) or not isinstance(mention_edges, list) or not isinstance(cooccurs_edges, list):
        raise ValueError("Invalid KAG graph payload structure.")

    doc_by_node_id: dict[str, Mapping[str, Any]] = {}
    for item in doc_nodes:
        if isinstance(item, Mapping) and isinstance(item.get("id"), str):
            doc_by_node_id[str(item["id"])] = item

    entity_to_docs: dict[str, set[str]] = {}
    for edge in mention_edges:
        if not isinstance(edge, Mapping):
            continue
        src = str(edge.get("src", ""))
        dst = str(edge.get("dst", ""))
        if not src.startswith("doc:") or not dst.startswith("ent:"):
            continue
        entity = dst.removeprefix("ent:")
        entity_to_docs.setdefault(entity, set()).add(src)

    entity_neighbors: dict[str, dict[str, int]] = {}
    for edge in cooccurs_edges:
        if not isinstance(edge, Mapping):
            continue
        left = str(edge.get("src", ""))
        right = str(edge.get("dst", ""))
        if not left.startswith("ent:") or not right.startswith("ent:"):
            continue
        left_entity = left.removeprefix("ent:")
        right_entity = right.removeprefix("ent:")
        weight = int(edge.get("weight", 0))
        entity_neighbors.setdefault(left_entity, {})[right_entity] = weight
        entity_neighbors.setdefault(right_entity, {})[left_entity] = weight

    query_entities = _tokenize_entities(query)
    doc_scores: dict[str, float] = {}
    matched_entities_by_doc: dict[str, set[str]] = {}

    for entity in query_entities:
        matched_docs = entity_to_docs.get(entity, set())
        for doc_node_id in matched_docs:
            doc_scores[doc_node_id] = doc_scores.get(doc_node_id, 0.0) + 1.0
            matched_entities_by_doc.setdefault(doc_node_id, set()).add(entity)

        for neighbor_entity, cooccur_weight in entity_neighbors.get(entity, {}).items():
            for doc_node_id in entity_to_docs.get(neighbor_entity, set()):
                doc_scores[doc_node_id] = doc_scores.get(doc_node_id, 0.0) + (0.1 * float(cooccur_weight))

    ranked = sorted(doc_scores.items(), key=lambda item: item[1], reverse=True)[:topk]
    results: list[dict[str, Any]] = []
    for doc_node_id, score in ranked:
        doc_node = doc_by_node_id.get(doc_node_id)
        if doc_node is None:
            continue
        doc_id = str(doc_node.get("doc_id", "")).strip()
        if not doc_id:
            continue
        results.append(
            {
                "score": score,
                "id": doc_id,
                "source": str(doc_node.get("source", "")),
                "title": str(doc_node.get("title", "")),
                "matched_entities": sorted(matched_entities_by_doc.get(doc_node_id, set())),
                "citation": {
                    "id": doc_id,
                    "source": str(doc_node.get("source", "")),
                    "path": str(doc_node.get("path", "")),
                },
            }
        )
    return results
