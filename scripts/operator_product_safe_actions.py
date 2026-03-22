from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

GATEWAY_OPERATOR_SAFE_ACTIONS_SCHEMA = "gateway_operator_safe_actions_v1"
GATEWAY_OPERATOR_SAFE_ACTION_RUN_SCHEMA = "gateway_operator_safe_action_run_v1"

SAFE_ACTIONS: dict[str, dict[str, Any]] = {
    "gateway_local_core": {
        "label": "Gateway local smoke core",
        "script": "scripts/gateway_v1_smoke.py",
        "scenario": "core",
        "runs_subdir": "ui-safe-gateway-core",
        "summary_name": "gateway_smoke_summary.json",
    },
    "gateway_local_hybrid": {
        "label": "Gateway local smoke hybrid",
        "script": "scripts/gateway_v1_smoke.py",
        "scenario": "hybrid",
        "runs_subdir": "ui-safe-gateway-hybrid",
        "summary_name": "gateway_smoke_summary.json",
    },
    "gateway_local_automation": {
        "label": "Gateway local smoke automation",
        "script": "scripts/gateway_v1_smoke.py",
        "scenario": "automation",
        "runs_subdir": "ui-safe-gateway-automation",
        "summary_name": "gateway_smoke_summary.json",
    },
    "gateway_local_combo_a": {
        "label": "Gateway local smoke Combo A",
        "script": "scripts/gateway_v1_smoke.py",
        "scenario": "combo_a",
        "runs_subdir": "ui-safe-gateway-combo-a",
        "summary_name": "gateway_smoke_summary.json",
    },
    "gateway_http_core": {
        "label": "Gateway HTTP smoke core",
        "script": "scripts/gateway_v1_http_smoke.py",
        "scenario": "core",
        "runs_subdir": "ui-safe-gateway-http-core",
        "summary_name": "gateway_http_smoke_summary.json",
    },
    "gateway_http_hybrid": {
        "label": "Gateway HTTP smoke hybrid",
        "script": "scripts/gateway_v1_http_smoke.py",
        "scenario": "hybrid",
        "runs_subdir": "ui-safe-gateway-http-hybrid",
        "summary_name": "gateway_http_smoke_summary.json",
    },
    "gateway_http_automation": {
        "label": "Gateway HTTP smoke automation",
        "script": "scripts/gateway_v1_http_smoke.py",
        "scenario": "automation",
        "runs_subdir": "ui-safe-gateway-http-automation",
        "summary_name": "gateway_http_smoke_summary.json",
    },
    "gateway_http_combo_a": {
        "label": "Gateway HTTP smoke Combo A",
        "script": "scripts/gateway_v1_http_smoke.py",
        "scenario": "combo_a",
        "runs_subdir": "ui-safe-gateway-http-combo-a",
        "summary_name": "gateway_http_smoke_summary.json",
    },
    "cross_service_suite_smoke": {
        "label": "Cross-service suite smoke",
        "script": "scripts/cross_service_benchmark_suite.py",
        "scenario": "suite",
        "runs_subdir": "ui-safe-cross-service-suite",
        "summary_name": "cross_service_benchmark_suite.json",
        "extra_args": ["--smoke-stub-voice-asr"],
    },
    "cross_service_suite_combo_a_smoke": {
        "label": "Cross-service suite Combo A smoke",
        "script": "scripts/cross_service_benchmark_suite.py",
        "scenario": "suite",
        "runs_subdir": "ui-safe-cross-service-suite-combo-a",
        "summary_name": "cross_service_benchmark_suite.json",
        "extra_args": ["--profile", "combo_a"],
    },
    "combo_a_operating_cycle_smoke": {
        "label": "Combo A operating cycle smoke",
        "script": "scripts/run_combo_a_operating_cycle.py",
        "scenario": "policy_surface",
        "runs_subdir": "ui-safe-combo-a-operating-cycle",
        "summary_name": "operating_cycle_summary.json",
    },
    "gateway_sla_operating_cycle_smoke": {
        "label": "Gateway SLA operating cycle smoke",
        "script": "scripts/run_gateway_sla_operating_cycle.py",
        "scenario": "policy_surface",
        "runs_subdir": "ui-safe-gateway-sla-operating-cycle",
        "summary_name": "operating_cycle_summary.json",
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_action_catalog() -> list[dict[str, Any]]:
    return [
        {
            "action_key": action_key,
            "label": config["label"],
            "scenario": config.get("scenario"),
            "summary_name": config["summary_name"],
            "smoke_only": True,
        }
        for action_key, config in SAFE_ACTIONS.items()
    ]


def safe_actions_audit_log_path(runs_dir: Path) -> Path:
    return Path(runs_dir) / "ui-safe-actions" / "safe_actions_audit.jsonl"


def append_safe_action_audit(runs_dir: Path, entry: dict[str, Any]) -> None:
    path = safe_actions_audit_log_path(runs_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp_utc": entry.get("timestamp_utc") or _utc_now(),
        "action_key": entry.get("action_key"),
        "command": entry.get("command"),
        "exit_code": entry.get("exit_code"),
        "status": entry.get("status"),
        "summary_json": entry.get("summary_json"),
        "summary_status": entry.get("summary_status"),
        "error": entry.get("error"),
        "ok": bool(entry.get("ok", False)),
        "action_runs_dir": entry.get("action_runs_dir"),
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_safe_action_audit(runs_dir: Path, limit: int = 10) -> list[dict[str, Any]]:
    path = safe_actions_audit_log_path(runs_dir)
    if limit <= 0:
        return []
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return [
            {
                "timestamp_utc": _utc_now(),
                "action_key": "audit_read_error",
                "command": None,
                "exit_code": None,
                "status": "error",
                "summary_json": str(path),
                "summary_status": None,
                "error": f"failed to read audit log: {exc}",
                "ok": False,
                "action_runs_dir": None,
            }
        ]

    for line_idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            entries.append(
                {
                    "timestamp_utc": _utc_now(),
                    "action_key": "invalid_audit_entry",
                    "command": None,
                    "exit_code": None,
                    "status": "error",
                    "summary_json": str(path),
                    "summary_status": None,
                    "error": f"invalid audit entry at line {line_idx}",
                    "ok": False,
                    "action_runs_dir": None,
                }
            )
            continue
        if not isinstance(payload, dict):
            entries.append(
                {
                    "timestamp_utc": _utc_now(),
                    "action_key": "invalid_audit_entry",
                    "command": None,
                    "exit_code": None,
                    "status": "error",
                    "summary_json": str(path),
                    "summary_status": None,
                    "error": f"invalid audit entry at line {line_idx}",
                    "ok": False,
                    "action_runs_dir": None,
                }
            )
            continue
        entries.append(
            {
                "timestamp_utc": payload.get("timestamp_utc"),
                "action_key": payload.get("action_key"),
                "command": payload.get("command"),
                "exit_code": payload.get("exit_code"),
                "status": payload.get("status"),
                "summary_json": payload.get("summary_json"),
                "summary_status": payload.get("summary_status"),
                "error": payload.get("error"),
                "ok": bool(payload.get("ok", False)),
                "action_runs_dir": payload.get("action_runs_dir"),
            }
        )
    return list(reversed(entries))[:limit]


def resolve_safe_action(action_key: str, runs_dir: Path) -> tuple[list[str], Path, Path]:
    config = SAFE_ACTIONS.get(action_key)
    if config is None:
        raise ValueError(f"unsupported safe action: {action_key!r}")
    action_runs_dir = Path(runs_dir) / config["runs_subdir"]
    summary_path = action_runs_dir / config["summary_name"]
    command = [
        sys.executable,
        config["script"],
        "--runs-dir",
        str(action_runs_dir),
        "--summary-json",
        str(summary_path),
    ]
    scenario = config.get("scenario")
    if isinstance(scenario, str) and scenario.strip() and str(config["script"]).endswith("_smoke.py"):
        command.extend(["--scenario", scenario])
    extra_args = config.get("extra_args")
    if isinstance(extra_args, list):
        command.extend(str(item) for item in extra_args)
    return command, action_runs_dir, summary_path


def run_safe_action(action_key: str, runs_dir: Path, *, timeout_sec: float = 300.0) -> dict[str, Any]:
    command, action_runs_dir, summary_path = resolve_safe_action(action_key, runs_dir)
    command_text = " ".join(command)
    started_at_utc = _utc_now()
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "schema_version": GATEWAY_OPERATOR_SAFE_ACTION_RUN_SCHEMA,
            "timestamp_utc": started_at_utc,
            "action_key": action_key,
            "command": command_text,
            "action_runs_dir": str(action_runs_dir),
            "summary_json": str(summary_path),
            "exit_code": 2,
            "status": "error",
            "ok": False,
            "summary_status": None,
            "error": f"safe action timeout: {exc}",
            "stdout": "",
            "stderr": "",
        }

    summary_payload = None
    load_error = None
    try:
        summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(summary_payload, dict):
            load_error = f"json root must be object: {summary_path}"
            summary_payload = None
    except FileNotFoundError:
        load_error = f"missing file: {summary_path}"
    except Exception as exc:
        load_error = f"failed to parse JSON {summary_path}: {exc}"

    summary_status = None if summary_payload is None else str(summary_payload.get("status"))
    ok = completed.returncode == 0 and summary_status == "ok" and load_error is None
    return {
        "schema_version": GATEWAY_OPERATOR_SAFE_ACTION_RUN_SCHEMA,
        "timestamp_utc": started_at_utc,
        "action_key": action_key,
        "command": command_text,
        "action_runs_dir": str(action_runs_dir),
        "summary_json": str(summary_path),
        "exit_code": int(completed.returncode),
        "status": "ok" if ok else "error",
        "ok": ok,
        "summary_status": summary_status,
        "error": load_error,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def build_safe_actions_overview(runs_dir: Path, *, history_limit: int = 10) -> dict[str, Any]:
    return {
        "schema_version": GATEWAY_OPERATOR_SAFE_ACTIONS_SCHEMA,
        "checked_at_utc": _utc_now(),
        "status": "ok",
        "catalog": safe_action_catalog(),
        "recent_runs": load_safe_action_audit(runs_dir, limit=history_limit),
    }
