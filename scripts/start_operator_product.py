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


def build_startup_plan(args: argparse.Namespace) -> dict[str, Any]:
    gateway_url = f"http://{args.gateway_host}:{args.gateway_port}"
    streamlit_url = f"http://127.0.0.1:{args.streamlit_port}"
    voice_runtime_url = args.voice_runtime_url
    tts_runtime_url = args.tts_runtime_url
    managed_processes: dict[str, dict[str, Any]] = {}

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
        "--operator-health-timeout-sec",
        str(args.gateway_timeout_sec),
    ]
    if voice_runtime_url:
        gateway_command.extend(["--voice-service-url", voice_runtime_url])
    if tts_runtime_url:
        gateway_command.extend(["--tts-service-url", tts_runtime_url])

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
        "--gateway-url",
        gateway_url,
        "--gateway-timeout-sec",
        str(args.gateway_timeout_sec),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": "operator_product_core",
        "generated_at_utc": _utc_now(),
        "managed_processes": managed_processes,
        "gateway": {
            "url": gateway_url,
            "runs_dir": str(args.gateway_runs_dir),
            "command": gateway_command,
            "voice_runtime_url": voice_runtime_url,
            "tts_runtime_url": tts_runtime_url,
        },
        "streamlit": {
            "url": streamlit_url,
            "runs_dir": str(args.panel_runs_dir),
            "command": streamlit_command,
        },
    }


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
        default=Path("runs") / "gateway-http",
        help="Gateway runs directory (default: runs/gateway-http).",
    )
    parser.add_argument(
        "--panel-runs-dir",
        type=Path,
        default=Path("runs"),
        help="Streamlit panel runs directory (default: runs).",
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
        default=Path("runs") / "voice-runtime",
        help="Managed voice runtime runs directory (default: runs/voice-runtime).",
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
        default=Path("runs") / "tts-runtime",
        help="Managed TTS runtime runs directory (default: runs/tts-runtime).",
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
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plan = build_startup_plan(args)
    if args.print_plan_json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    now = datetime.now(timezone.utc)
    run_dir = _create_run_dir(args.runs_dir, now)
    run_json_path = run_dir / "run.json"
    run_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "start_operator_product",
        "status": "starting",
        "profile": plan["profile"],
        "gateway_url": plan["gateway"]["url"],
        "streamlit_url": plan["streamlit"]["url"],
        "managed_processes": plan["managed_processes"],
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "gateway_log": str(run_dir / "gateway.log"),
            "streamlit_log": str(run_dir / "streamlit.log"),
        },
        "commands": {
            "gateway": list(plan["gateway"]["command"]),
            "streamlit": list(plan["streamlit"]["command"]),
        },
        "child_processes": {},
    }
    for service_name, service_plan in plan["managed_processes"].items():
        if service_plan.get("managed"):
            run_payload["paths"][f"{service_name}_log"] = str(run_dir / f"{service_name}.log")
            run_payload["commands"][service_name] = list(service_plan["command"])
    _write_json(run_json_path, run_payload)

    gateway_process = None
    streamlit_process = None
    managed_processes: list[tuple[str, subprocess.Popen[str]]] = []
    try:
        for service_name in ("voice_runtime_service", "tts_runtime_service"):
            service_plan = plan["managed_processes"].get(service_name, {})
            if not service_plan.get("managed"):
                continue
            process = _launch_process(service_plan["command"], run_dir / f"{service_name}.log")
            managed_processes.append((service_name, process))
            health_payload, health_error = _wait_for_runtime_health(
                str(service_plan["url"]),
                timeout_sec=args.startup_timeout_sec,
            )
            if health_payload is None:
                raise RuntimeError(
                    f"{service_name} did not become ready within startup timeout: {health_error}"
                )

        gateway_process = _launch_process(plan["gateway"]["command"], run_dir / "gateway.log")
        operator_snapshot, gateway_error = _wait_for_gateway_operator_snapshot(
            plan["gateway"]["url"],
            timeout_sec=args.startup_timeout_sec,
        )
        if operator_snapshot is None:
            raise RuntimeError(
                "Gateway operator snapshot did not become ready within startup timeout: "
                f"{gateway_error}"
            )

        streamlit_process = _launch_process(plan["streamlit"]["command"], run_dir / "streamlit.log")
        run_payload["status"] = "running"
        run_payload["started_at_utc"] = _utc_now()
        run_payload["operator_snapshot_checked_at_utc"] = operator_snapshot.get("checked_at_utc")
        run_payload["child_processes"] = {
            service_name: {"pid": process.pid}
            for service_name, process in managed_processes
        }
        run_payload["child_processes"]["gateway"] = {"pid": gateway_process.pid}
        run_payload["child_processes"]["streamlit"] = {"pid": streamlit_process.pid}
        _write_json(run_json_path, run_payload)

        print(f"[start_operator_product] gateway_url: {plan['gateway']['url']}")
        print(f"[start_operator_product] streamlit_url: {plan['streamlit']['url']}")
        print(f"[start_operator_product] run_dir: {run_dir}")

        while True:
            if gateway_process.poll() is not None:
                raise RuntimeError("gateway process exited unexpectedly")
            if streamlit_process.poll() is not None:
                raise RuntimeError("streamlit process exited unexpectedly")
            time.sleep(1.0)
    except KeyboardInterrupt:
        run_payload["status"] = "stopped"
        run_payload["stopped_at_utc"] = _utc_now()
        _write_json(run_json_path, run_payload)
        return 0
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        run_payload["finished_at_utc"] = _utc_now()
        _write_json(run_json_path, run_payload)
        return 2
    finally:
        if streamlit_process is not None:
            _terminate_process(streamlit_process)
        if gateway_process is not None:
            _terminate_process(gateway_process)
        for _service_name, process in reversed(managed_processes):
            _terminate_process(process)


if __name__ == "__main__":
    raise SystemExit(main())
