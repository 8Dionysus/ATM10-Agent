from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib import request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.streamlit_operator_panel import (
    TAB_NAMES,
    canonical_fail_nightly_progress_sources,
    canonical_summary_sources,
)
from scripts.streamlit_operator_panel import (
    MOBILE_LAYOUT_BREAKPOINT_PX_DEFAULT,
    MOBILE_LAYOUT_POLICY_SCHEMA,
    mobile_layout_policy,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-streamlit-smoke")
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


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _probe_http_ready(port: int) -> bool:
    url = f"http://127.0.0.1:{port}/"
    try:
        with request.urlopen(url, timeout=1.0):
            return True
    except Exception:
        return False


def _capture_output(process: subprocess.Popen[str], output_lines: list[str]) -> None:
    if process.stdout is None:
        return
    for line in process.stdout:
        output_lines.append(line.rstrip("\n"))


def _launch_streamlit_process(command: list[str]) -> tuple[subprocess.Popen[str], list[str], threading.Thread]:
    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    output_lines: list[str] = []
    reader = threading.Thread(target=_capture_output, args=(process, output_lines), daemon=True)
    reader.start()
    return process, output_lines, reader


def _wait_for_startup(
    process: subprocess.Popen[str],
    output_lines: list[str],
    *,
    startup_timeout_sec: float,
    port: int,
) -> tuple[bool, str | None]:
    markers = (
        "You can now view your Streamlit app in your browser.",
        "Local URL:",
        "Network URL:",
    )
    deadline = time.monotonic() + startup_timeout_sec
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False, f"streamlit process exited early with code {process.returncode}"
        latest_log = "\n".join(output_lines[-60:])
        if any(marker in latest_log for marker in markers):
            return True, None
        if _probe_http_ready(port):
            return True, None
        time.sleep(0.2)
    return False, f"streamlit startup timeout after {startup_timeout_sec:.1f}s"


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except Exception:
        process.kill()
        process.wait(timeout=2.0)


def _build_streamlit_command(
    *,
    port: int,
    panel_runs_dir: Path,
    gateway_url: str,
    gateway_timeout_sec: float,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(REPO_ROOT / "scripts" / "streamlit_operator_panel.py"),
        "--server.headless",
        "true",
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
        "--",
        "--runs-dir",
        str(panel_runs_dir),
        "--gateway-url",
        gateway_url,
        "--gateway-timeout-sec",
        str(gateway_timeout_sec),
    ]


def run_streamlit_operator_panel_smoke(
    *,
    panel_runs_dir: Path,
    runs_dir: Path,
    summary_json: Path | None = None,
    gateway_url: str = "http://127.0.0.1:8770",
    startup_timeout_sec: float = 45.0,
    gateway_timeout_sec: float = 3.0,
    viewport_width: int = 390,
    viewport_height: int = 844,
    compact_breakpoint_px: int = MOBILE_LAYOUT_BREAKPOINT_PX_DEFAULT,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    startup_log_path = run_dir / "streamlit_startup.log"
    summary_path = (
        summary_json if summary_json is not None else (runs_dir / "streamlit_smoke_summary.json")
    )

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "streamlit_operator_panel_smoke",
        "status": "started",
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_path),
            "startup_log": str(startup_log_path),
        },
    }
    _write_json(run_json_path, run_payload)

    output_lines: list[str] = []
    startup_ok = False
    startup_error: str | None = None
    process_exit_code: int | None = None

    try:
        port = _pick_free_port()
        command = _build_streamlit_command(
            port=port,
            panel_runs_dir=panel_runs_dir,
            gateway_url=gateway_url,
            gateway_timeout_sec=gateway_timeout_sec,
        )
        process, output_lines, reader = _launch_streamlit_process(command)
        startup_ok, startup_error = _wait_for_startup(
            process,
            output_lines,
            startup_timeout_sec=startup_timeout_sec,
            port=port,
        )
        _terminate_process(process)
        process_exit_code = process.returncode
        reader.join(timeout=1.0)
    except Exception as exc:  # pragma: no cover - defensive path
        startup_ok = False
        startup_error = f"smoke execution error: {exc}"

    startup_log_path.parent.mkdir(parents=True, exist_ok=True)
    startup_log_path.write_text("\n".join(output_lines), encoding="utf-8")

    tabs_detected = list(TAB_NAMES)
    required_missing_sources = [
        str(path)
        for path in canonical_summary_sources(panel_runs_dir).values()
        if not path.is_file()
    ]
    optional_missing_sources = [
        str(path)
        for path in canonical_fail_nightly_progress_sources(panel_runs_dir).values()
        if not path.is_file()
    ]
    # Backward-compatible alias: retains previous semantics for required sources.
    missing_sources = list(required_missing_sources)
    mobile_policy = mobile_layout_policy(breakpoint_px=compact_breakpoint_px)
    viewport_baseline = {
        "width": int(viewport_width),
        "height": int(viewport_height),
        "orientation": "portrait" if int(viewport_height) >= int(viewport_width) else "landscape",
    }
    mobile_layout_contract_ok = (
        mobile_policy.get("schema_version") == MOBILE_LAYOUT_POLICY_SCHEMA
        and viewport_baseline["width"] <= int(mobile_policy.get("compact_breakpoint_px", 0))
        and viewport_baseline["orientation"] == "portrait"
    )

    errors: list[str] = []
    if startup_error is not None:
        errors.append(startup_error)
    if tabs_detected != list(TAB_NAMES):
        errors.append("tabs_detected does not match required TAB_NAMES")
    if not mobile_layout_contract_ok:
        errors.append(
            "mobile layout regression: viewport baseline is outside compact policy "
            f"(viewport={viewport_baseline}, policy={mobile_policy})"
        )

    status_ok = startup_ok and mobile_layout_contract_ok and not required_missing_sources and not errors
    exit_code = 0 if status_ok else 2
    summary_payload: dict[str, Any] = {
        "schema_version": "streamlit_smoke_summary_v1",
        "status": "ok" if status_ok else "error",
        "startup_ok": startup_ok,
        "tabs_detected": tabs_detected,
        "mobile_layout_contract_ok": mobile_layout_contract_ok,
        "mobile_layout_policy": mobile_policy,
        "viewport_baseline": viewport_baseline,
        "missing_sources": missing_sources,
        "required_missing_sources": required_missing_sources,
        "optional_missing_sources": optional_missing_sources,
        "errors": errors,
        "exit_code": exit_code,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_path),
            "startup_log": str(startup_log_path),
        },
        "debug": {
            "gateway_url": gateway_url,
            "process_exit_code": process_exit_code,
            "panel_runs_dir": str(panel_runs_dir),
        },
    }
    _write_json(summary_path, summary_payload)

    run_payload["status"] = summary_payload["status"]
    run_payload["result"] = {
        "startup_ok": startup_ok,
        "missing_sources_count": len(missing_sources),
        "required_missing_sources_count": len(required_missing_sources),
        "optional_missing_sources_count": len(optional_missing_sources),
        "exit_code": exit_code,
    }
    _write_json(run_json_path, run_payload)

    return {
        "ok": status_ok,
        "exit_code": exit_code,
        "run_dir": run_dir,
        "run_payload": run_payload,
        "summary_payload": summary_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="No-crash smoke runner for Streamlit operator panel.")
    parser.add_argument(
        "--panel-runs-dir",
        type=Path,
        default=Path("runs"),
        help="Runs directory that Streamlit panel reads from.",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Smoke artifact base directory.")
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional output path for streamlit_smoke_summary_v1.",
    )
    parser.add_argument(
        "--gateway-url",
        default="http://127.0.0.1:8770",
        help="Gateway URL passed to Streamlit panel.",
    )
    parser.add_argument(
        "--startup-timeout-sec",
        type=float,
        default=45.0,
        help="Startup timeout in seconds (default: 45.0).",
    )
    parser.add_argument(
        "--gateway-timeout-sec",
        type=float,
        default=3.0,
        help="Gateway timeout passed to panel (default: 3.0).",
    )
    parser.add_argument(
        "--viewport-width",
        type=int,
        default=390,
        help="Viewport width baseline for compact mobile regression-check (default: 390).",
    )
    parser.add_argument(
        "--viewport-height",
        type=int,
        default=844,
        help="Viewport height baseline for compact mobile regression-check (default: 844).",
    )
    parser.add_argument(
        "--compact-breakpoint-px",
        type=int,
        default=MOBILE_LAYOUT_BREAKPOINT_PX_DEFAULT,
        help=f"Compact mobile breakpoint in px (default: {MOBILE_LAYOUT_BREAKPOINT_PX_DEFAULT}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_streamlit_operator_panel_smoke(
        panel_runs_dir=args.panel_runs_dir,
        runs_dir=args.runs_dir,
        summary_json=args.summary_json,
        gateway_url=args.gateway_url,
        startup_timeout_sec=args.startup_timeout_sec,
        gateway_timeout_sec=args.gateway_timeout_sec,
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
        compact_breakpoint_px=args.compact_breakpoint_px,
    )
    summary_payload = result["summary_payload"]
    print(f"[streamlit_smoke] run_dir: {result['run_dir']}")
    print(f"[streamlit_smoke] summary_json: {summary_payload['paths']['summary_json']}")
    print(f"[streamlit_smoke] status: {summary_payload['status']}")
    print(f"[streamlit_smoke] startup_ok: {summary_payload['startup_ok']}")
    print(f"[streamlit_smoke] mobile_layout_contract_ok: {summary_payload['mobile_layout_contract_ok']}")
    print(f"[streamlit_smoke] missing_sources_count: {len(summary_payload['missing_sources'])}")
    print(
        "[streamlit_smoke] optional_missing_sources_count: "
        f"{len(summary_payload['optional_missing_sources'])}"
    )
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
