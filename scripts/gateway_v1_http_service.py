from __future__ import annotations

import argparse
import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.gateway_v1_local import run_gateway_request

RESPONSE_SCHEMA_VERSION = "gateway_response_v1"
FastAPIRequest = Any


@dataclass(frozen=True)
class GatewayHTTPPolicy:
    max_request_body_bytes: int = 262_144
    max_json_depth: int = 8
    max_string_length: int = 8_192
    max_array_items: int = 256
    max_object_keys: int = 256
    operation_timeout_sec: float = 15.0


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


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


def create_app(*, runs_dir: Path, policy: GatewayHTTPPolicy | None = None) -> Any:
    effective_policy = policy or GatewayHTTPPolicy()
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
    except Exception as exc:  # pragma: no cover - dependency presence
        raise RuntimeError("FastAPI is required for gateway_v1_http_service.") from exc

    global FastAPIRequest
    FastAPIRequest = Request

    app = FastAPI(title="ATM10 Gateway v1 HTTP", version="0.1.0")

    @app.get("/healthz")
    def _healthz() -> dict[str, Any]:
        return {
            "timestamp_utc": _utc_now(),
            "status": "ok",
            "service": "gateway_v1_http_service",
            "runs_dir": str(runs_dir),
            "policy": asdict(effective_policy),
        }

    @app.post("/v1/gateway")
    async def _gateway(request: FastAPIRequest) -> Any:
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
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
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
            _append_jsonl(
                runs_dir / "gateway_http_errors.jsonl",
                {
                    "timestamp_utc": _utc_now(),
                    "path": "/v1/gateway",
                    "error_code": "internal_error_sanitized",
                    "error": str(exc),
                    "operation": operation,
                    "request_body_bytes": len(raw_body),
                    "request_context": _build_request_context(request_payload if request_payload else None),
                    "traceback": traceback.format_exc(),
                },
            )
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = GatewayHTTPPolicy(
        max_request_body_bytes=args.max_request_bytes,
        max_json_depth=args.max_json_depth,
        max_string_length=args.max_string_length,
        max_array_items=args.max_array_items,
        max_object_keys=args.max_object_keys,
        operation_timeout_sec=args.operation_timeout_sec,
    )
    app = create_app(runs_dir=args.runs_dir, policy=policy)
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - dependency presence
        raise SystemExit("uvicorn is required. Install fastapi + uvicorn.") from exc

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
