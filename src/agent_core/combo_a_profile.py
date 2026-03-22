from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib import error as url_error
from urllib import request

from src.kag import build_kag_graph, sync_kag_graph_neo4j
from src.rag.retrieval import ingest_docs_qdrant, load_docs

DEFAULT_PROFILE = "baseline_first"
COMBO_A_PROFILE = "combo_a"
SUPPORTED_PROFILES = (DEFAULT_PROFILE, COMBO_A_PROFILE)

DEFAULT_COMBO_A_QDRANT_URL = "http://127.0.0.1:6333"
DEFAULT_COMBO_A_QDRANT_HOST = "127.0.0.1"
DEFAULT_COMBO_A_QDRANT_PORT = 6333
DEFAULT_COMBO_A_QDRANT_COLLECTION = "atm10_combo_a_fixture"
DEFAULT_COMBO_A_QDRANT_VECTOR_SIZE = 64

DEFAULT_COMBO_A_NEO4J_URL = "http://127.0.0.1:7474"
DEFAULT_COMBO_A_NEO4J_DATABASE = "neo4j"
DEFAULT_COMBO_A_NEO4J_USER = "neo4j"
DEFAULT_COMBO_A_NEO4J_DATASET_TAG = "atm10_combo_a_fixture"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def profile_backends(profile: str) -> tuple[str, str]:
    normalized = str(profile).strip().lower() or DEFAULT_PROFILE
    if normalized == COMBO_A_PROFILE:
        return "qdrant", "neo4j"
    return "in_memory", "file"


def docs_path_required(*, retrieval_backend: str, kag_backend: str) -> bool:
    return retrieval_backend == "in_memory" or kag_backend == "file"


def combo_a_fixture_collection(scope: str) -> str:
    normalized_scope = str(scope).strip().lower().replace(" ", "_").replace("-", "_")
    suffix = normalized_scope or "default"
    return f"{DEFAULT_COMBO_A_QDRANT_COLLECTION}_{suffix}"


def combo_a_fixture_dataset_tag(scope: str) -> str:
    normalized_scope = str(scope).strip().lower().replace(" ", "_").replace("-", "_")
    suffix = normalized_scope or "default"
    return f"{DEFAULT_COMBO_A_NEO4J_DATASET_TAG}_{suffix}"


def qdrant_host_port_from_url(url: str | None) -> tuple[str, int]:
    normalized = str(url or DEFAULT_COMBO_A_QDRANT_URL).strip().rstrip("/")
    if normalized.startswith("http://"):
        normalized = normalized[len("http://") :]
    elif normalized.startswith("https://"):
        normalized = normalized[len("https://") :]
    host_part, _, port_part = normalized.partition(":")
    host = host_part.strip() or DEFAULT_COMBO_A_QDRANT_HOST
    port = DEFAULT_COMBO_A_QDRANT_PORT
    if port_part.strip():
        port = int(port_part.strip().split("/", 1)[0])
    return host, port


def resolve_neo4j_password(password: str | None) -> str:
    if password is not None and str(password).strip():
        return str(password)
    from_env = os.environ.get("NEO4J_PASSWORD", "").strip()
    if from_env:
        return from_env
    raise ValueError("Neo4j password is required: pass neo4j_password or set NEO4J_PASSWORD.")


def _create_run_dir(runs_dir: Path, *, scope: str, now: datetime) -> Path:
    normalized_scope = str(scope).strip().lower().replace(" ", "-").replace("_", "-") or "default"
    base_name = now.strftime(f"%Y%m%d_%H%M%S-combo-a-seed-{normalized_scope}")
    run_dir = runs_dir / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    suffix = 1
    while True:
        candidate = runs_dir / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def seed_combo_a_fixture_data(
    *,
    scope: str,
    docs_path: Path,
    runs_dir: Path,
    max_entities_per_doc: int = 128,
    qdrant_collection: str | None = None,
    qdrant_host: str = DEFAULT_COMBO_A_QDRANT_HOST,
    qdrant_port: int = DEFAULT_COMBO_A_QDRANT_PORT,
    qdrant_vector_size: int = DEFAULT_COMBO_A_QDRANT_VECTOR_SIZE,
    qdrant_timeout_sec: float = 10.0,
    qdrant_batch_size: int = 128,
    neo4j_url: str = DEFAULT_COMBO_A_NEO4J_URL,
    neo4j_database: str = DEFAULT_COMBO_A_NEO4J_DATABASE,
    neo4j_user: str = DEFAULT_COMBO_A_NEO4J_USER,
    neo4j_password: str | None = None,
    neo4j_dataset_tag: str | None = None,
    neo4j_timeout_sec: float = 30.0,
    neo4j_batch_size: int = 500,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    effective_collection = qdrant_collection or combo_a_fixture_collection(scope)
    effective_dataset_tag = neo4j_dataset_tag or combo_a_fixture_dataset_tag(scope)
    run_dir = _create_run_dir(runs_dir, scope=scope, now=now)
    run_json_path = run_dir / "run.json"
    seed_summary_json = run_dir / "seed_summary.json"
    graph_json_path = run_dir / "kag_graph.json"

    run_payload: dict[str, Any] = {
        "schema_version": "combo_a_fixture_seed_v1",
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "combo_a_fixture_seed",
        "status": "started",
        "scope": scope,
        "request": {
            "docs_path": str(docs_path),
            "max_entities_per_doc": max_entities_per_doc,
            "qdrant_collection": effective_collection,
            "qdrant_host": qdrant_host,
            "qdrant_port": qdrant_port,
            "qdrant_vector_size": qdrant_vector_size,
            "neo4j_url": neo4j_url,
            "neo4j_database": neo4j_database,
            "neo4j_user": neo4j_user,
            "neo4j_dataset_tag": effective_dataset_tag,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "seed_summary_json": str(seed_summary_json),
            "kag_graph_json": str(graph_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        password = resolve_neo4j_password(neo4j_password)
        docs = load_docs(docs_path)
        qdrant_summary = ingest_docs_qdrant(
            docs,
            collection=effective_collection,
            host=qdrant_host,
            port=qdrant_port,
            vector_size=qdrant_vector_size,
            timeout_sec=qdrant_timeout_sec,
            batch_size=qdrant_batch_size,
        )
        graph_payload = build_kag_graph(docs, max_entities_per_doc=max_entities_per_doc)
        _write_json(graph_json_path, graph_payload)
        neo4j_summary = sync_kag_graph_neo4j(
            graph_payload,
            url=neo4j_url,
            database=neo4j_database,
            user=neo4j_user,
            password=password,
            timeout_sec=neo4j_timeout_sec,
            batch_size=neo4j_batch_size,
            reset_graph=True,
            dataset_tag=effective_dataset_tag,
        )
        summary_payload = {
            "schema_version": "combo_a_fixture_seed_summary_v1",
            "status": "ok",
            "scope": scope,
            "checked_at_utc": utc_now(),
            "qdrant": {
                "host": qdrant_host,
                "port": qdrant_port,
                "collection": effective_collection,
                "vector_size": qdrant_vector_size,
                "summary": qdrant_summary,
            },
            "neo4j": {
                "url": neo4j_url,
                "database": neo4j_database,
                "user": neo4j_user,
                "dataset_tag": effective_dataset_tag,
                "summary": neo4j_summary,
            },
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "seed_summary_json": str(seed_summary_json),
                "kag_graph_json": str(graph_json_path),
            },
        }
        _write_json(seed_summary_json, summary_payload)
        run_payload["status"] = "ok"
        run_payload["result"] = {
            "docs_ingested": qdrant_summary.get("docs_ingested"),
            "qdrant_collection": effective_collection,
            "neo4j_dataset_tag": effective_dataset_tag,
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
        }
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": None,
        }


def probe_qdrant_service(
    *,
    qdrant_url: str | None,
    timeout_sec: float,
) -> dict[str, Any]:
    if qdrant_url is None or not str(qdrant_url).strip():
        return {
            "service_name": "qdrant",
            "configured": False,
            "status": "not_configured",
            "url": None,
            "health_path": "/collections",
            "payload": None,
            "error": None,
        }
    url = str(qdrant_url).rstrip("/") + "/collections"
    req = request.Request(url=url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8")
        payload = json.loads(body) if body else {}
        return {
            "service_name": "qdrant",
            "configured": True,
            "status": "ok",
            "url": str(qdrant_url),
            "health_path": "/collections",
            "payload": payload,
            "error": None,
        }
    except url_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        return {
            "service_name": "qdrant",
            "configured": True,
            "status": "error",
            "url": str(qdrant_url),
            "health_path": "/collections",
            "payload": None,
            "error": f"http {exc.code}: {details.strip() or exc.reason}",
        }
    except Exception as exc:
        return {
            "service_name": "qdrant",
            "configured": True,
            "status": "error",
            "url": str(qdrant_url),
            "health_path": "/collections",
            "payload": None,
            "error": str(exc),
        }


def probe_neo4j_service(
    *,
    neo4j_url: str | None,
    neo4j_database: str,
    neo4j_user: str,
    neo4j_password: str | None,
    timeout_sec: float,
) -> dict[str, Any]:
    if neo4j_url is None or not str(neo4j_url).strip():
        return {
            "service_name": "neo4j",
            "configured": False,
            "status": "not_configured",
            "url": None,
            "health_path": f"/db/{neo4j_database}/tx/commit",
            "payload": None,
            "error": None,
        }
    try:
        password = resolve_neo4j_password(neo4j_password)
    except ValueError as exc:
        return {
            "service_name": "neo4j",
            "configured": True,
            "status": "missing_auth",
            "url": str(neo4j_url),
            "health_path": f"/db/{neo4j_database}/tx/commit",
            "payload": None,
            "error": str(exc),
        }

    import base64

    commit_url = f"{str(neo4j_url).rstrip('/')}/db/{neo4j_database.strip() or 'neo4j'}/tx/commit"
    auth_token = base64.b64encode(f"{neo4j_user}:{password}".encode("utf-8")).decode("ascii")
    req = request.Request(
        url=commit_url,
        method="POST",
        data=json.dumps(
            {"statements": [{"statement": "RETURN 1 AS ok", "resultDataContents": ["row"]}]}
        ).encode("utf-8"),
        headers={
            "Authorization": f"Basic {auth_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8")
        payload = json.loads(body) if body else {}
        return {
            "service_name": "neo4j",
            "configured": True,
            "status": "ok",
            "url": str(neo4j_url),
            "health_path": f"/db/{neo4j_database}/tx/commit",
            "payload": payload,
            "error": None,
        }
    except url_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        return {
            "service_name": "neo4j",
            "configured": True,
            "status": "error",
            "url": str(neo4j_url),
            "health_path": f"/db/{neo4j_database}/tx/commit",
            "payload": None,
            "error": f"http {exc.code}: {details.strip() or exc.reason}",
        }
    except Exception as exc:
        return {
            "service_name": "neo4j",
            "configured": True,
            "status": "error",
            "url": str(neo4j_url),
            "health_path": f"/db/{neo4j_database}/tx/commit",
            "payload": None,
            "error": str(exc),
        }
