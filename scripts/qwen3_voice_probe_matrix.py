from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

GATE_STATUS_READY = "ready"
GATE_STATUS_BLOCKED_UPSTREAM = "blocked_upstream"
GATE_STATUS_IMPORT_ERROR = "import_error"
GATE_STATUS_RUNTIME_ERROR = "runtime_error"
GATE_STATUS_SETUP_FAILED = "setup_failed"
GATE_STATUS_PROBE_FAILED = "probe_failed"
GATE_STATUS_UNKNOWN = "unknown"


PRESETS: dict[str, dict[str, Any]] = {
    "current": {
        "python": sys.executable,
        "setup_commands": [],
        "description": "Current active environment.",
    },
    "venv-exp-transformers-main": {
        "python": r".venv-exp\Scripts\python.exe",
        "setup_commands": [
            [r".venv-exp\Scripts\python.exe", "-m", "pip", "install", "--upgrade", "pip"],
            [
                r".venv-exp\Scripts\python.exe",
                "-m",
                "pip",
                "install",
                "--upgrade",
                "git+https://github.com/huggingface/transformers.git",
            ],
        ],
        "description": "Experimental venv with transformers from main only.",
    },
    "venv-exp-transformers-4.57.6": {
        "python": r".venv-exp\Scripts\python.exe",
        "setup_commands": [
            [r".venv-exp\Scripts\python.exe", "-m", "pip", "install", "--upgrade", "pip"],
            [
                r".venv-exp\Scripts\python.exe",
                "-m",
                "pip",
                "install",
                "--upgrade",
                "transformers==4.57.6",
            ],
        ],
        "description": "Experimental venv with pinned transformers fallback.",
    },
}


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-qwen3-voice-matrix")
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


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def _build_probe_inline_command() -> str:
    return (
        "import json;"
        "from scripts.probe_qwen3_voice_support import probe_default_voice_stack;"
        "print(json.dumps(probe_default_voice_stack(), ensure_ascii=False))"
    )


def _derive_gate_from_probe_statuses(probe_statuses: Mapping[str, str] | None) -> tuple[bool, str, list[str]]:
    if not probe_statuses:
        return False, GATE_STATUS_UNKNOWN, []

    blocked_architectures = [name for name, status in probe_statuses.items() if status != "supported"]
    if not blocked_architectures:
        return True, GATE_STATUS_READY, []

    statuses = [probe_statuses[name] for name in blocked_architectures]
    if any(status == GATE_STATUS_IMPORT_ERROR for status in statuses):
        return False, GATE_STATUS_IMPORT_ERROR, blocked_architectures
    if any(status == GATE_STATUS_RUNTIME_ERROR for status in statuses):
        return False, GATE_STATUS_RUNTIME_ERROR, blocked_architectures
    if any(status == GATE_STATUS_BLOCKED_UPSTREAM for status in statuses):
        return False, GATE_STATUS_BLOCKED_UPSTREAM, blocked_architectures
    return False, GATE_STATUS_UNKNOWN, blocked_architectures


def run_qwen3_voice_probe_matrix(
    *,
    execute: bool = False,
    with_setup: bool = False,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    plan_json_path = run_dir / "matrix_plan.json"
    results_json_path = run_dir / "matrix_results.json"

    plan_payload: dict[str, Any] = {
        "execute": execute,
        "with_setup": with_setup,
        "presets": PRESETS,
        "probe_command": ["<python>", "-c", _build_probe_inline_command()],
    }
    _write_json(plan_json_path, plan_payload)

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "qwen3_voice_probe_matrix",
        "status": "dry_run" if not execute else "started",
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "plan_json": str(plan_json_path),
            "results_json": str(results_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    if not execute:
        _write_json(results_json_path, {"combos": [], "note": "dry-run only"})
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "plan_payload": plan_payload,
            "results_payload": {"combos": [], "note": "dry-run only"},
            "ok": True,
        }

    combos: list[dict[str, Any]] = []
    inline_probe = _build_probe_inline_command()
    for name, preset in PRESETS.items():
        combo_dir = run_dir / "combos" / name
        combo_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = combo_dir / "stdout.log"
        stderr_path = combo_dir / "stderr.log"

        combo_payload: dict[str, Any] = {
            "name": name,
            "python": preset["python"],
            "description": preset["description"],
            "setup_requested": with_setup,
            "setup_commands": preset["setup_commands"],
            "setup_completed": False,
            "setup_ok": True,
            "probe_ok": False,
            "probe_statuses": None,
            "unlock_ready": False,
            "gate_status": GATE_STATUS_UNKNOWN,
            "blocked_architectures": [],
            "returncode": None,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "error": None,
        }

        all_stdout_parts: list[str] = []
        all_stderr_parts: list[str] = []

        try:
            if with_setup:
                for command in preset["setup_commands"]:
                    setup_result = _run_command(command)
                    all_stdout_parts.append(setup_result.stdout or "")
                    all_stderr_parts.append(setup_result.stderr or "")
                    if setup_result.returncode != 0:
                        combo_payload["setup_ok"] = False
                        combo_payload["returncode"] = int(setup_result.returncode)
                        combo_payload["error"] = "setup command failed"
                        combo_payload["gate_status"] = GATE_STATUS_SETUP_FAILED
                        break
                combo_payload["setup_completed"] = True
            if combo_payload["setup_ok"]:
                probe_command = [preset["python"], "-c", inline_probe]
                probe_result = _run_command(probe_command)
                combo_payload["returncode"] = int(probe_result.returncode)
                all_stdout_parts.append(probe_result.stdout or "")
                all_stderr_parts.append(probe_result.stderr or "")
                if probe_result.returncode == 0:
                    parsed = json.loads((probe_result.stdout or "").strip() or "{}")
                    combo_payload["probe_ok"] = True
                    combo_payload["probe_statuses"] = {
                        key: value.get("status") for key, value in parsed.items() if isinstance(value, dict)
                    }
                    unlock_ready, gate_status, blocked_architectures = _derive_gate_from_probe_statuses(
                        combo_payload["probe_statuses"]
                    )
                    combo_payload["unlock_ready"] = unlock_ready
                    combo_payload["gate_status"] = gate_status
                    combo_payload["blocked_architectures"] = blocked_architectures
                else:
                    combo_payload["error"] = "probe command failed"
                    combo_payload["gate_status"] = GATE_STATUS_PROBE_FAILED
        except Exception as exc:
            combo_payload["error"] = str(exc)
            combo_payload["traceback"] = traceback.format_exc()

        stdout_path.write_text("\n".join(all_stdout_parts), encoding="utf-8")
        stderr_path.write_text("\n".join(all_stderr_parts), encoding="utf-8")
        combos.append(combo_payload)

    ok = all(item["probe_ok"] for item in combos)
    run_payload["status"] = "ok" if ok else "error"
    run_payload["ok"] = ok
    results_payload = {
        "combos": combos,
        "summary": {
            "combos_total": len(combos),
            "probe_ok": sum(1 for item in combos if item["probe_ok"]),
            "unlock_ready": sum(1 for item in combos if item["unlock_ready"]),
        },
    }
    _write_json(results_json_path, results_payload)
    _write_json(run_json_path, run_payload)

    return {
        "run_dir": run_dir,
        "run_payload": run_payload,
        "plan_payload": plan_payload,
        "results_payload": results_payload,
        "ok": ok,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run dry-run or execute matrix probes for qwen3_asr/qwen3_tts support "
            "across current and .venv-exp environments."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run matrix commands. Without this flag, script writes only plan artifacts.",
    )
    parser.add_argument(
        "--with-setup",
        action="store_true",
        help="When used with --execute, run pip setup commands for experimental presets.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base directory for run artifacts (default: runs).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_qwen3_voice_probe_matrix(
        execute=args.execute,
        with_setup=args.with_setup,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[qwen3_voice_matrix] run_dir: {run_dir}")
    print(f"[qwen3_voice_matrix] run_json: {run_dir / 'run.json'}")
    print(f"[qwen3_voice_matrix] plan_json: {run_dir / 'matrix_plan.json'}")
    print(f"[qwen3_voice_matrix] results_json: {run_dir / 'matrix_results.json'}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
