from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.automation_dry_run import run_automation_dry_run
from scripts.gateway_artifact_policy import REDACTION_CHECKLIST_VERSION, redact_payload
from scripts.kag_build_baseline import run_kag_build_baseline
from scripts.kag_query_demo import run_kag_query_demo
from scripts.kag_query_neo4j import run_kag_query_neo4j
from src.rag.retrieval import load_docs, retrieve_top_k

REQUEST_SCHEMA_VERSION = "gateway_request_v1"
RESPONSE_SCHEMA_VERSION = "gateway_response_v1"
SUPPORTED_OPERATIONS = ("health", "retrieval_query", "kag_query", "automation_dry_run")
DEFAULT_RERANKER_MODEL = "Qwen/Qwen3-Reranker-0.6B"
ALLOWED_RERANKER_MODELS = (
    DEFAULT_RERANKER_MODEL,
    "OpenVINO/Qwen3-Reranker-0.6B-fp16-ov",
)
ALLOW_UNTRUSTED_RERANKER_MODEL_ENV = "ATM10_ALLOW_UNTRUSTED_RERANKER_MODEL"


class GatewayOperationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "operation_failed",
        child_runs: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.child_runs = dict(child_runs or {})


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-gateway-v1")
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


def _create_named_dir(base_dir: Path, name: str) -> Path:
    candidate = base_dir / name
    if not candidate.exists():
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate

    suffix = 1
    while True:
        alt = base_dir / f"{name}_{suffix:02d}"
        if not alt.exists():
            alt.mkdir(parents=True, exist_ok=False)
            return alt
        suffix += 1


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"request_json path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"request_json path must be a file: {path}")
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise ValueError(f"request_json is empty: {path}")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("gateway request root must be object.")
    return parsed


def _coerce_int(payload: Mapping[str, Any], field: str, default: int, *, min_value: int = 1) -> int:
    raw_value = payload.get(field, default)
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise ValueError(f"payload.{field} must be integer.")
    if raw_value < min_value:
        raise ValueError(f"payload.{field} must be >= {min_value}.")
    return raw_value


def _env_flag_true(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _validate_reranker_model(model_id: str) -> None:
    if _env_flag_true(ALLOW_UNTRUSTED_RERANKER_MODEL_ENV):
        return
    if model_id in ALLOWED_RERANKER_MODELS:
        return
    raise ValueError(
        "payload.reranker_model is not allowed. "
        f"Allowed: {list(ALLOWED_RERANKER_MODELS)!r}. "
        f"Set {ALLOW_UNTRUSTED_RERANKER_MODEL_ENV}=true only for trusted custom models."
    )


def _normalize_request(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    schema_version = str(raw_payload.get("schema_version", "")).strip()
    if schema_version != REQUEST_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported schema_version: {schema_version!r}. Expected {REQUEST_SCHEMA_VERSION!r}."
        )

    operation = str(raw_payload.get("operation", "")).strip()
    if operation not in SUPPORTED_OPERATIONS:
        raise ValueError(
            f"Unsupported operation: {operation!r}. Expected one of {list(SUPPORTED_OPERATIONS)!r}."
        )

    payload = raw_payload.get("payload", {})
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be object.")

    normalized: dict[str, Any] = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "operation": operation,
        "payload": dict(payload),
    }
    request_id = raw_payload.get("request_id")
    if request_id is not None:
        request_id_value = str(request_id).strip()
        if not request_id_value:
            raise ValueError("request_id must be non-empty string when provided.")
        normalized["request_id"] = request_id_value
    return normalized


def _run_health(payload: Mapping[str, Any], *, now: datetime) -> tuple[dict[str, Any], dict[str, str]]:
    if payload:
        _ = payload
    result = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "supported_operations": list(SUPPORTED_OPERATIONS),
    }
    return result, {}


def _run_retrieval_query(
    payload: Mapping[str, Any],
    *,
    child_runs_dir: Path,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, str]]:
    query = str(payload.get("query", "")).strip()
    if not query:
        raise ValueError("payload.query must be non-empty string for retrieval_query.")

    docs_path = Path(str(payload.get("docs_path", Path("tests") / "fixtures" / "retrieval_docs_sample.jsonl")))
    topk = _coerce_int(payload, "topk", 3, min_value=1)
    candidate_k = _coerce_int(payload, "candidate_k", 10, min_value=1)
    reranker = str(payload.get("reranker", "none")).strip().lower()
    if reranker not in {"none", "qwen3"}:
        raise ValueError("payload.reranker must be one of ['none', 'qwen3'].")
    reranker_model = str(payload.get("reranker_model", DEFAULT_RERANKER_MODEL)).strip()
    reranker_runtime = str(payload.get("reranker_runtime", "torch")).strip().lower()
    if reranker_runtime not in {"torch", "openvino"}:
        raise ValueError("payload.reranker_runtime must be one of ['torch', 'openvino'].")
    reranker_device = str(payload.get("reranker_device", "AUTO")).strip()
    reranker_max_length = _coerce_int(payload, "reranker_max_length", 1024, min_value=1)
    if reranker == "qwen3":
        _validate_reranker_model(reranker_model)

    child_run_dir = _create_named_dir(child_runs_dir, "retrieval_query")
    child_run_json = child_run_dir / "run.json"
    child_results_json = child_run_dir / "retrieval_results.json"
    child_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "gateway_retrieval_query",
        "status": "started",
        "request": {
            "query": query,
            "docs_path": str(docs_path),
            "topk": topk,
            "candidate_k": candidate_k,
            "reranker": reranker,
            "reranker_model": reranker_model if reranker == "qwen3" else None,
            "reranker_runtime": reranker_runtime if reranker == "qwen3" else None,
            "reranker_device": reranker_device if reranker == "qwen3" else None,
            "reranker_max_length": reranker_max_length if reranker == "qwen3" else None,
        },
        "paths": {
            "run_dir": str(child_run_dir),
            "run_json": str(child_run_json),
            "results_json": str(child_results_json),
        },
    }
    _write_json(child_run_json, child_payload)

    try:
        docs = load_docs(docs_path)
        results = retrieve_top_k(
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
        _write_json(
            child_results_json,
            {
                "query": query,
                "count": len(results),
                "results": results,
            },
        )
        child_payload["status"] = "ok"
        child_payload["result"] = {"results_count": len(results)}
        _write_json(child_run_json, child_payload)
        return {
            "query": query,
            "backend": "in_memory",
            "results_count": len(results),
            "topk": topk,
            "candidate_k": candidate_k,
            "reranker": reranker,
        }, {"retrieval_query": str(child_run_dir)}
    except Exception as exc:
        child_payload["status"] = "error"
        child_payload["error_code"] = "retrieval_query_failed"
        child_payload["error"] = str(exc)
        _write_json(child_run_json, child_payload)
        raise GatewayOperationError(
            str(exc),
            error_code="operation_failed",
            child_runs={"retrieval_query": str(child_run_dir)},
        ) from exc


def _run_kag_query(
    payload: Mapping[str, Any],
    *,
    child_runs_dir: Path,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, str]]:
    backend = str(payload.get("backend", "file")).strip().lower()
    if backend not in {"file", "neo4j"}:
        raise ValueError("payload.backend must be one of ['file', 'neo4j'].")

    query = str(payload.get("query", "")).strip()
    if not query:
        raise ValueError("payload.query must be non-empty string for kag_query.")
    topk = _coerce_int(payload, "topk", 5, min_value=1)

    if backend == "file":
        docs_in = Path(str(payload.get("docs_in", Path("tests") / "fixtures" / "kag_neo4j_docs_sample.jsonl")))
        max_entities_per_doc = _coerce_int(payload, "max_entities_per_doc", 128, min_value=1)

        build_result = run_kag_build_baseline(
            docs_in=docs_in,
            max_entities_per_doc=max_entities_per_doc,
            runs_dir=child_runs_dir,
            now=now,
        )
        child_runs = {"kag_build_baseline": str(build_result["run_dir"])}
        if not build_result["ok"]:
            raise GatewayOperationError(
                str(build_result["run_payload"].get("error", "kag_build_baseline failed")),
                error_code="operation_failed",
                child_runs=child_runs,
            )

        graph_path = Path(build_result["run_payload"]["paths"]["kag_graph_json"])
        query_result = run_kag_query_demo(
            graph_path=graph_path,
            query=query,
            topk=topk,
            runs_dir=child_runs_dir,
            now=now,
        )
        child_runs["kag_query_demo"] = str(query_result["run_dir"])
        if not query_result["ok"]:
            raise GatewayOperationError(
                str(query_result["run_payload"].get("error", "kag_query_demo failed")),
                error_code="operation_failed",
                child_runs=child_runs,
            )

        return {
            "backend": "file",
            "query": query,
            "topk": topk,
            "results_count": int(query_result["results_payload"]["count"]),
        }, child_runs

    neo4j_url = str(payload.get("neo4j_url", "http://127.0.0.1:7474")).strip()
    neo4j_database = str(payload.get("neo4j_database", "neo4j")).strip()
    neo4j_user = str(payload.get("neo4j_user", "neo4j")).strip()
    neo4j_password_value = payload.get("neo4j_password")
    neo4j_password = None if neo4j_password_value is None else str(neo4j_password_value)
    timeout_sec = float(payload.get("timeout_sec", 10.0))

    neo4j_result = run_kag_query_neo4j(
        query=query,
        topk=topk,
        neo4j_url=neo4j_url,
        neo4j_database=neo4j_database,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        timeout_sec=timeout_sec,
        runs_dir=child_runs_dir,
        now=now,
    )
    child_runs = {"kag_query_neo4j": str(neo4j_result["run_dir"])}
    if not neo4j_result["ok"]:
        raise GatewayOperationError(
            str(neo4j_result["run_payload"].get("error", "kag_query_neo4j failed")),
            error_code="operation_failed",
            child_runs=child_runs,
        )
    return {
        "backend": "neo4j",
        "query": query,
        "topk": topk,
        "results_count": int(neo4j_result["results_payload"]["count"]),
    }, child_runs


def _run_automation_dry_run(
    payload: Mapping[str, Any],
    *,
    child_runs_dir: Path,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, str]]:
    plan_json_value = payload.get("plan_json")
    plan_payload_value = payload.get("plan_payload")

    if plan_json_value is None and plan_payload_value is None:
        raise ValueError("payload.plan_json or payload.plan_payload is required for automation_dry_run.")
    if plan_json_value is not None and plan_payload_value is not None:
        raise ValueError("Provide only one of payload.plan_json or payload.plan_payload.")

    if plan_json_value is not None:
        plan_json_path = Path(str(plan_json_value))
    else:
        if not isinstance(plan_payload_value, Mapping):
            raise ValueError("payload.plan_payload must be object.")
        plan_json_path = child_runs_dir / "gateway_plan.json"
        _write_json(plan_json_path, dict(plan_payload_value))

    automation_result = run_automation_dry_run(
        plan_json=plan_json_path,
        runs_dir=child_runs_dir,
        now=now,
    )
    child_runs = {"automation_dry_run": str(automation_result["run_dir"])}
    if not automation_result["ok"]:
        raise GatewayOperationError(
            str(automation_result["run_payload"].get("error", "automation_dry_run failed")),
            error_code="operation_failed",
            child_runs=child_runs,
        )

    result_payload = dict(automation_result["run_payload"].get("result", {}))
    result_payload["dry_run_only"] = True
    return result_payload, child_runs


def _dispatch_operation(
    *,
    operation: str,
    payload: Mapping[str, Any],
    child_runs_dir: Path,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, str]]:
    if operation == "health":
        return _run_health(payload, now=now)
    if operation == "retrieval_query":
        return _run_retrieval_query(payload, child_runs_dir=child_runs_dir, now=now)
    if operation == "kag_query":
        return _run_kag_query(payload, child_runs_dir=child_runs_dir, now=now)
    if operation == "automation_dry_run":
        return _run_automation_dry_run(payload, child_runs_dir=child_runs_dir, now=now)
    raise ValueError(f"Unsupported operation: {operation!r}.")


def run_gateway_request(
    *,
    request_payload: Mapping[str, Any] | None = None,
    request_json: Path | None = None,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)
    if request_payload is None and request_json is None:
        raise ValueError("request_payload or request_json is required.")
    if request_payload is not None and request_json is not None:
        raise ValueError("Provide only one of request_payload or request_json.")

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    request_out_path = run_dir / "request.json"
    response_json_path = run_dir / "response.json"
    child_runs_dir = run_dir / "child_runs"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "gateway_v1_local",
        "status": "started",
        "request_redaction": {
            "checklist_version": REDACTION_CHECKLIST_VERSION,
            "applied": False,
            "fields_redacted": [],
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "request_json": str(request_out_path),
            "response_json": str(response_json_path),
            "child_runs_dir": str(child_runs_dir),
        },
    }
    _write_json(run_json_path, run_payload)
    loaded_request: dict[str, Any] = {}
    operation = "unknown"
    child_runs: dict[str, str] = {}
    try:
        loaded_request = (
            _read_json_object(request_json) if request_json is not None else dict(request_payload or {})
        )
        redacted_request, request_redaction = redact_payload(loaded_request, enable_redaction=True)
        _write_json(request_out_path, redacted_request)
        run_payload["request_redaction"] = request_redaction
        normalized_request = _normalize_request(loaded_request)
        operation = normalized_request["operation"]
        result_payload, child_runs = _dispatch_operation(
            operation=operation,
            payload=normalized_request["payload"],
            child_runs_dir=child_runs_dir,
            now=now,
        )
        response_payload: dict[str, Any] = {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "operation": operation,
            "status": "ok",
            "error_code": None,
            "error": None,
            "result": result_payload,
            "artifacts": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "child_runs": child_runs,
            },
        }
        run_payload["status"] = "ok"
        run_payload["operation"] = operation
        run_payload["result"] = result_payload
        run_payload["child_runs"] = child_runs
    except GatewayOperationError as exc:
        child_runs = dict(exc.child_runs)
        response_payload = {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "operation": operation,
            "status": "error",
            "error_code": exc.error_code,
            "error": str(exc),
            "result": None,
            "artifacts": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "child_runs": child_runs,
            },
        }
        run_payload["status"] = "error"
        run_payload["operation"] = operation
        run_payload["error_code"] = exc.error_code
        run_payload["error"] = str(exc)
        run_payload["child_runs"] = child_runs
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        response_payload = {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "operation": operation,
            "status": "error",
            "error_code": "invalid_request",
            "error": str(exc),
            "result": None,
            "artifacts": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "child_runs": child_runs,
            },
        }
        run_payload["status"] = "error"
        run_payload["operation"] = operation
        run_payload["error_code"] = "invalid_request"
        run_payload["error"] = str(exc)
        run_payload["child_runs"] = child_runs
    except Exception as exc:
        response_payload = {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "operation": operation,
            "status": "error",
            "error_code": "gateway_dispatch_failed",
            "error": str(exc),
            "result": None,
            "artifacts": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "child_runs": child_runs,
            },
        }
        run_payload["status"] = "error"
        run_payload["operation"] = operation
        run_payload["error_code"] = "gateway_dispatch_failed"
        run_payload["error"] = str(exc)
        run_payload["child_runs"] = child_runs

    if not request_out_path.exists():
        fallback_request_payload: dict[str, Any] = {}
        if request_json is not None:
            fallback_request_payload["request_json"] = str(request_json)
        redacted_fallback_request, fallback_redaction = redact_payload(
            fallback_request_payload,
            enable_redaction=True,
        )
        _write_json(request_out_path, redacted_fallback_request)
        run_payload["request_redaction"] = fallback_redaction

    _write_json(response_json_path, response_payload)
    _write_json(run_json_path, run_payload)
    return {
        "ok": response_payload["status"] == "ok",
        "run_dir": run_dir,
        "run_payload": run_payload,
        "response_payload": response_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local gateway v1 dispatcher (contract-first, no HTTP server).")
    parser.add_argument("--request-json", type=Path, required=True, help="Path to gateway_request_v1 JSON.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_gateway_request(request_json=args.request_json, runs_dir=args.runs_dir)
    run_dir = result["run_dir"]
    response_payload = result["response_payload"]
    print(f"[gateway_v1_local] run_dir: {run_dir}")
    print(f"[gateway_v1_local] run_json: {run_dir / 'run.json'}")
    print(f"[gateway_v1_local] request_json: {run_dir / 'request.json'}")
    print(f"[gateway_v1_local] response_json: {run_dir / 'response.json'}")
    print(f"[gateway_v1_local] operation: {response_payload['operation']}")
    print(f"[gateway_v1_local] status: {response_payload['status']}")
    if response_payload["status"] != "ok":
        print(f"[gateway_v1_local] error_code: {response_payload['error_code']}")
        print(f"[gateway_v1_local] error: {response_payload['error']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
