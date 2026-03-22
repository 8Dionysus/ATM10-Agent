from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.gateway_artifact_policy import (
    cleanup_old_gateway_artifacts,
    redact_error_entry,
    rotate_jsonl,
)
from scripts.operator_product_safe_actions import build_safe_actions_overview
from scripts.operator_product_snapshot import (
    build_operator_history_payload,
    build_operator_product_snapshot,
    build_operator_runs_payload,
)
from scripts.gateway_v1_local import SUPPORTED_OPERATIONS, SUPPORTED_PROFILES, run_gateway_request

RESPONSE_SCHEMA_VERSION = "gateway_response_v1"
FastAPIRequest = Any
_GATEWAY_REQUEST_EXECUTOR_MAX_WORKERS = 4
_SERVICE_TOKEN_HEADER = "X-ATM10-Token"
_SERVICE_TOKEN_ENV = "ATM10_SERVICE_TOKEN"


@dataclass(frozen=True)
class GatewayHTTPPolicy:
    max_request_body_bytes: int = 262_144
    max_json_depth: int = 8
    max_string_length: int = 8_192
    max_array_items: int = 256
    max_object_keys: int = 256
    operation_timeout_sec: float = 15.0
    error_log_max_bytes: int = 1_048_576
    error_log_max_files: int = 5
    artifact_retention_days: int = 14
    enable_error_redaction: bool = True


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _parse_bool_flag(raw_value: str) -> bool:
    normalized = str(raw_value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("Expected one of: true|false|1|0|yes|no.")


def _append_gateway_error_entry(
    *,
    runs_dir: Path,
    policy: GatewayHTTPPolicy,
    payload: Mapping[str, Any],
) -> None:
    error_log_path = runs_dir / "gateway_http_errors.jsonl"
    redacted_payload = redact_error_entry(payload, enable_redaction=policy.enable_error_redaction)
    redacted_payload["retention_policy"] = {
        "artifact_retention_days": policy.artifact_retention_days,
        "error_log_max_bytes": policy.error_log_max_bytes,
        "error_log_max_files": policy.error_log_max_files,
    }
    rotate_jsonl(error_log_path, max_bytes=policy.error_log_max_bytes, max_files=policy.error_log_max_files)
    _append_jsonl(error_log_path, redacted_payload)
    rotate_jsonl(error_log_path, max_bytes=policy.error_log_max_bytes, max_files=policy.error_log_max_files)


def _validate_policy(policy: GatewayHTTPPolicy) -> None:
    if policy.max_request_body_bytes <= 0:
        raise ValueError("max_request_body_bytes must be > 0.")
    if policy.max_json_depth <= 0:
        raise ValueError("max_json_depth must be > 0.")
    if policy.max_string_length <= 0:
        raise ValueError("max_string_length must be > 0.")
    if policy.max_array_items <= 0:
        raise ValueError("max_array_items must be > 0.")
    if policy.max_object_keys <= 0:
        raise ValueError("max_object_keys must be > 0.")
    if policy.operation_timeout_sec <= 0:
        raise ValueError("operation_timeout_sec must be > 0.")
    if policy.error_log_max_bytes <= 0:
        raise ValueError("error_log_max_bytes must be > 0.")
    if policy.error_log_max_files <= 0:
        raise ValueError("error_log_max_files must be > 0.")
    if policy.artifact_retention_days < 0:
        raise ValueError("artifact_retention_days must be >= 0.")


def _resolve_service_token(cli_value: str | None) -> str | None:
    if cli_value is not None:
        stripped = cli_value.strip()
        return stripped or None
    env_value = os.getenv(_SERVICE_TOKEN_ENV, "").strip()
    return env_value or None


def _is_loopback_host(host: str) -> bool:
    normalized = str(host).strip()
    if not normalized:
        return False
    if normalized.lower() == "localhost":
        return True
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validate_bind_security(
    *,
    host: str,
    service_token: str | None,
    allow_insecure_no_token: bool,
) -> str | None:
    effective_service_token = _resolve_service_token(service_token)
    if effective_service_token is not None or allow_insecure_no_token or _is_loopback_host(host):
        return effective_service_token
    raise ValueError(
        "Refusing to start gateway_v1_http_service on a non-loopback host without a service token. "
        "Set --service-token / ATM10_SERVICE_TOKEN or pass --allow-insecure-no-token to opt into "
        "the insecure bind explicitly."
    )


def _is_authorized(
    request_headers: Mapping[str, Any],
    *,
    service_token: str | None,
) -> bool:
    if not service_token:
        return True
    presented_token = str(request_headers.get(_SERVICE_TOKEN_HEADER, "")).strip()
    return presented_token == service_token


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def map_gateway_http_status(response_payload: Mapping[str, Any]) -> int:
    if str(response_payload.get("status")) == "ok":
        return 200
    error_code = str(response_payload.get("error_code") or "")
    if error_code == "invalid_request":
        return 400
    if error_code in {"payload_too_large", "payload_limit_exceeded"}:
        return 413
    if error_code == "unauthorized":
        return 401
    if error_code == "operation_timeout":
        return 504
    if error_code in {"operation_failed", "gateway_dispatch_failed"}:
        return 500
    if error_code == "internal_error_sanitized":
        return 500
    return 500


def _build_response(
    *,
    operation: str,
    status: str,
    error_code: str | None,
    error: str | None,
    result: Mapping[str, Any] | None,
    artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "operation": operation,
        "status": status,
        "error_code": error_code,
        "error": error,
        "result": result,
        "artifacts": {
            "run_dir": None if artifacts is None else artifacts.get("run_dir"),
            "run_json": None if artifacts is None else artifacts.get("run_json"),
            "child_runs": {} if artifacts is None else dict(artifacts.get("child_runs") or {}),
        },
    }


def _build_health_payload(
    *,
    runs_dir: Path,
    operator_runs_dir: Path,
    policy: GatewayHTTPPolicy,
    service_token: str | None,
    expose_openapi: bool,
) -> dict[str, Any]:
    return {
        "timestamp_utc": _utc_now(),
        "status": "ok",
        "service": "gateway_v1_http_service",
        "runs_dir": str(runs_dir),
        "operator_runs_dir": str(operator_runs_dir),
        "supported_operations": list(SUPPORTED_OPERATIONS),
        "supported_profiles": list(SUPPORTED_PROFILES),
        "auth_enabled": bool(service_token),
        "api_docs_exposed": bool(expose_openapi),
        "policy": asdict(policy),
    }


def _raise_payload_limit_if_needed(value: Any, *, policy: GatewayHTTPPolicy, depth: int = 1) -> None:
    if depth > policy.max_json_depth:
        raise ValueError(
            f"payload_limit_exceeded: max_json_depth={policy.max_json_depth}, observed_depth={depth}"
        )
    if isinstance(value, str):
        if len(value) > policy.max_string_length:
            raise ValueError(
                "payload_limit_exceeded: "
                f"max_string_length={policy.max_string_length}, observed_length={len(value)}"
            )
        return
    if isinstance(value, list):
        if len(value) > policy.max_array_items:
            raise ValueError(
                f"payload_limit_exceeded: max_array_items={policy.max_array_items}, observed_items={len(value)}"
            )
        for item in value:
            _raise_payload_limit_if_needed(item, policy=policy, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > policy.max_object_keys:
            raise ValueError(
                f"payload_limit_exceeded: max_object_keys={policy.max_object_keys}, observed_keys={len(value)}"
            )
        for item in value.values():
            _raise_payload_limit_if_needed(item, policy=policy, depth=depth + 1)
        return


def _parse_request_json_bytes(
    *,
    body_bytes: bytes,
    content_length: int | None,
    policy: GatewayHTTPPolicy,
) -> dict[str, Any]:
    if content_length is not None and content_length > policy.max_request_body_bytes:
        raise RuntimeError("payload_too_large")
    if len(body_bytes) > policy.max_request_body_bytes:
        raise RuntimeError("payload_too_large")
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid_request: JSON parse failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid_request: request body must be JSON object.")
    _raise_payload_limit_if_needed(payload, policy=policy)
    return payload


def _extract_operation(payload: Mapping[str, Any]) -> str:
    return str(payload.get("operation") or "unknown")


def _build_request_context(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    context: dict[str, Any] = {
        "schema_version": payload.get("schema_version"),
        "operation": payload.get("operation"),
    }
    request_id = payload.get("request_id")
    if request_id is not None:
        context["request_id"] = str(request_id)
    payload_value = payload.get("payload")
    if isinstance(payload_value, Mapping):
        context["payload_keys"] = sorted(str(key) for key in payload_value.keys())[:64]
    return context


def _parse_csv_values(raw_value: str | None) -> list[str] | None:
    if raw_value is None:
        return None
    values = [item.strip() for item in str(raw_value).split(",") if item.strip()]
    return values or None


def create_app(
    *,
    runs_dir: Path,
    operator_runs_dir: Path | None = None,
    policy: GatewayHTTPPolicy | None = None,
    service_token: str | None = None,
    expose_openapi: bool = False,
    voice_service_url: str | None = None,
    tts_service_url: str | None = None,
    qdrant_url: str | None = None,
    neo4j_url: str | None = None,
    neo4j_database: str = "neo4j",
    neo4j_user: str = "neo4j",
    operator_health_timeout_sec: float = 1.5,
) -> Any:
    effective_operator_runs_dir = Path(operator_runs_dir) if operator_runs_dir is not None else Path(runs_dir)
    effective_policy = policy or GatewayHTTPPolicy()
    _validate_policy(effective_policy)
    effective_service_token = _resolve_service_token(service_token)
    _ = cleanup_old_gateway_artifacts(
        runs_dir=runs_dir,
        retention_days=effective_policy.artifact_retention_days,
    )
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
    except Exception as exc:  # pragma: no cover - dependency presence
        raise RuntimeError("FastAPI is required for gateway_v1_http_service.") from exc

    global FastAPIRequest
    FastAPIRequest = Request

    @asynccontextmanager
    async def _lifespan(app_instance: Any):
        app_instance.state.gateway_request_executor = ThreadPoolExecutor(
            max_workers=_GATEWAY_REQUEST_EXECUTOR_MAX_WORKERS
        )
        try:
            yield
        finally:
            executor = getattr(app_instance.state, "gateway_request_executor", None)
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(
        title="ATM10 Gateway v1 HTTP",
        version="0.1.0",
        lifespan=_lifespan,
        docs_url="/docs" if expose_openapi else None,
        openapi_url="/openapi.json" if expose_openapi else None,
        redoc_url=None,
    )

    @app.get("/healthz")
    def _healthz(request: FastAPIRequest) -> Any:
        if not _is_authorized(request.headers, service_token=effective_service_token):
            response = _build_response(
                operation="unknown",
                status="error",
                error_code="unauthorized",
                error="unauthorized",
                result=None,
            )
            return JSONResponse(status_code=map_gateway_http_status(response), content=response)
        return _build_health_payload(
            runs_dir=runs_dir,
            operator_runs_dir=effective_operator_runs_dir,
            policy=effective_policy,
            service_token=effective_service_token,
            expose_openapi=expose_openapi,
        )

    @app.get("/v1/operator/snapshot")
    def _operator_snapshot(request: FastAPIRequest) -> Any:
        if not _is_authorized(request.headers, service_token=effective_service_token):
            return JSONResponse(
                status_code=401,
                content={
                    "schema_version": "gateway_operator_status_v1",
                    "status": "error",
                    "error_code": "unauthorized",
                    "error": "unauthorized",
                },
            )
        gateway_health = _build_health_payload(
            runs_dir=runs_dir,
            operator_runs_dir=effective_operator_runs_dir,
            policy=effective_policy,
            service_token=effective_service_token,
            expose_openapi=expose_openapi,
        )
        return build_operator_product_snapshot(
            runs_dir=runs_dir,
            gateway_health=gateway_health,
            operator_runs_dir=effective_operator_runs_dir,
            voice_service_url=voice_service_url,
            tts_service_url=tts_service_url,
            qdrant_url=qdrant_url,
            neo4j_url=neo4j_url,
            neo4j_database=neo4j_database,
            neo4j_user=neo4j_user,
            health_timeout_sec=operator_health_timeout_sec,
            service_token=effective_service_token,
        )

    @app.get("/v1/operator/runs")
    def _operator_runs(request: FastAPIRequest, limit: int = 20) -> Any:
        if not _is_authorized(request.headers, service_token=effective_service_token):
            return JSONResponse(
                status_code=401,
                content={
                    "schema_version": "gateway_operator_runs_v1",
                    "status": "error",
                    "error_code": "unauthorized",
                    "error": "unauthorized",
                },
            )
        return build_operator_runs_payload(
            runs_dir=runs_dir,
            operator_runs_dir=effective_operator_runs_dir,
            limit=limit,
        )

    @app.get("/v1/operator/history")
    def _operator_history(
        request: FastAPIRequest,
        source: str | None = None,
        status: str | None = None,
        limit_per_source: int = 10,
    ) -> Any:
        if not _is_authorized(request.headers, service_token=effective_service_token):
            return JSONResponse(
                status_code=401,
                content={
                    "schema_version": "gateway_operator_history_v1",
                    "status": "error",
                    "error_code": "unauthorized",
                    "error": "unauthorized",
                },
            )
        return build_operator_history_payload(
            runs_dir=runs_dir,
            selected_sources=_parse_csv_values(source),
            selected_statuses=_parse_csv_values(status),
            limit_per_source=limit_per_source,
        )

    @app.get("/v1/operator/safe-actions")
    def _operator_safe_actions(request: FastAPIRequest, history_limit: int = 10) -> Any:
        if not _is_authorized(request.headers, service_token=effective_service_token):
            return JSONResponse(
                status_code=401,
                content={
                    "schema_version": "gateway_operator_safe_actions_v1",
                    "status": "error",
                    "error_code": "unauthorized",
                    "error": "unauthorized",
                },
            )
        return build_safe_actions_overview(runs_dir=runs_dir, history_limit=history_limit)

    @app.post("/v1/operator/safe-actions/run")
    async def _operator_safe_action_run(request: FastAPIRequest) -> Any:
        if not _is_authorized(request.headers, service_token=effective_service_token):
            return JSONResponse(
                status_code=401,
                content={
                    "schema_version": "gateway_operator_safe_action_run_v1",
                    "status": "error",
                    "error_code": "unauthorized",
                    "error": "unauthorized",
                },
            )
        request_payload: dict[str, Any] = {}
        raw_body = b""
        try:
            content_length_raw = request.headers.get("content-length")
            content_length = int(content_length_raw) if content_length_raw is not None else None
            if content_length is not None and content_length < 0:
                raise ValueError("invalid_request: content-length must be >= 0")
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={
                    "schema_version": "gateway_operator_safe_action_run_v1",
                    "status": "error",
                    "error_code": "invalid_request",
                    "error": "invalid_request: malformed Content-Length header",
                },
            )

        raw_body = await request.body()
        try:
            body_payload = _parse_request_json_bytes(
                body_bytes=raw_body,
                content_length=content_length,
                policy=effective_policy,
            )
        except RuntimeError:
            return JSONResponse(
                status_code=413,
                content={
                    "schema_version": "gateway_operator_safe_action_run_v1",
                    "status": "error",
                    "error_code": "payload_too_large",
                    "error": "payload too large",
                },
            )
        except ValueError as exc:
            error_message = str(exc)
            error_code = "payload_limit_exceeded" if "payload_limit_exceeded" in error_message else "invalid_request"
            status_code = 413 if error_code == "payload_limit_exceeded" else 400
            return JSONResponse(
                status_code=status_code,
                content={
                    "schema_version": "gateway_operator_safe_action_run_v1",
                    "status": "error",
                    "error_code": error_code,
                    "error": error_message,
                },
            )

        request_payload = {
            "schema_version": "gateway_request_v1",
            "operation": "safe_action_smoke",
            "payload": body_payload,
        }
        try:
            executor = getattr(app.state, "gateway_request_executor", None)
            if executor is None:
                raise RuntimeError("gateway_request_executor is not initialized.")
            future = executor.submit(
                run_gateway_request,
                request_payload=request_payload,
                runs_dir=runs_dir,
            )
            try:
                gateway_result = future.result(timeout=effective_policy.operation_timeout_sec)
            except FutureTimeoutError:
                future.cancel()
                return JSONResponse(
                    status_code=504,
                    content={
                        "schema_version": "gateway_operator_safe_action_run_v1",
                        "status": "error",
                        "error_code": "operation_timeout",
                        "error": "gateway operation timed out",
                    },
                )
            response_payload = gateway_result["response_payload"]
            status_code = 200 if response_payload["status"] == "ok" else map_gateway_http_status(response_payload)
            return JSONResponse(status_code=status_code, content=response_payload["result"] if response_payload["status"] == "ok" else {
                "schema_version": "gateway_operator_safe_action_run_v1",
                "status": "error",
                "error_code": response_payload.get("error_code"),
                "error": response_payload.get("error"),
                "action_key": body_payload.get("action_key"),
            })
        except Exception as exc:  # pragma: no cover - defensive path
            try:
                _append_gateway_error_entry(
                    runs_dir=runs_dir,
                    policy=effective_policy,
                    payload={
                        "timestamp_utc": _utc_now(),
                        "path": "/v1/operator/safe-actions/run",
                        "error_code": "internal_error_sanitized",
                        "error": str(exc),
                        "operation": "safe_action_smoke",
                        "request_body_bytes": len(raw_body),
                        "request_context": _build_request_context(request_payload),
                        "traceback": traceback.format_exc(),
                    },
                )
            except Exception:
                pass
            return JSONResponse(
                status_code=500,
                content={
                    "schema_version": "gateway_operator_safe_action_run_v1",
                    "status": "error",
                    "error_code": "internal_error_sanitized",
                    "error": "internal service error",
                },
            )

    @app.post("/v1/gateway")
    async def _gateway(request: FastAPIRequest) -> Any:
        if not _is_authorized(request.headers, service_token=effective_service_token):
            response = _build_response(
                operation="unknown",
                status="error",
                error_code="unauthorized",
                error="unauthorized",
                result=None,
            )
            return JSONResponse(status_code=map_gateway_http_status(response), content=response)
        request_payload: dict[str, Any] = {}
        raw_body = b""
        try:
            content_length_raw = request.headers.get("content-length")
            content_length = int(content_length_raw) if content_length_raw is not None else None
            if content_length is not None and content_length < 0:
                raise ValueError("invalid_request: content-length must be >= 0")
        except ValueError:
            response = _build_response(
                operation="unknown",
                status="error",
                error_code="invalid_request",
                error="invalid_request: malformed Content-Length header",
                result=None,
            )
            return JSONResponse(status_code=map_gateway_http_status(response), content=response)

        raw_body = await request.body()
        try:
            request_payload = _parse_request_json_bytes(
                body_bytes=raw_body,
                content_length=content_length,
                policy=effective_policy,
            )
        except RuntimeError as exc:
            if str(exc) == "payload_too_large":
                response = _build_response(
                    operation="unknown",
                    status="error",
                    error_code="payload_too_large",
                    error="payload too large",
                    result=None,
                )
                return JSONResponse(status_code=map_gateway_http_status(response), content=response)
            response = _build_response(
                operation="unknown",
                status="error",
                error_code="invalid_request",
                error=f"invalid_request: {exc}",
                result=None,
            )
            return JSONResponse(status_code=map_gateway_http_status(response), content=response)
        except ValueError as exc:
            error_message = str(exc)
            if "payload_limit_exceeded" in error_message:
                response = _build_response(
                    operation=_extract_operation(request_payload) if request_payload else "unknown",
                    status="error",
                    error_code="payload_limit_exceeded",
                    error=error_message,
                    result=None,
                )
            else:
                response = _build_response(
                    operation="unknown",
                    status="error",
                    error_code="invalid_request",
                    error=error_message,
                    result=None,
                )
            return JSONResponse(status_code=map_gateway_http_status(response), content=response)

        operation = _extract_operation(request_payload)
        try:
            executor = getattr(app.state, "gateway_request_executor", None)
            if executor is None:
                raise RuntimeError("gateway_request_executor is not initialized.")
            future = executor.submit(
                run_gateway_request,
                request_payload=request_payload,
                runs_dir=runs_dir,
            )
            try:
                gateway_result = future.result(timeout=effective_policy.operation_timeout_sec)
            except FutureTimeoutError:
                future.cancel()
                response = _build_response(
                    operation=operation,
                    status="error",
                    error_code="operation_timeout",
                    error="gateway operation timed out",
                    result=None,
                )
                return JSONResponse(status_code=map_gateway_http_status(response), content=response)
            response_payload = gateway_result["response_payload"]
            return JSONResponse(
                status_code=map_gateway_http_status(response_payload),
                content=response_payload,
            )
        except Exception as exc:  # pragma: no cover - defensive path
            try:
                _append_gateway_error_entry(
                    runs_dir=runs_dir,
                    policy=effective_policy,
                    payload={
                        "timestamp_utc": _utc_now(),
                        "path": "/v1/gateway",
                        "error_code": "internal_error_sanitized",
                        "error": str(exc),
                        "operation": operation,
                        "request_body_bytes": len(raw_body),
                        "request_context": _build_request_context(
                            request_payload if request_payload else None
                        ),
                        "traceback": traceback.format_exc(),
                    },
                )
            except Exception:
                pass
            response = _build_response(
                operation=operation,
                status="error",
                error_code="internal_error_sanitized",
                error="internal service error",
                result=None,
            )
            return JSONResponse(status_code=map_gateway_http_status(response), content=response)

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HTTP transport wrapper for gateway v1 contract.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8770, help="Bind port (default: 8770).")
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs") / "gateway-http",
        help="Run artifact base directory (default: runs/gateway-http).",
    )
    parser.add_argument(
        "--operator-runs-dir",
        type=Path,
        default=None,
        help=(
            "Operator artifact base directory used to resolve launcher/session artifacts "
            "(default: same as --runs-dir)."
        ),
    )
    parser.add_argument(
        "--max-request-bytes",
        type=int,
        default=262_144,
        help="Maximum allowed HTTP request body size in bytes (default: 262144).",
    )
    parser.add_argument(
        "--max-json-depth",
        type=int,
        default=8,
        help="Maximum allowed JSON depth (default: 8).",
    )
    parser.add_argument(
        "--max-string-length",
        type=int,
        default=8_192,
        help="Maximum allowed JSON string length (default: 8192).",
    )
    parser.add_argument(
        "--max-array-items",
        type=int,
        default=256,
        help="Maximum allowed JSON array length (default: 256).",
    )
    parser.add_argument(
        "--max-object-keys",
        type=int,
        default=256,
        help="Maximum allowed JSON object key count (default: 256).",
    )
    parser.add_argument(
        "--operation-timeout-sec",
        type=float,
        default=15.0,
        help="Gateway operation timeout in seconds (default: 15.0).",
    )
    parser.add_argument(
        "--error-log-max-bytes",
        type=int,
        default=1_048_576,
        help="Maximum size per gateway_http_errors JSONL file before rotation (default: 1048576).",
    )
    parser.add_argument(
        "--error-log-max-files",
        type=int,
        default=5,
        help="Maximum number of rotated gateway_http_errors JSONL files (default: 5).",
    )
    parser.add_argument(
        "--artifact-retention-days",
        type=int,
        default=14,
        help="Retention window in days for gateway error logs and gateway run artifacts (default: 14).",
    )
    parser.add_argument(
        "--enable-error-redaction",
        type=_parse_bool_flag,
        default=True,
        help="Enable redaction for gateway HTTP error logs (default: true).",
    )
    parser.add_argument(
        "--service-token",
        type=str,
        default=None,
        help=(
            "Optional shared token for HTTP endpoints. "
            "When set (or via ATM10_SERVICE_TOKEN), require header X-ATM10-Token."
        ),
    )
    parser.add_argument(
        "--allow-insecure-no-token",
        action="store_true",
        help=(
            "Allow binding to a non-loopback host without a service token. "
            "Intended only for explicit local-network testing."
        ),
    )
    parser.add_argument(
        "--expose-openapi",
        action="store_true",
        help="Expose /docs and /openapi.json for local debugging (default: disabled).",
    )
    parser.add_argument(
        "--voice-service-url",
        type=str,
        default=None,
        help="Optional base URL for voice_runtime_service health probes in the operator snapshot.",
    )
    parser.add_argument(
        "--tts-service-url",
        type=str,
        default=None,
        help="Optional base URL for tts_runtime_service health probes in the operator snapshot.",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=None,
        help="Optional base URL for external Qdrant readiness probes in the operator snapshot.",
    )
    parser.add_argument(
        "--neo4j-url",
        type=str,
        default=None,
        help="Optional base URL for external Neo4j readiness probes in the operator snapshot.",
    )
    parser.add_argument(
        "--neo4j-database",
        type=str,
        default="neo4j",
        help="Neo4j database name for operator readiness probes.",
    )
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default="neo4j",
        help="Neo4j user for operator readiness probes.",
    )
    parser.add_argument(
        "--operator-health-timeout-sec",
        type=float,
        default=1.5,
        help="Timeout in seconds for optional downstream health probes in /v1/operator/snapshot.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        service_token = _validate_bind_security(
            host=args.host,
            service_token=args.service_token,
            allow_insecure_no_token=args.allow_insecure_no_token,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    policy = GatewayHTTPPolicy(
        max_request_body_bytes=args.max_request_bytes,
        max_json_depth=args.max_json_depth,
        max_string_length=args.max_string_length,
        max_array_items=args.max_array_items,
        max_object_keys=args.max_object_keys,
        operation_timeout_sec=args.operation_timeout_sec,
        error_log_max_bytes=args.error_log_max_bytes,
        error_log_max_files=args.error_log_max_files,
        artifact_retention_days=args.artifact_retention_days,
        enable_error_redaction=args.enable_error_redaction,
    )
    app = create_app(
        runs_dir=args.runs_dir,
        operator_runs_dir=args.operator_runs_dir,
        policy=policy,
        service_token=service_token,
        expose_openapi=args.expose_openapi,
        voice_service_url=args.voice_service_url,
        tts_service_url=args.tts_service_url,
        qdrant_url=args.qdrant_url,
        neo4j_url=args.neo4j_url,
        neo4j_database=args.neo4j_database,
        neo4j_user=args.neo4j_user,
        operator_health_timeout_sec=args.operator_health_timeout_sec,
    )
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - dependency presence
        raise SystemExit("uvicorn is required. Install fastapi + uvicorn.") from exc

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
