from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib import error, request

from src.rag.doc_contract import ensure_valid_doc

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_ALLOWED_RERANKERS = {"none", "qwen3"}
_DEFAULT_QWEN3_RERANKER = "Qwen/Qwen3-Reranker-0.6B"


def _tokenize(value: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(value)}


def _normalize_reranker(reranker: str) -> str:
    normalized = reranker.strip().lower()
    if normalized not in _ALLOWED_RERANKERS:
        raise ValueError(f"Unsupported reranker: {reranker!r}. Expected one of {_ALLOWED_RERANKERS}.")
    return normalized


def _resolve_candidate_k(*, topk: int, candidate_k: int | None) -> int:
    required = max(topk, 0)
    if required == 0:
        return 0
    if candidate_k is None:
        return required
    if candidate_k <= 0:
        raise ValueError("candidate_k must be positive.")
    return candidate_k


def _vectorize_text(value: str, *, size: int) -> list[float]:
    if size <= 0:
        raise ValueError("Vector size must be positive.")

    vector = [0.0] * size
    for token in _tokenize(value):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], byteorder="big", signed=False) % size
        vector[index] += 1.0

    norm = sum(component * component for component in vector) ** 0.5
    if norm > 0:
        return [component / norm for component in vector]
    return vector


def _point_id_from_doc_id(doc_id: str) -> int:
    digest = hashlib.sha1(doc_id.encode("utf-8")).digest()
    point_id = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return point_id or 1


def _qdrant_base_url(*, host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _qdrant_url(*, host: str, port: int, path: str) -> str:
    safe_path = path if path.startswith("/") else f"/{path}"
    return f"{_qdrant_base_url(host=host, port=port)}{safe_path}"


def _qdrant_request(
    *,
    method: str,
    url: str,
    payload: Mapping[str, Any] | None,
    timeout_sec: float,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(
        url=url,
        data=body,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qdrant request failed: {method} {url} HTTP {exc.code}: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Qdrant request failed: {method} {url}: {exc.reason}") from exc

    if not raw:
        return {}

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Unexpected Qdrant response payload type from {url}.")
    return parsed


def _resolve_jsonl_paths(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(path for path in input_path.glob("*.jsonl") if path.is_file())
    return []


def load_docs(input_path: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    jsonl_paths = _resolve_jsonl_paths(input_path)
    if not jsonl_paths:
        raise FileNotFoundError(f"No JSONL files found for input path: {input_path}")

    for jsonl_path in jsonl_paths:
        for line_no, raw_line in enumerate(jsonl_path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {jsonl_path}:{line_no}") from exc

            if not isinstance(doc, dict):
                raise ValueError(f"Expected JSON object at {jsonl_path}:{line_no}")
            ensure_valid_doc(doc)
            doc["__path"] = str(jsonl_path)
            docs.append(doc)
    return docs


def _searchable_text(doc: Mapping[str, Any]) -> str:
    return " ".join(
        [
            str(doc.get("title", "")),
            str(doc.get("text", "")),
            " ".join(str(tag) for tag in doc.get("tags", [])),
        ]
    )


def _first_stage_rank(
    query: str,
    docs: Sequence[Mapping[str, Any]],
) -> list[tuple[float, Mapping[str, Any]]]:
    query_tokens = _tokenize(query)
    scored: list[tuple[int, int, Mapping[str, Any]]] = []

    for index, doc in enumerate(docs):
        searchable = _searchable_text(doc)
        score = len(query_tokens & _tokenize(searchable)) if query_tokens else 0
        if score > 0:
            scored.append((score, -index, doc))

    scored.sort(reverse=True)
    return [(float(score), doc) for score, _, doc in scored]


def _result_from_doc(*, doc: Mapping[str, Any], score: float) -> dict[str, Any]:
    citation_path = str(doc.get("path") or doc.get("__path") or "")
    return {
        "score": score,
        "id": str(doc["id"]),
        "source": str(doc["source"]),
        "title": str(doc["title"]),
        "text": str(doc["text"]),
        "citation": {
            "id": str(doc["id"]),
            "source": str(doc["source"]),
            "path": citation_path,
        },
    }


@lru_cache(maxsize=2)
def _load_qwen3_reranker(model_id: str) -> tuple[Any, Any, Any]:
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "reranker=qwen3 requires optional dependencies. "
            "Install them manually, for example: pip install transformers torch"
        ) from exc

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForSequenceClassification.from_pretrained(model_id, trust_remote_code=True)
    model.eval()
    return tokenizer, model, torch


def _rerank_candidates_qwen3(
    query: str,
    candidate_docs: Sequence[Mapping[str, Any]],
    *,
    model_id: str,
    max_length: int,
) -> list[tuple[float, Mapping[str, Any]]]:
    if not candidate_docs:
        return []
    if max_length <= 0:
        raise ValueError("reranker_max_length must be positive.")

    tokenizer, model, torch = _load_qwen3_reranker(model_id)
    passages = [
        "\n".join(
            part
            for part in (
                str(doc.get("title", "")).strip(),
                str(doc.get("text", "")).strip(),
            )
            if part
        )
        for doc in candidate_docs
    ]
    queries = [query] * len(passages)

    inputs = tokenizer(
        queries,
        passages,
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits
    dim = logits.dim() if hasattr(logits, "dim") else 1
    score_tensor = logits[:, 0] if dim == 2 else logits
    scores = [float(value) for value in score_tensor.detach().cpu().tolist()]

    ranked = sorted(zip(scores, candidate_docs), key=lambda pair: pair[0], reverse=True)
    return ranked


def retrieve_top_k(
    query: str,
    docs: Sequence[Mapping[str, Any]],
    *,
    topk: int = 5,
    candidate_k: int | None = None,
    reranker: str = "none",
    reranker_model: str = _DEFAULT_QWEN3_RERANKER,
    reranker_max_length: int = 1024,
) -> list[dict[str, Any]]:
    topk_limit = max(topk, 0)
    if topk_limit == 0:
        return []

    reranker_name = _normalize_reranker(reranker)
    candidate_limit = _resolve_candidate_k(topk=topk_limit, candidate_k=candidate_k)
    ranked_first_stage = _first_stage_rank(query, docs)
    if not ranked_first_stage:
        return []

    candidate_pool = ranked_first_stage[:candidate_limit]
    if reranker_name == "none":
        return [_result_from_doc(doc=doc, score=score) for score, doc in candidate_pool[:topk_limit]]

    reranked = _rerank_candidates_qwen3(
        query,
        [doc for _, doc in candidate_pool],
        model_id=reranker_model,
        max_length=reranker_max_length,
    )
    return [_result_from_doc(doc=doc, score=score) for score, doc in reranked[:topk_limit]]


def _build_qdrant_point(doc: Mapping[str, Any], *, vector_size: int) -> dict[str, Any]:
    ensure_valid_doc(doc)
    payload = {
        "id": str(doc["id"]),
        "source": str(doc["source"]),
        "title": str(doc["title"]),
        "text": str(doc["text"]),
        "path": str(doc.get("path") or doc.get("__path") or ""),
    }
    vector = _vectorize_text(_searchable_text(doc), size=vector_size)
    return {
        "id": _point_id_from_doc_id(str(doc["id"])),
        "vector": vector,
        "payload": payload,
    }


def ingest_docs_qdrant(
    docs: Sequence[Mapping[str, Any]],
    *,
    collection: str,
    host: str = "127.0.0.1",
    port: int = 6333,
    vector_size: int = 64,
    timeout_sec: float = 10.0,
    batch_size: int = 128,
) -> dict[str, Any]:
    if not collection.strip():
        raise ValueError("Collection name must be non-empty.")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive.")

    base = _qdrant_base_url(host=host, port=port)
    collection_created = True
    try:
        _qdrant_request(
            method="PUT",
            url=f"{base}/collections/{collection}",
            payload={"vectors": {"size": vector_size, "distance": "Cosine"}},
            timeout_sec=timeout_sec,
        )
    except RuntimeError as exc:
        message = str(exc).lower()
        if "http 409" in message and "already exists" in message:
            collection_created = False
        else:
            raise

    points = [_build_qdrant_point(doc, vector_size=vector_size) for doc in docs]
    upsert_calls = 0
    for start in range(0, len(points), batch_size):
        chunk = points[start : start + batch_size]
        _qdrant_request(
            method="PUT",
            url=f"{base}/collections/{collection}/points?wait=true",
            payload={"points": chunk},
            timeout_sec=timeout_sec,
        )
        upsert_calls += 1

    return {
        "collection": collection,
        "host": host,
        "port": port,
        "vector_size": vector_size,
        "collection_created": collection_created,
        "docs_ingested": len(points),
        "upsert_calls": upsert_calls,
    }


def retrieve_top_k_qdrant(
    query: str,
    *,
    collection: str,
    topk: int = 5,
    candidate_k: int | None = None,
    reranker: str = "none",
    reranker_model: str = _DEFAULT_QWEN3_RERANKER,
    reranker_max_length: int = 1024,
    host: str = "127.0.0.1",
    port: int = 6333,
    vector_size: int = 64,
    timeout_sec: float = 10.0,
) -> list[dict[str, Any]]:
    topk_limit = max(topk, 0)
    if topk_limit == 0:
        return []
    if not collection.strip():
        raise ValueError("Collection name must be non-empty.")
    reranker_name = _normalize_reranker(reranker)
    candidate_limit = _resolve_candidate_k(topk=topk_limit, candidate_k=candidate_k)

    vector = _vectorize_text(query, size=vector_size)
    base = _qdrant_base_url(host=host, port=port)
    response = _qdrant_request(
        method="POST",
        url=f"{base}/collections/{collection}/points/search",
        payload={
            "vector": vector,
            "limit": candidate_limit,
            "with_payload": True,
        },
        timeout_sec=timeout_sec,
    )
    raw_hits = response.get("result")
    if not isinstance(raw_hits, list):
        raise RuntimeError("Unexpected Qdrant search response: missing result list.")

    first_stage_results: list[dict[str, Any]] = []
    for raw_hit in raw_hits:
        if not isinstance(raw_hit, Mapping):
            continue
        payload = raw_hit.get("payload")
        if not isinstance(payload, Mapping):
            continue
        if not payload.get("id") or not payload.get("source"):
            continue
        if not payload.get("title") or not payload.get("text"):
            continue
        score = float(raw_hit.get("score", 0.0))
        first_stage_results.append(_result_from_doc(doc=payload, score=score))

    if reranker_name == "none":
        return first_stage_results[:topk_limit]

    candidate_docs: list[dict[str, Any]] = []
    for item in first_stage_results:
        candidate_docs.append(
            {
                "id": item["id"],
                "source": item["source"],
                "title": item["title"],
                "text": item["text"],
                "path": item["citation"]["path"],
            }
        )
    reranked = _rerank_candidates_qwen3(
        query,
        candidate_docs,
        model_id=reranker_model,
        max_length=reranker_max_length,
    )
    return [_result_from_doc(doc=doc, score=score) for score, doc in reranked[:topk_limit]]
