from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as url_error
from urllib import request

from src.agent_core.combo_a_profile import (
    DEFAULT_COMBO_A_NEO4J_DATABASE,
    DEFAULT_COMBO_A_NEO4J_URL,
    DEFAULT_COMBO_A_NEO4J_USER,
    DEFAULT_COMBO_A_QDRANT_URL,
)

SCHEMA_VERSION = "operator_product_startup_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_run_dir(root: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-start-operator-product")
    run_dir = root / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir
    suffix = 1
    while True:
        candidate = root / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _resolve_effective_runs_dirs(args: argparse.Namespace) -> argparse.Namespace:
    args.runs_dir = Path(args.runs_dir)
    args.gateway_runs_dir = Path(args.gateway_runs_dir) if args.gateway_runs_dir is not None else args.runs_dir / "gateway-http"
    args.panel_runs_dir = Path(args.panel_runs_dir) if args.panel_runs_dir is not None else args.runs_dir
    args.voice_runtime_runs_dir = (
        Path(args.voice_runtime_runs_dir) if args.voice_runtime_runs_dir is not None else args.runs_dir / "voice-runtime"
    )
    args.tts_runtime_runs_dir = (
        Path(args.tts_runtime_runs_dir) if args.tts_runtime_runs_dir is not None else args.runs_dir / "tts-runtime"
    )
    return args


def build_startup_plan(args: argparse.Namespace) -> dict[str, Any]:
    gateway_url = f"http://{args.gateway_host}:{args.gateway_port}"
    streamlit_url = f"http://127.0.0.1:{args.streamlit_port}"
    voice_runtime_url = args.voice_runtime_url
    tts_runtime_url = args.tts_runtime_url
    managed_processes: dict[str, dict[str, Any]] = {}
    external_services = {
        "qdrant": {
            "managed": False,
            "url": args.qdrant_url,
            "runs_dir": None,
            "command": None,
        },
        "neo4j": {
            "managed": False,
            "url": args.neo4j_url,
            "runs_dir": None,
            "command": None,
            "database": args.neo4j_database,
            "user": args.neo4j_user,
        },
    }

    if args.start_voice_runtime:
        voice_runtime_url = f"http://127.0.0.1:{args.voice_runtime_port}"
        managed_processes["voice_runtime_service"] = {
            "managed": True,
            "url": voice_runtime_url,
            "runs_dir": str(args.voice_runtime_runs_dir),
            "command": [
                sys.executable,
                "scripts/voice_runtime_service.py",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.voice_runtime_port),
                "--runs-dir",
                str(args.voice_runtime_runs_dir),
            ],
        }
    else:
        managed_processes["voice_runtime_service"] = {
            "managed": False,
            "url": voice_runtime_url,
            "runs_dir": str(args.voice_runtime_runs_dir),
            "command": None,
        }

    if args.start_tts_runtime:
        tts_runtime_url = f"http://127.0.0.1:{args.tts_runtime_port}"
        managed_processes["tts_runtime_service"] = {
            "managed": True,
            "url": tts_runtime_url,
            "runs_dir": str(args.tts_runtime_runs_dir),
            "command": [
                sys.executable,
                "scripts/tts_runtime_service.py",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.tts_runtime_port),
                "--runs-dir",
                str(args.tts_runtime_runs_dir),
            ],
        }
    else:
        managed_processes["tts_runtime_service"] = {
            "managed": False,
            "url": tts_runtime_url,
            "runs_dir": str(args.tts_runtime_runs_dir),
            "command": None,
        }

    gateway_command = [
        sys.executable,
        "scripts/gateway_v1_http_service.py",
        "--host",
        args.gateway_host,
        "--port",
        str(args.gateway_port),
        "--runs-dir",
        str(args.gateway_runs_dir),
        "--operator-runs-dir",
        str(args.runs_dir),
        "--operator-health-timeout-sec",
        str(args.gateway_timeout_sec),
    ]
    if voice_runtime_url:
        gateway_command.extend(["--voice-service-url", voice_runtime_url])
    if tts_runtime_url:
        gateway_command.extend(["--tts-service-url", tts_runtime_url])
    if args.qdrant_url:
        gateway_command.extend(["--qdrant-url", args.qdrant_url])
    if args.neo4j_url:
        gateway_command.extend(
            [
                "--neo4j-url",
                args.neo4j_url,
                "--neo4j-database",
                args.neo4j_database,
                "--neo4j-user",
                args.neo4j_user,
            ]
        )

    streamlit_command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "scripts/streamlit_operator_panel.py",
        "--server.headless",
        "true",
        "--server.port",
        str(args.streamlit_port),
        "--",
        "--runs-dir",
        str(args.panel_runs_dir),
        "--operator-runs-dir",
        str(args.runs_dir),
        "--gateway-url",
        gateway_url,
        "--gateway-timeout-sec",
        str(args.gateway_timeout_sec),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": "operator_product_core",
        "generated_at_utc": _utc_now(),
        "artifact_roots": {
            "operator_runs_dir": str(args.runs_dir),
            "panel_runs_dir": str(args.panel_runs_dir),
            "gateway_runs_dir": str(args.gateway_runs_dir),
            "voice_runtime_runs_dir": str(args.voice_runtime_runs_dir),
            "tts_runtime_runs_dir": str(args.tts_runtime_runs_dir),
        },
        "managed_processes": managed_processes,
        "external_services": external_services,
        "gateway": {
            "url": gateway_url,
            "runs_dir": str(args.gateway_runs_dir),
            "command": gateway_command,
            "voice_runtime_url": voice_runtime_url,
            "tts_runtime_url": tts_runtime_url,
            "qdrant_url": args.qdrant_url,
            "neo4j_url": args.neo4j_url,
            "neo4j_database": args.neo4j_database,
            "neo4j_user": args.neo4j_user,
        },
        "streamlit": {
            "url": streamlit_url,
            "runs_dir": str(args.panel_runs_dir),
            "command": streamlit_command,
        },
    }


def _build_initial_session_state(plan: dict[str, Any], run_dir: Path) -> dict[str, dict[str, Any]]:
    session_state: dict[str, dict[str, Any]] = {}
    for service_name, service_plan in plan["managed_processes"].items():
        session_state[service_name] = {
            "service_name": service_name,
            "managed": bool(service_plan.get("managed")),
            "configured": bool(service_plan.get("url")),
            "effective_url": service_plan.get("url"),
            "runs_dir": service_plan.get("runs_dir"),
            "log_path": str(run_dir / f"{service_name}.log"),
            "status": "pending" if service_plan.get("managed") else (
                "external" if service_plan.get("url") else "not_configured"
            ),
            "pid": None,
            "last_probe": None,
            "error": None,
            "started_at_utc": None,
            "finished_at_utc": None,
            "last_event": "plan_resolved",
        }

    for service_name, service_plan in plan.get("external_services", {}).items():
        session_state[service_name] = {
            "service_name": service_name,
            "managed": False,
            "configured": bool(service_plan.get("url")),
            "effective_url": service_plan.get("url"),
            "runs_dir": service_plan.get("runs_dir"),
            "log_path": None,
            "status": "external" if service_plan.get("url") else "not_configured",
            "pid": None,
            "last_probe": None,
            "error": None,
            "started_at_utc": None,
            "finished_at_utc": None,
            "last_event": "plan_resolved",
        }

    session_state["gateway"] = {
        "service_name": "gateway",
        "managed": True,
        "configured": True,
        "effective_url": plan["gateway"]["url"],
        "runs_dir": plan["gateway"]["runs_dir"],
        "log_path": str(run_dir / "gateway.log"),
        "status": "pending",
        "pid": None,
        "last_probe": None,
        "error": None,
        "started_at_utc": None,
        "finished_at_utc": None,
        "last_event": "plan_resolved",
    }
    session_state["streamlit"] = {
        "service_name": "streamlit",
        "managed": True,
        "configured": True,
        "effective_url": plan["streamlit"]["url"],
        "runs_dir": plan["streamlit"]["runs_dir"],
        "log_path": str(run_dir / "streamlit.log"),
        "status": "pending",
        "pid": None,
        "last_probe": None,
        "error": None,
        "started_at_utc": None,
        "finished_at_utc": None,
        "last_event": "plan_resolved",
    }
    return session_state


def _update_session_entry(
    run_payload: dict[str, Any],
    service_name: str,
    **updates: Any,
) -> None:
    session_state = run_payload.setdefault("session_state", {})
    entry = session_state.setdefault(service_name, {"service_name": service_name})
    for key, value in updates.items():
        if value is not None:
            entry[key] = value


def _append_startup_checkpoint(
    run_payload: dict[str, Any],
    *,
    stage: str,
    status: str,
    service_name: str | None = None,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    checkpoint = {
        "timestamp_utc": _utc_now(),
        "stage": stage,
        "status": status,
        "service_name": service_name,
        "message": message,
        "details": details or {},
    }
    run_payload.setdefault("startup_checkpoints", []).append(checkpoint)
    run_payload["last_checkpoint"] = checkpoint


def _update_child_process_state(
    run_payload: dict[str, Any],
    service_name: str,
    process: subprocess.Popen[str] | None,
) -> None:
    child_processes = run_payload.setdefault("child_processes", {})
    if process is None:
        child_processes.setdefault(service_name, {"pid": None, "return_code": None})
        return
    child_processes[service_name] = {
        "pid": process.pid,
        "return_code": process.returncode if process.poll() is not None else None,
    }


def _mark_probe_result(
    run_payload: dict[str, Any],
    service_name: str,
    *,
    payload: dict[str, Any] | None,
    error: str | None,
) -> None:
    probe_status = "ok" if payload is not None else "error"
    probe_payload = {
        "checked_at_utc": _utc_now(),
        "status": probe_status,
        "error": error,
        "payload": payload,
    }
    updates: dict[str, Any] = {
        "last_probe": probe_payload,
        "last_event": "probe_ok" if payload is not None else "probe_error",
    }
    if payload is not None:
        updates["status"] = "running"
        updates["error"] = None
    else:
        updates["status"] = "error"
        updates["error"] = error
        updates["finished_at_utc"] = _utc_now()
    _update_session_entry(run_payload, service_name, **updates)


def _wait_for_gateway_operator_snapshot(
    gateway_url: str,
    *,
    timeout_sec: float,
) -> tuple[dict[str, Any] | None, str | None]:
    deadline = time.time() + max(timeout_sec, 0.1)
    last_error = "gateway operator snapshot did not become ready"
    url = gateway_url.rstrip("/") + "/v1/operator/snapshot"
    while time.time() < deadline:
        req = request.Request(url=url, method="GET")
        try:
            with request.urlopen(req, timeout=min(2.0, timeout_sec)) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict) and str(payload.get("status", "")).strip() == "ok":
                return payload, None
            last_error = f"unexpected gateway operator snapshot payload: {payload!r}"
        except Exception as exc:
            last_error = f"{exc}"
        time.sleep(0.5)
    return None, last_error


def _wait_for_runtime_health(
    service_url: str,
    *,
    timeout_sec: float,
) -> tuple[dict[str, Any] | None, str | None]:
    deadline = time.time() + max(timeout_sec, 0.1)
    last_error = "runtime health did not become ready"
    url = service_url.rstrip("/") + "/health"
    while time.time() < deadline:
        req = request.Request(url=url, method="GET")
        try:
            with request.urlopen(req, timeout=min(2.0, timeout_sec)) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict) and str(payload.get("status", "")).strip() == "ok":
                return payload, None
            last_error = f"unexpected runtime health payload: {payload!r}"
        except Exception as exc:
            last_error = f"{exc}"
        time.sleep(0.5)
    return None, last_error


def _launch_process(command: list[str], log_path: Path) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8", newline="\n")
    try:
        process = subprocess.Popen(
            command,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except Exception:
        log_handle.close()
        raise
    process._codex_log_handle = log_handle  # type: ignore[attr-defined]
    return process


def _close_process_log_handle(process: subprocess.Popen[str]) -> None:
    handle = getattr(process, "_codex_log_handle", None)
    if handle is not None:
        try:
            handle.close()
        except Exception:
            pass


def _terminate_process(process: subprocess.Popen[str], *, timeout_sec: float = 10.0) -> None:
    if process.poll() is not None:
        _close_process_log_handle(process)
        return
    try:
        process.terminate()
        process.wait(timeout=timeout_sec)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=timeout_sec)
        except Exception:
            pass
    finally:
        _close_process_log_handle(process)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Primary startup profile for the operator product core.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Base runs directory.")
    parser.add_argument(
        "--gateway-runs-dir",
        type=Path,
        default=None,
        help="Gateway runs directory (default: <runs-dir>/gateway-http).",
    )
    parser.add_argument(
        "--panel-runs-dir",
        type=Path,
        default=None,
        help="Streamlit panel runs directory (default: <runs-dir>).",
    )
    parser.add_argument("--gateway-host", default="127.0.0.1", help="Gateway bind host.")
    parser.add_argument("--gateway-port", type=int, default=8770, help="Gateway port.")
    parser.add_argument("--streamlit-port", type=int, default=8501, help="Streamlit port.")
    parser.add_argument(
        "--gateway-timeout-sec",
        type=float,
        default=3.0,
        help="Gateway/operator snapshot timeout in seconds.",
    )
    parser.add_argument(
        "--startup-timeout-sec",
        type=float,
        default=20.0,
        help="Timeout waiting for the gateway operator snapshot to become ready.",
    )
    parser.add_argument(
        "--voice-runtime-url",
        type=str,
        default=None,
        help="Optional voice runtime base URL to expose through the gateway operator snapshot.",
    )
    parser.add_argument(
        "--start-voice-runtime",
        action="store_true",
        help="Launch voice_runtime_service as a managed child process.",
    )
    parser.add_argument(
        "--voice-runtime-port",
        type=int,
        default=8765,
        help="Managed voice runtime port (default: 8765).",
    )
    parser.add_argument(
        "--voice-runtime-runs-dir",
        type=Path,
        default=None,
        help="Managed voice runtime runs directory (default: <runs-dir>/voice-runtime).",
    )
    parser.add_argument(
        "--tts-runtime-url",
        type=str,
        default=None,
        help="Optional TTS runtime base URL to expose through the gateway operator snapshot.",
    )
    parser.add_argument(
        "--start-tts-runtime",
        action="store_true",
        help="Launch tts_runtime_service as a managed child process.",
    )
    parser.add_argument(
        "--tts-runtime-port",
        type=int,
        default=8780,
        help="Managed TTS runtime port (default: 8780).",
    )
    parser.add_argument(
        "--tts-runtime-runs-dir",
        type=Path,
        default=None,
        help="Managed TTS runtime runs directory (default: <runs-dir>/tts-runtime).",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=None,
        help=f"Optional external Qdrant URL to probe and expose (example: {DEFAULT_COMBO_A_QDRANT_URL}).",
    )
    parser.add_argument(
        "--neo4j-url",
        type=str,
        default=None,
        help=f"Optional external Neo4j URL to probe and expose (example: {DEFAULT_COMBO_A_NEO4J_URL}).",
    )
    parser.add_argument(
        "--neo4j-database",
        type=str,
        default=DEFAULT_COMBO_A_NEO4J_DATABASE,
        help="Neo4j database name for external readiness probes.",
    )
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default=DEFAULT_COMBO_A_NEO4J_USER,
        help="Neo4j user for external readiness probes.",
    )
    parser.add_argument(
        "--print-plan-json",
        action="store_true",
        help="Print the resolved startup plan as JSON and exit without launching processes.",
    )
    args = parser.parse_args(argv)
    if args.start_voice_runtime and args.voice_runtime_url:
        parser.error("--start-voice-runtime cannot be combined with --voice-runtime-url.")
    if args.start_tts_runtime and args.tts_runtime_url:
        parser.error("--start-tts-runtime cannot be combined with --tts-runtime-url.")
    return _resolve_effective_runs_dirs(args)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_startup_plan(args)
    if args.print_plan_json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    now = datetime.now(timezone.utc)
    run_dir = _create_run_dir(args.runs_dir, now)
    run_json_path = run_dir / "run.json"
    startup_plan_json_path = run_dir / "startup_plan.json"
    _write_json(startup_plan_json_path, plan)
    run_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "start_operator_product",
        "status": "starting",
        "profile": plan["profile"],
        "gateway_url": plan["gateway"]["url"],
        "streamlit_url": plan["streamlit"]["url"],
        "effective_urls": {
            "gateway": plan["gateway"]["url"],
            "streamlit": plan["streamlit"]["url"],
            "voice_runtime_service": plan["gateway"].get("voice_runtime_url"),
            "tts_runtime_service": plan["gateway"].get("tts_runtime_url"),
            "qdrant": plan["gateway"].get("qdrant_url"),
            "neo4j": plan["gateway"].get("neo4j_url"),
        },
        "artifact_roots": dict(plan.get("artifact_roots") or {}),
        "managed_processes": plan["managed_processes"],
        "external_services": plan.get("external_services", {}),
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "startup_plan_json": str(startup_plan_json_path),
            "gateway_log": str(run_dir / "gateway.log"),
            "streamlit_log": str(run_dir / "streamlit.log"),
        },
        "commands": {
            "gateway": list(plan["gateway"]["command"]),
            "streamlit": list(plan["streamlit"]["command"]),
        },
        "session_state": _build_initial_session_state(plan, run_dir),
        "startup_checkpoints": [],
        "last_checkpoint": None,
        "child_processes": {},
    }
    for service_name, service_plan in plan["managed_processes"].items():
        if service_plan.get("managed"):
            run_payload["paths"][f"{service_name}_log"] = str(run_dir / f"{service_name}.log")
            run_payload["commands"][service_name] = list(service_plan["command"])
    _append_startup_checkpoint(
        run_payload,
        stage="plan",
        status="ok",
        message="startup plan resolved",
        details={"profile": plan["profile"]},
    )
    _write_json(run_json_path, run_payload)

    gateway_process = None
    streamlit_process = None
    managed_processes: list[tuple[str, subprocess.Popen[str]]] = []
    process_map: dict[str, subprocess.Popen[str]] = {}
    exit_code = 0
    final_status = "stopped"
    final_error: str | None = None
    try:
        for service_name in ("voice_runtime_service", "tts_runtime_service"):
            service_plan = plan["managed_processes"].get(service_name, {})
            if not service_plan.get("managed"):
                continue
            process = _launch_process(service_plan["command"], run_dir / f"{service_name}.log")
            managed_processes.append((service_name, process))
            process_map[service_name] = process
            _update_session_entry(
                run_payload,
                service_name,
                status="starting",
                pid=process.pid,
                started_at_utc=_utc_now(),
                last_event="process_started",
            )
            _update_child_process_state(run_payload, service_name, process)
            _append_startup_checkpoint(
                run_payload,
                stage="launch",
                status="ok",
                service_name=service_name,
                message="managed runtime process started",
                details={"pid": process.pid, "url": service_plan.get("url")},
            )
            _write_json(run_json_path, run_payload)
            health_payload, health_error = _wait_for_runtime_health(
                str(service_plan["url"]),
                timeout_sec=args.startup_timeout_sec,
            )
            if health_payload is None:
                _mark_probe_result(
                    run_payload,
                    service_name,
                    payload=None,
                    error=health_error,
                )
                _append_startup_checkpoint(
                    run_payload,
                    stage="probe",
                    status="error",
                    service_name=service_name,
                    message="managed runtime health probe failed",
                    details={"error": health_error},
                )
                raise RuntimeError(
                    f"{service_name} did not become ready within startup timeout: {health_error}"
                )
            _mark_probe_result(
                run_payload,
                service_name,
                payload={
                    "status": health_payload.get("status"),
                    "service": health_payload.get("service"),
                },
                error=None,
            )
            _append_startup_checkpoint(
                run_payload,
                stage="probe",
                status="ok",
                service_name=service_name,
                message="managed runtime health probe succeeded",
                details={"status": health_payload.get("status")},
            )
            _write_json(run_json_path, run_payload)

        gateway_process = _launch_process(plan["gateway"]["command"], run_dir / "gateway.log")
        process_map["gateway"] = gateway_process
        _update_session_entry(
            run_payload,
            "gateway",
            status="starting",
            pid=gateway_process.pid,
            started_at_utc=_utc_now(),
            last_event="process_started",
        )
        _update_child_process_state(run_payload, "gateway", gateway_process)
        _append_startup_checkpoint(
            run_payload,
            stage="launch",
            status="ok",
            service_name="gateway",
            message="gateway process started",
            details={"pid": gateway_process.pid, "url": plan["gateway"]["url"]},
        )
        _write_json(run_json_path, run_payload)
        operator_snapshot, gateway_error = _wait_for_gateway_operator_snapshot(
            plan["gateway"]["url"],
            timeout_sec=args.startup_timeout_sec,
        )
        if operator_snapshot is None:
            _mark_probe_result(
                run_payload,
                "gateway",
                payload=None,
                error=gateway_error,
            )
            _append_startup_checkpoint(
                run_payload,
                stage="probe",
                status="error",
                service_name="gateway",
                message="gateway operator snapshot probe failed",
                details={"error": gateway_error},
            )
            raise RuntimeError(
                "Gateway operator snapshot did not become ready within startup timeout: "
                f"{gateway_error}"
            )
        _mark_probe_result(
            run_payload,
            "gateway",
            payload={
                "status": operator_snapshot.get("status"),
                "checked_at_utc": operator_snapshot.get("checked_at_utc"),
            },
            error=None,
        )
        _append_startup_checkpoint(
            run_payload,
            stage="probe",
            status="ok",
            service_name="gateway",
            message="gateway operator snapshot probe succeeded",
            details={"checked_at_utc": operator_snapshot.get("checked_at_utc")},
        )
        stack_services = operator_snapshot.get("stack_services")
        stack_services = stack_services if isinstance(stack_services, dict) else {}
        for service_name in ("qdrant", "neo4j"):
            stack_payload = stack_services.get(service_name)
            if not isinstance(stack_payload, dict):
                continue
            _update_session_entry(
                run_payload,
                service_name,
                status=str(stack_payload.get("status", "unknown")),
                last_probe={
                    "checked_at_utc": operator_snapshot.get("checked_at_utc"),
                    "status": str(stack_payload.get("status", "unknown")),
                    "payload": stack_payload.get("payload"),
                    "error": stack_payload.get("error"),
                },
                error=stack_payload.get("error"),
                last_event="operator_snapshot_probe",
            )

        streamlit_process = _launch_process(plan["streamlit"]["command"], run_dir / "streamlit.log")
        process_map["streamlit"] = streamlit_process
        _update_session_entry(
            run_payload,
            "streamlit",
            status="running",
            pid=streamlit_process.pid,
            started_at_utc=_utc_now(),
            last_event="process_started",
        )
        _update_child_process_state(run_payload, "streamlit", streamlit_process)
        _append_startup_checkpoint(
            run_payload,
            stage="launch",
            status="ok",
            service_name="streamlit",
            message="streamlit process started",
            details={"pid": streamlit_process.pid, "url": plan["streamlit"]["url"]},
        )
        run_payload["status"] = "running"
        run_payload["started_at_utc"] = _utc_now()
        run_payload["operator_snapshot_checked_at_utc"] = operator_snapshot.get("checked_at_utc")
        for service_name, process in process_map.items():
            _update_child_process_state(run_payload, service_name, process)
        _write_json(run_json_path, run_payload)

        print(f"[start_operator_product] gateway_url: {plan['gateway']['url']}")
        print(f"[start_operator_product] streamlit_url: {plan['streamlit']['url']}")
        print(f"[start_operator_product] run_dir: {run_dir}")

        while True:
            if gateway_process.poll() is not None:
                _update_session_entry(
                    run_payload,
                    "gateway",
                    status="error",
                    error="gateway process exited unexpectedly",
                    finished_at_utc=_utc_now(),
                    last_event="unexpected_exit",
                )
                _append_startup_checkpoint(
                    run_payload,
                    stage="watchdog",
                    status="error",
                    service_name="gateway",
                    message="gateway process exited unexpectedly",
                )
                raise RuntimeError("gateway process exited unexpectedly")
            if streamlit_process.poll() is not None:
                _update_session_entry(
                    run_payload,
                    "streamlit",
                    status="error",
                    error="streamlit process exited unexpectedly",
                    finished_at_utc=_utc_now(),
                    last_event="unexpected_exit",
                )
                _append_startup_checkpoint(
                    run_payload,
                    stage="watchdog",
                    status="error",
                    service_name="streamlit",
                    message="streamlit process exited unexpectedly",
                )
                raise RuntimeError("streamlit process exited unexpectedly")
            time.sleep(1.0)
    except KeyboardInterrupt:
        final_status = "stopped"
        exit_code = 0
        _append_startup_checkpoint(
            run_payload,
            stage="shutdown",
            status="ok",
            message="keyboard interrupt received; shutting down operator product",
        )
    except Exception as exc:
        final_status = "error"
        final_error = str(exc)
        exit_code = 2
        _append_startup_checkpoint(
            run_payload,
            stage="shutdown",
            status="error",
            message="operator product startup/runtime failed",
            details={"error": str(exc)},
        )
    finally:
        if streamlit_process is not None:
            _terminate_process(streamlit_process)
        if gateway_process is not None:
            _terminate_process(gateway_process)
        for _service_name, process in reversed(managed_processes):
            _terminate_process(process)
        finished_at_utc = _utc_now()
        for service_name, process in process_map.items():
            _update_child_process_state(run_payload, service_name, process)
            entry = run_payload.get("session_state", {}).get(service_name, {})
            current_status = str(entry.get("status", "")).strip()
            if current_status == "error":
                continue
            if entry.get("pid") is None and current_status == "pending":
                _update_session_entry(
                    run_payload,
                    service_name,
                    status="not_started",
                    finished_at_utc=finished_at_utc,
                    last_event="not_started",
                )
                continue
            _update_session_entry(
                run_payload,
                service_name,
                status="stopped",
                finished_at_utc=finished_at_utc,
                last_event="shutdown",
            )
        run_payload["status"] = final_status
        if final_status == "stopped":
            run_payload["stopped_at_utc"] = finished_at_utc
        if final_status == "error":
            run_payload["finished_at_utc"] = finished_at_utc
            run_payload["error"] = final_error
        _write_json(run_json_path, run_payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
