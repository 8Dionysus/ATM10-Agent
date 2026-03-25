from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error as url_error
from urllib import request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.combo_a_profile import (
    DEFAULT_COMBO_A_NEO4J_DATABASE,
    DEFAULT_COMBO_A_NEO4J_URL,
    DEFAULT_COMBO_A_NEO4J_USER,
    DEFAULT_COMBO_A_QDRANT_URL,
)

SCHEMA_VERSION = "operator_product_startup_v1"
DEFAULT_LIVE_ASR_LANGUAGE = "ru"
DEFAULT_LIVE_ASR_MAX_NEW_TOKENS = 64
DEFAULT_LIVE_PILOT_VLM_MAX_NEW_TOKENS = 64
DEFAULT_LIVE_PILOT_TEXT_MAX_NEW_TOKENS = 96
DEFAULT_LIVE_PILOT_HYBRID_TIMEOUT_SEC = 1.5
DEFAULT_LIVE_PILOT_GATEWAY_TOPK = 3
DEFAULT_LIVE_PILOT_GATEWAY_CANDIDATE_K = 6
DEFAULT_LIVE_PILOT_MAX_ENTITIES_PER_DOC = 32
DEFAULT_LIVE_PILOT_INPUT_DEVICE_INDEX = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc_timestamp(raw_value: Any) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
    args.pilot_runtime_runs_dir = (
        Path(args.pilot_runtime_runs_dir) if args.pilot_runtime_runs_dir is not None else args.runs_dir / "pilot-runtime"
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
        voice_runtime_command = [
            sys.executable,
            "scripts/voice_runtime_service.py",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.voice_runtime_port),
            "--runs-dir",
            str(args.voice_runtime_runs_dir),
            "--asr-language",
            str(args.voice_asr_language),
            "--asr-max-new-tokens",
            str(args.voice_asr_max_new_tokens),
        ]
        if args.voice_asr_warmup_request:
            voice_runtime_command.append("--asr-warmup-request")
        if args.voice_asr_warmup_language is not None:
            voice_runtime_command.extend(["--asr-warmup-language", str(args.voice_asr_warmup_language)])
        managed_processes["voice_runtime_service"] = {
            "managed": True,
            "url": voice_runtime_url,
            "runs_dir": str(args.voice_runtime_runs_dir),
            "command": voice_runtime_command,
        }
    else:
        managed_processes["voice_runtime_service"] = {
            "managed": False,
            "url": voice_runtime_url,
            "runs_dir": str(args.voice_runtime_runs_dir),
            "command": None,
        }

    if args.start_tts_runtime:
        tts_runtime_command = [
            sys.executable,
            "scripts/tts_runtime_service.py",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.tts_runtime_port),
            "--runs-dir",
            str(args.tts_runtime_runs_dir),
        ]
        if args.tts_piper_executable is not None:
            tts_runtime_command.extend(["--tts-piper-executable", str(args.tts_piper_executable)])
        if args.tts_piper_model_path is not None:
            tts_runtime_command.extend(["--tts-piper-model-path", str(args.tts_piper_model_path)])
        if args.tts_piper_speaker is not None:
            tts_runtime_command.extend(["--tts-piper-speaker", str(args.tts_piper_speaker)])
        tts_runtime_url = f"http://127.0.0.1:{args.tts_runtime_port}"
        managed_processes["tts_runtime_service"] = {
            "managed": True,
            "url": tts_runtime_url,
            "runs_dir": str(args.tts_runtime_runs_dir),
            "command": tts_runtime_command,
        }
    else:
        managed_processes["tts_runtime_service"] = {
            "managed": False,
            "url": tts_runtime_url,
            "runs_dir": str(args.tts_runtime_runs_dir),
            "command": None,
        }

    if args.start_pilot_runtime:
        pilot_command = [
            sys.executable,
            "scripts/pilot_runtime_loop.py",
            "--runs-dir",
            str(args.pilot_runtime_runs_dir),
            "--gateway-url",
            gateway_url,
            "--pilot-hotkey",
            str(args.pilot_hotkey),
            "--pilot-vlm-model-dir",
            str(args.pilot_vlm_model_dir),
            "--pilot-text-model-dir",
            str(args.pilot_text_model_dir),
            "--pilot-vlm-device",
            str(args.pilot_vlm_device),
            "--pilot-text-device",
            str(args.pilot_text_device),
            "--pilot-vlm-provider",
            str(args.pilot_vlm_provider),
            "--pilot-text-provider",
            str(args.pilot_text_provider),
            "--pilot-vlm-max-new-tokens",
            str(args.pilot_vlm_max_new_tokens),
            "--pilot-text-max-new-tokens",
            str(args.pilot_text_max_new_tokens),
            "--pilot-hybrid-timeout-sec",
            str(args.pilot_hybrid_timeout_sec),
            "--pilot-gateway-topk",
            str(args.pilot_gateway_topk),
            "--pilot-gateway-candidate-k",
            str(args.pilot_gateway_candidate_k),
            "--pilot-max-entities-per-doc",
            str(args.pilot_max_entities_per_doc),
            "--asr-language",
            str(args.voice_asr_language),
            "--asr-max-new-tokens",
            str(args.voice_asr_max_new_tokens),
        ]
        if args.voice_asr_warmup_request:
            pilot_command.append("--asr-warmup-request")
        if args.voice_asr_warmup_language is not None:
            pilot_command.extend(["--asr-warmup-language", str(args.voice_asr_warmup_language)])
        if args.pilot_input_device_index is not None:
            pilot_command.extend(["--input-device-index", str(args.pilot_input_device_index)])
        if voice_runtime_url:
            pilot_command.extend(["--voice-runtime-url", voice_runtime_url])
        if tts_runtime_url:
            pilot_command.extend(["--tts-runtime-url", tts_runtime_url])
        if args.capture_monitor is not None:
            pilot_command.extend(["--capture-monitor", str(args.capture_monitor)])
        if args.capture_region is not None:
            pilot_command.extend(["--capture-region", str(args.capture_region)])
        if args.pilot_hud_hook_json is not None:
            pilot_command.extend(["--hud-hook-json", str(args.pilot_hud_hook_json)])
        if args.pilot_tesseract_bin is not None:
            pilot_command.extend(["--tesseract-bin", str(args.pilot_tesseract_bin)])
        managed_processes["pilot_runtime"] = {
            "managed": True,
            "configured": True,
            "url": None,
            "runs_dir": str(args.pilot_runtime_runs_dir),
            "status_json": str(args.pilot_runtime_runs_dir / "pilot_runtime_status_latest.json"),
            "command": pilot_command,
            "launch_after": "gateway",
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
            "pilot_runtime_runs_dir": str(args.pilot_runtime_runs_dir),
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
        configured = bool(service_plan.get("configured", bool(service_plan.get("url"))))
        session_state[service_name] = {
            "service_name": service_name,
            "managed": bool(service_plan.get("managed")),
            "configured": configured,
            "effective_url": service_plan.get("url"),
            "runs_dir": service_plan.get("runs_dir"),
            "log_path": str(run_dir / f"{service_name}.log"),
            "status": "pending" if service_plan.get("managed") else ("external" if configured else "not_configured"),
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


def _reconcile_final_session_state(
    run_payload: dict[str, Any],
    process_map: dict[str, subprocess.Popen[str]],
    *,
    finished_at_utc: str,
) -> None:
    for service_name, process in process_map.items():
        _update_child_process_state(run_payload, service_name, process)

    session_state = run_payload.get("session_state", {})
    if not isinstance(session_state, dict):
        return

    for service_name, entry in session_state.items():
        if not isinstance(entry, dict):
            continue
        current_status = str(entry.get("status", "")).strip()
        if current_status in {"error", "external", "not_configured"}:
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
    request_timeout = max(0.5, min(timeout_sec, 15.0))
    while time.time() < deadline:
        req = request.Request(url=url, method="GET")
        try:
            with request.urlopen(req, timeout=request_timeout) as response:
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
    request_timeout = max(0.5, min(timeout_sec, 15.0))
    while time.time() < deadline:
        req = request.Request(url=url, method="GET")
        try:
            with request.urlopen(req, timeout=request_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict) and str(payload.get("status", "")).strip() == "ok":
                return payload, None
            last_error = f"unexpected runtime health payload: {payload!r}"
        except Exception as exc:
            last_error = f"{exc}"
        time.sleep(0.5)
    return None, last_error


def _wait_for_pilot_runtime_ready(
    pilot_runs_dir: Path,
    *,
    timeout_sec: float,
    process: subprocess.Popen[str] | None = None,
    min_timestamp_utc: datetime | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    deadline = time.time() + max(timeout_sec, 0.1)
    last_error = "pilot runtime status did not become ready"
    status_path = Path(pilot_runs_dir) / "pilot_runtime_status_latest.json"
    expected_root = Path(pilot_runs_dir).resolve()
    while time.time() < deadline:
        if process is not None and process.poll() is not None:
            return None, f"pilot runtime process exited early with code {process.returncode}"
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and str(payload.get("schema_version", "")).strip() == "pilot_runtime_status_v1":
                status = str(payload.get("status", "")).strip().lower()
                if status in {"running", "degraded", "ok"}:
                    payload_timestamp = _parse_utc_timestamp(payload.get("timestamp_utc"))
                    if min_timestamp_utc is not None:
                        if payload_timestamp is None:
                            last_error = "pilot runtime status is missing a valid timestamp_utc"
                            time.sleep(0.5)
                            continue
                        if payload_timestamp < (min_timestamp_utc - timedelta(seconds=1)):
                            last_error = "stale pilot runtime status payload is older than the current launch attempt"
                            time.sleep(0.5)
                            continue
                    paths_payload = payload.get("paths")
                    paths_payload = paths_payload if isinstance(paths_payload, dict) else {}
                    run_dir_value = str(paths_payload.get("run_dir", "")).strip()
                    if not run_dir_value:
                        last_error = "pilot runtime status is missing paths.run_dir"
                        time.sleep(0.5)
                        continue
                    run_dir = Path(run_dir_value).resolve()
                    if run_dir.parent != expected_root:
                        last_error = f"pilot runtime status points to unexpected run_dir: {run_dir_value}"
                        time.sleep(0.5)
                        continue
                    return payload, None
                last_error = f"unexpected pilot runtime status payload: {payload!r}"
            else:
                last_error = f"unexpected pilot runtime status payload: {payload!r}"
        except FileNotFoundError:
            last_error = f"{status_path} not found yet"
        except Exception as exc:
            last_error = f"{exc}"
        time.sleep(0.5)
    return None, last_error


def _wait_for_streamlit_ready(
    streamlit_url: str,
    *,
    timeout_sec: float,
    process: subprocess.Popen[str] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    deadline = time.time() + max(timeout_sec, 0.1)
    last_error = "streamlit did not become ready"
    url = streamlit_url.rstrip("/") + "/"
    request_timeout = max(0.5, min(timeout_sec, 15.0))
    while time.time() < deadline:
        if process is not None and process.poll() is not None:
            return None, f"streamlit process exited early with code {process.returncode}"
        req = request.Request(url=url, method="GET")
        try:
            with request.urlopen(req, timeout=request_timeout):
                return {"status": "ok", "url": url}, None
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
        help="Timeout waiting for managed services, gateway, and Streamlit to become ready.",
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
        "--voice-asr-language",
        type=str,
        default=DEFAULT_LIVE_ASR_LANGUAGE,
        help="Static language hint for managed live ASR (default: ru).",
    )
    parser.add_argument(
        "--voice-asr-max-new-tokens",
        type=int,
        default=DEFAULT_LIVE_ASR_MAX_NEW_TOKENS,
        help="ASR token budget for managed live voice runtime.",
    )
    parser.add_argument(
        "--voice-asr-warmup-request",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run one managed ASR warmup request on startup (default: enabled).",
    )
    parser.add_argument(
        "--voice-asr-warmup-language",
        type=str,
        default=DEFAULT_LIVE_ASR_LANGUAGE,
        help="Language hint for the managed ASR warmup request (default: ru).",
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
        "--tts-piper-executable",
        type=str,
        default=None,
        help="Optional Piper executable override forwarded to managed tts_runtime_service.",
    )
    parser.add_argument(
        "--tts-piper-model-path",
        type=str,
        default=None,
        help="Optional Piper model path forwarded to managed tts_runtime_service.",
    )
    parser.add_argument(
        "--tts-piper-speaker",
        type=str,
        default=None,
        help="Optional Piper speaker override forwarded to managed tts_runtime_service.",
    )
    parser.add_argument(
        "--start-pilot-runtime",
        action="store_true",
        help="Launch pilot_runtime_loop as a managed child process.",
    )
    parser.add_argument(
        "--pilot-runtime-runs-dir",
        type=Path,
        default=None,
        help="Managed pilot runtime runs directory (default: <runs-dir>/pilot-runtime).",
    )
    parser.add_argument(
        "--pilot-hotkey",
        type=str,
        default="F8",
        help="Pilot push-to-talk hotkey (default: F8).",
    )
    parser.add_argument(
        "--capture-monitor",
        type=int,
        default=None,
        help="Windows monitor index for pilot live capture.",
    )
    parser.add_argument(
        "--capture-region",
        type=str,
        default=None,
        help="Optional pilot capture region formatted as x,y,w,h.",
    )
    parser.add_argument(
        "--pilot-hud-hook-json",
        type=Path,
        default=None,
        help="Optional path to the latest ATM10 HUD mod-hook payload JSON for the managed pilot runtime.",
    )
    parser.add_argument(
        "--pilot-tesseract-bin",
        type=str,
        default=None,
        help="Optional Tesseract binary override for additive pilot HUD OCR.",
    )
    parser.add_argument(
        "--pilot-vlm-model-dir",
        type=Path,
        default=Path("models") / "qwen2.5-vl-7b-instruct-int4-ov",
        help="Pilot local VLM model dir.",
    )
    parser.add_argument(
        "--pilot-text-model-dir",
        type=Path,
        default=Path("models") / "qwen3-8b-int4-cw-ov",
        help="Pilot local grounded-reply model dir.",
    )
    parser.add_argument(
        "--pilot-vlm-device",
        type=str,
        default="GPU",
        help="OpenVINO device for pilot VLM (default: GPU).",
    )
    parser.add_argument(
        "--pilot-text-device",
        type=str,
        default="NPU",
        help="OpenVINO device for pilot grounded-reply model (default: NPU).",
    )
    parser.add_argument(
        "--pilot-vlm-provider",
        choices=("openvino", "stub"),
        default="openvino",
        help="Pilot VLM provider passed to pilot_runtime_loop.py (default: openvino; use stub only for diagnostics).",
    )
    parser.add_argument(
        "--pilot-text-provider",
        choices=("openvino", "stub"),
        default="openvino",
        help="Pilot grounded-reply provider passed to pilot_runtime_loop.py (default: openvino; use stub only for diagnostics).",
    )
    parser.add_argument(
        "--pilot-input-device-index",
        type=int,
        default=DEFAULT_LIVE_PILOT_INPUT_DEVICE_INDEX,
        help="Explicit sounddevice input device index passed to pilot_runtime_loop.py (default: 1).",
    )
    parser.add_argument(
        "--pilot-vlm-max-new-tokens",
        type=int,
        default=DEFAULT_LIVE_PILOT_VLM_MAX_NEW_TOKENS,
        help="VLM token budget for the managed pilot runtime.",
    )
    parser.add_argument(
        "--pilot-text-max-new-tokens",
        type=int,
        default=DEFAULT_LIVE_PILOT_TEXT_MAX_NEW_TOKENS,
        help="Grounded-reply token budget for the managed pilot runtime.",
    )
    parser.add_argument(
        "--pilot-hybrid-timeout-sec",
        type=float,
        default=DEFAULT_LIVE_PILOT_HYBRID_TIMEOUT_SEC,
        help="Pilot-side timeout for opportunistic hybrid queries.",
    )
    parser.add_argument(
        "--pilot-gateway-topk",
        type=int,
        default=DEFAULT_LIVE_PILOT_GATEWAY_TOPK,
        help="Live pilot hybrid top-k budget.",
    )
    parser.add_argument(
        "--pilot-gateway-candidate-k",
        type=int,
        default=DEFAULT_LIVE_PILOT_GATEWAY_CANDIDATE_K,
        help="Live pilot hybrid candidate-k budget.",
    )
    parser.add_argument(
        "--pilot-max-entities-per-doc",
        type=int,
        default=DEFAULT_LIVE_PILOT_MAX_ENTITIES_PER_DOC,
        help="Live pilot hybrid entity budget per document.",
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
            "pilot_runtime": plan["managed_processes"].get("pilot_runtime", {}).get("status_json"),
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

        pilot_plan = plan["managed_processes"].get("pilot_runtime", {})
        if pilot_plan.get("managed"):
            pilot_launch_started_at = datetime.now(timezone.utc)
            process = _launch_process(pilot_plan["command"], run_dir / "pilot_runtime.log")
            managed_processes.append(("pilot_runtime", process))
            process_map["pilot_runtime"] = process
            _update_session_entry(
                run_payload,
                "pilot_runtime",
                status="starting",
                pid=process.pid,
                started_at_utc=_utc_now(),
                last_event="process_started",
            )
            _update_child_process_state(run_payload, "pilot_runtime", process)
            _append_startup_checkpoint(
                run_payload,
                stage="launch",
                status="ok",
                service_name="pilot_runtime",
                message="pilot runtime process started",
                details={"pid": process.pid, "runs_dir": pilot_plan.get("runs_dir")},
            )
            _write_json(run_json_path, run_payload)
            pilot_status_payload, pilot_status_error = _wait_for_pilot_runtime_ready(
                Path(str(pilot_plan.get("runs_dir"))),
                timeout_sec=args.startup_timeout_sec,
                process=process,
                min_timestamp_utc=pilot_launch_started_at,
            )
            if pilot_status_payload is None:
                _mark_probe_result(
                    run_payload,
                    "pilot_runtime",
                    payload=None,
                    error=pilot_status_error,
                )
                _append_startup_checkpoint(
                    run_payload,
                    stage="probe",
                    status="error",
                    service_name="pilot_runtime",
                    message="pilot runtime status probe failed",
                    details={"error": pilot_status_error},
                )
                raise RuntimeError(
                    f"pilot_runtime did not become ready within startup timeout: {pilot_status_error}"
                )
            _mark_probe_result(
                run_payload,
                "pilot_runtime",
                payload={
                    "status": pilot_status_payload.get("status"),
                    "state": pilot_status_payload.get("state"),
                    "last_turn_id": pilot_status_payload.get("last_turn_id"),
                },
                error=None,
            )
            _append_startup_checkpoint(
                run_payload,
                stage="probe",
                status="ok",
                service_name="pilot_runtime",
                message="pilot runtime status probe succeeded",
                details={"status": pilot_status_payload.get("status"), "state": pilot_status_payload.get("state")},
            )
            _write_json(run_json_path, run_payload)

        streamlit_process = _launch_process(plan["streamlit"]["command"], run_dir / "streamlit.log")
        process_map["streamlit"] = streamlit_process
        _update_session_entry(
            run_payload,
            "streamlit",
            status="starting",
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
        _write_json(run_json_path, run_payload)
        streamlit_payload, streamlit_error = _wait_for_streamlit_ready(
            plan["streamlit"]["url"],
            timeout_sec=args.startup_timeout_sec,
            process=streamlit_process,
        )
        if streamlit_payload is None:
            _mark_probe_result(
                run_payload,
                "streamlit",
                payload=None,
                error=streamlit_error,
            )
            _append_startup_checkpoint(
                run_payload,
                stage="probe",
                status="error",
                service_name="streamlit",
                message="streamlit readiness probe failed",
                details={"error": streamlit_error},
            )
            _write_json(run_json_path, run_payload)
            raise RuntimeError(
                "Streamlit did not become ready within startup timeout: "
                f"{streamlit_error}"
            )
        _mark_probe_result(
            run_payload,
            "streamlit",
            payload=streamlit_payload,
            error=None,
        )
        _append_startup_checkpoint(
            run_payload,
            stage="probe",
            status="ok",
            service_name="streamlit",
            message="streamlit readiness probe succeeded",
            details={"url": streamlit_payload.get("url")},
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
        _reconcile_final_session_state(
            run_payload,
            process_map,
            finished_at_utc=finished_at_utc,
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
