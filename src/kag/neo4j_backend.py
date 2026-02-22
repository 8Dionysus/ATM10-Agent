from __future__ import annotations

import base64
import json
from typing import Any, Mapping, Sequence
from urllib import error, request

from src.kag.baseline import tokenize_kag_entities


def _neo4j_commit_url(*, url: str, database: str) -> str:
    safe_url = url.rstrip("/")
    db_name = database.strip() or "neo4j"
    return f"{safe_url}/db/{db_name}/tx/commit"


def _auth_header(*, user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _doc_key_from_doc_id(doc_id: str) -> str:
    normalized = doc_id.strip().lower()
    if ":" not in normalized:
        return normalized
    return normalized.split(":", 1)[1]


def _neo4j_cypher_json(
    *,
    url: str,
    database: str,
    user: str,
    password: str,
    statements: Sequence[Mapping[str, Any]],
    timeout_sec: float,
) -> dict[str, Any]:
    commit_url = _neo4j_commit_url(url=url, database=database)
    payload = {"statements": list(statements)}
    req = request.Request(
        url=commit_url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": _auth_header(user=user, password=password),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Neo4j request failed: HTTP {exc.code}: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Neo4j request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("Neo4j request failed: invalid JSON response.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Neo4j request failed: unexpected response payload type.")

    errors_payload = parsed.get("errors", [])
    if isinstance(errors_payload, list) and errors_payload:
        first = errors_payload[0]
        if isinstance(first, Mapping):
            code = str(first.get("code", "Neo4j.Error"))
            message = str(first.get("message", "Unknown Neo4j error."))
            raise RuntimeError(f"Neo4j query failed: {code}: {message}")
        raise RuntimeError("Neo4j query failed: unknown error payload.")
    return parsed


def _run_cypher(
    *,
    url: str,
    database: str,
    user: str,
    password: str,
    statement: str,
    parameters: Mapping[str, Any] | None,
    timeout_sec: float,
) -> list[dict[str, Any]]:
    payload = _neo4j_cypher_json(
        url=url,
        database=database,
        user=user,
        password=password,
        statements=[
            {
                "statement": statement,
                "parameters": dict(parameters or {}),
                "resultDataContents": ["row"],
            }
        ],
        timeout_sec=timeout_sec,
    )
    results = payload.get("results", [])
    if not isinstance(results, list) or not results:
        return []
    first = results[0]
    if not isinstance(first, Mapping):
        return []
    columns = first.get("columns", [])
    data = first.get("data", [])
    if not isinstance(columns, list) or not isinstance(data, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, Mapping):
            continue
        raw_row = item.get("row", [])
        if not isinstance(raw_row, list):
            continue
        if len(raw_row) != len(columns):
            continue
        row: dict[str, Any] = {}
        for key, value in zip(columns, raw_row):
            row[str(key)] = value
        rows.append(row)
    return rows


def _batched(rows: Sequence[Mapping[str, Any]], *, batch_size: int) -> list[list[Mapping[str, Any]]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive.")
    chunks: list[list[Mapping[str, Any]]] = []
    for index in range(0, len(rows), batch_size):
        chunks.append(list(rows[index : index + batch_size]))
    return chunks


def sync_kag_graph_neo4j(
    graph_payload: Mapping[str, Any],
    *,
    url: str,
    database: str,
    user: str,
    password: str,
    timeout_sec: float = 30.0,
    batch_size: int = 500,
    reset_graph: bool = False,
) -> dict[str, Any]:
    doc_nodes = graph_payload.get("nodes", {}).get("docs", [])
    entity_nodes = graph_payload.get("nodes", {}).get("entities", [])
    mention_edges = graph_payload.get("edges", {}).get("mentions", [])
    cooccurs_edges = graph_payload.get("edges", {}).get("cooccurs", [])
    if not isinstance(doc_nodes, list) or not isinstance(entity_nodes, list):
        raise ValueError("Invalid KAG graph payload: missing nodes lists.")
    if not isinstance(mention_edges, list) or not isinstance(cooccurs_edges, list):
        raise ValueError("Invalid KAG graph payload: missing edges lists.")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive.")

    calls = 0

    def run(statement: str, parameters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        return _run_cypher(
            url=url,
            database=database,
            user=user,
            password=password,
            statement=statement,
            parameters=parameters,
            timeout_sec=timeout_sec,
        )

    run("CREATE CONSTRAINT kag_doc_id IF NOT EXISTS FOR (d:Doc) REQUIRE d.id IS UNIQUE")
    run("CREATE CONSTRAINT kag_entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
    run("CREATE FULLTEXT INDEX kag_doc_fulltext IF NOT EXISTS FOR (d:Doc) ON EACH [d.title, d.doc_id]")

    if reset_graph:
        run("MATCH (n) WHERE n:Doc OR n:Entity DETACH DELETE n")

    doc_rows = [
        {
            "id": str(item.get("id", "")),
            "doc_id": str(item.get("doc_id", "")),
            "source": str(item.get("source", "")),
            "title": str(item.get("title", "")),
            "path": str(item.get("path", "")),
        }
        for item in doc_nodes
        if isinstance(item, Mapping) and str(item.get("id", "")).strip()
    ]
    for chunk in _batched(doc_rows, batch_size=batch_size):
        run(
            """
UNWIND $rows AS row
MERGE (d:Doc {id: row.id})
SET d.doc_id = row.doc_id,
    d.source = row.source,
    d.title = row.title,
    d.path = row.path
""".strip(),
            {"rows": chunk},
        )

    entity_rows = [
        {
            "id": str(item.get("id", "")),
            "entity": str(item.get("entity", "")),
            "label": str(item.get("label", "")),
        }
        for item in entity_nodes
        if isinstance(item, Mapping) and str(item.get("id", "")).strip()
    ]
    for chunk in _batched(entity_rows, batch_size=batch_size):
        run(
            """
UNWIND $rows AS row
MERGE (e:Entity {id: row.id})
SET e.entity = row.entity,
    e.label = row.label
""".strip(),
            {"rows": chunk},
        )

    mention_rows = [
        {
            "src": str(item.get("src", "")),
            "dst": str(item.get("dst", "")),
            "weight": int(item.get("weight", 1)),
        }
        for item in mention_edges
        if isinstance(item, Mapping)
        and str(item.get("src", "")).startswith("doc:")
        and str(item.get("dst", "")).startswith("ent:")
    ]
    for chunk in _batched(mention_rows, batch_size=batch_size):
        run(
            """
UNWIND $rows AS row
MATCH (d:Doc {id: row.src})
MATCH (e:Entity {id: row.dst})
MERGE (d)-[r:MENTIONS]->(e)
SET r.weight = row.weight
""".strip(),
            {"rows": chunk},
        )

    cooccurs_rows = [
        {
            "src": str(item.get("src", "")),
            "dst": str(item.get("dst", "")),
            "weight": int(item.get("weight", 1)),
        }
        for item in cooccurs_edges
        if isinstance(item, Mapping)
        and str(item.get("src", "")).startswith("ent:")
        and str(item.get("dst", "")).startswith("ent:")
    ]
    for chunk in _batched(cooccurs_rows, batch_size=batch_size):
        run(
            """
UNWIND $rows AS row
MATCH (a:Entity {id: row.src})
MATCH (b:Entity {id: row.dst})
MERGE (a)-[r:COOCCURS]->(b)
SET r.weight = row.weight
""".strip(),
            {"rows": chunk},
        )

    return {
        "url": url,
        "database": database,
        "reset_graph": reset_graph,
        "doc_nodes": len(doc_rows),
        "entity_nodes": len(entity_rows),
        "mention_edges": len(mention_rows),
        "cooccurs_edges": len(cooccurs_rows),
        "query_calls": calls,
    }


def query_kag_neo4j(
    *,
    url: str,
    database: str,
    user: str,
    password: str,
    query: str,
    topk: int = 5,
    timeout_sec: float = 10.0,
) -> list[dict[str, Any]]:
    if topk <= 0:
        return []
    query_entities = tokenize_kag_entities(query)
    if not query_entities:
        return []

    direct_rows = _run_cypher(
        url=url,
        database=database,
        user=user,
        password=password,
        timeout_sec=timeout_sec,
        statement="""
UNWIND $entities AS token
MATCH (d:Doc)-[:MENTIONS]->(e:Entity {entity: token})
WITH d, collect(DISTINCT e.entity) AS matched_entities, toFloat(count(DISTINCT e)) AS direct_score
RETURN d.doc_id AS doc_id,
       d.source AS source,
       d.title AS title,
       d.path AS path,
       matched_entities,
       direct_score
""".strip(),
        parameters={"entities": query_entities},
    )
    expansion_rows: list[dict[str, Any]] = []
    if len(query_entities) > 1:
        expansion_rows = _run_cypher(
            url=url,
            database=database,
            user=user,
            password=password,
            timeout_sec=timeout_sec,
            statement="""
UNWIND $entities AS token
MATCH (q:Entity {entity: token})-[c:COOCCURS]-(n:Entity)<-[:MENTIONS]-(d:Doc)
WITH d,
     d.source AS source,
     d.title AS title,
     d.path AS path,
     sum(0.1 * toFloat(coalesce(c.weight, 1))) AS expansion_score
RETURN d.doc_id AS doc_id,
       source,
       title,
       path,
       expansion_score
""".strip(),
            parameters={"entities": query_entities},
        )
    lexical_rows: list[dict[str, Any]] = []
    if len(direct_rows) < topk:
        lexical_rows = _run_cypher(
            url=url,
            database=database,
            user=user,
            password=password,
            timeout_sec=timeout_sec,
            statement="""
CALL db.index.fulltext.queryNodes('kag_doc_fulltext', $query_text) YIELD node, score
WITH node AS d, toFloat(score) AS fulltext_score
WITH d,
     fulltext_score,
     toLower(coalesce(d.title, '')) AS title_lc,
     CASE
         WHEN coalesce(d.doc_id, '') CONTAINS ':' THEN toLower(split(coalesce(d.doc_id, ''), ':')[1])
         ELSE toLower(coalesce(d.doc_id, ''))
     END AS doc_key
WITH d,
     fulltext_score,
     [token IN $entities WHERE title_lc CONTAINS token OR doc_key CONTAINS token] AS matched_lexical
WHERE size(matched_lexical) > 0
RETURN d.doc_id AS doc_id,
       d.source AS source,
       d.title AS title,
       d.path AS path,
       matched_lexical,
       toFloat(size(matched_lexical)) AS lexical_score,
       fulltext_score
""".strip(),
            parameters={"entities": query_entities, "query_text": query},
        )
        if len(query_entities) == 1:
            query_token = query_entities[0]
            has_direct_lexical_alignment = any(
                (
                    query_token in str(row.get("title", "")).lower()
                    or query_token in _doc_key_from_doc_id(str(row.get("doc_id", "")))
                )
                for row in direct_rows
            )
            should_scan_fallback = (len(direct_rows) == 0) or (not has_direct_lexical_alignment)
        else:
            should_scan_fallback = len(direct_rows) == 0
        if not lexical_rows and should_scan_fallback:
            lexical_rows = _run_cypher(
                url=url,
                database=database,
                user=user,
                password=password,
                timeout_sec=timeout_sec,
                statement="""
MATCH (d:Doc)
WITH d,
     toLower(coalesce(d.title, '')) AS title_lc,
     CASE
         WHEN coalesce(d.doc_id, '') CONTAINS ':' THEN toLower(split(coalesce(d.doc_id, ''), ':')[1])
         ELSE toLower(coalesce(d.doc_id, ''))
     END AS doc_key
WITH d,
     [token IN $entities WHERE title_lc CONTAINS token OR doc_key CONTAINS token] AS matched_lexical
WHERE size(matched_lexical) > 0
RETURN d.doc_id AS doc_id,
       d.source AS source,
       d.title AS title,
       d.path AS path,
       matched_lexical,
       toFloat(size(matched_lexical)) AS lexical_score,
       0.0 AS fulltext_score
ORDER BY lexical_score DESC, d.doc_id ASC
LIMIT $limit
""".strip(),
                parameters={
                    "entities": query_entities,
                    "limit": max(topk * 5, 20),
                },
            )

    by_doc: dict[str, dict[str, Any]] = {}
    for row in direct_rows:
        doc_id = str(row.get("doc_id", "")).strip()
        if not doc_id:
            continue
        matched_raw = row.get("matched_entities", [])
        matched_entities = []
        if isinstance(matched_raw, list):
            matched_entities = [str(item) for item in matched_raw if str(item).strip()]
        score = float(row.get("direct_score", 0.0))
        by_doc[doc_id] = {
            "score": score,
            "id": doc_id,
            "source": str(row.get("source", "")),
            "title": str(row.get("title", "")),
            "path": str(row.get("path", "")),
            "matched_entities": sorted(set(matched_entities)),
            "lexical_matched_tokens": [],
        }

    for row in expansion_rows:
        doc_id = str(row.get("doc_id", "")).strip()
        if not doc_id:
            continue
        item = by_doc.setdefault(
            doc_id,
            {
                "score": 0.0,
                "id": doc_id,
                "source": str(row.get("source", "")),
                "title": str(row.get("title", "")),
                "path": str(row.get("path", "")),
                "matched_entities": [],
                "lexical_matched_tokens": [],
            },
        )
        item["score"] = float(item.get("score", 0.0)) + float(row.get("expansion_score", 0.0))
        if not item.get("source"):
            item["source"] = str(row.get("source", ""))
        if not item.get("title"):
            item["title"] = str(row.get("title", ""))
        if not item.get("path"):
            item["path"] = str(row.get("path", ""))

    for row in lexical_rows:
        doc_id = str(row.get("doc_id", "")).strip()
        if not doc_id:
            continue
        item = by_doc.setdefault(
            doc_id,
            {
                "score": 0.0,
                "id": doc_id,
                "source": str(row.get("source", "")),
                "title": str(row.get("title", "")),
                "path": str(row.get("path", "")),
                "matched_entities": [],
                "lexical_matched_tokens": [],
            },
        )
        lexical_score = float(row.get("lexical_score", 0.0))
        fulltext_score = float(row.get("fulltext_score", 0.0))
        # Lexical fallback improves recall when graph mentions are sparse.
        item["score"] = float(item.get("score", 0.0)) + (0.75 * lexical_score) + (0.05 * fulltext_score)
        lexical_raw = row.get("matched_lexical", [])
        if isinstance(lexical_raw, list):
            lexical_tokens = [str(token) for token in lexical_raw if str(token).strip()]
            merged = set(item.get("matched_entities", []))
            merged.update(lexical_tokens)
            item["matched_entities"] = sorted(merged)
            lexical_merged = set(item.get("lexical_matched_tokens", []))
            lexical_merged.update(lexical_tokens)
            item["lexical_matched_tokens"] = sorted(lexical_merged)
        if not item.get("source"):
            item["source"] = str(row.get("source", ""))
        if not item.get("title"):
            item["title"] = str(row.get("title", ""))
        if not item.get("path"):
            item["path"] = str(row.get("path", ""))

    if len(query_entities) == 1:
        query_token = query_entities[0]
        for item in by_doc.values():
            lexical_tokens = set(str(token) for token in item.get("lexical_matched_tokens", []))
            if query_token not in lexical_tokens:
                continue
            doc_id = str(item.get("id", ""))
            # For single-token queries, prefer lexical filename/title alignment.
            lexical_bonus = 0.35
            if ":chapters/chapter_" in doc_id.lower():
                lexical_bonus += 0.05
            item["score"] = float(item.get("score", 0.0)) + lexical_bonus

    ranked = sorted(by_doc.values(), key=lambda item: float(item["score"]), reverse=True)[:topk]
    results: list[dict[str, Any]] = []
    for item in ranked:
        results.append(
            {
                "score": float(item["score"]),
                "id": str(item["id"]),
                "source": str(item["source"]),
                "title": str(item["title"]),
                "matched_entities": list(item["matched_entities"]),
                "citation": {
                    "id": str(item["id"]),
                    "source": str(item["source"]),
                    "path": str(item["path"]),
                },
            }
        )
    return results
