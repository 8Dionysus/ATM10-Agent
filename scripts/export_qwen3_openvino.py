from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PRESETS: dict[str, dict[str, Any]] = {
    "qwen3-vl-4b": {
        "model_id": "Qwen/Qwen3-VL-4B-Instruct",
        "task": "image-text-to-text",
        "weight_format": "int4",
        "output_subdir": "qwen3-vl-4b-instruct-ov",
        "trust_remote_code": True,
    },
    "qwen3-asr-0.6b": {
        "model_id": "Qwen/Qwen3-ASR-0.6B",
        "task": "automatic-speech-recognition",
        "weight_format": "int8",
        "output_subdir": "qwen3-asr-0.6b-ov",
        "trust_remote_code": True,
    },
}


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-qwen3-export")
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


def _build_export_command(
    *,
    preset_name: str,
    output_root: Path,
    optimum_cli: str,
    weight_format_override: str | None,
) -> tuple[list[str], Path]:
    preset = PRESETS[preset_name]
    output_dir = output_root / preset["output_subdir"]
    weight_format = weight_format_override or preset["weight_format"]

    cmd: list[str] = [
        optimum_cli,
        "export",
        "openvino",
        "--model",
        preset["model_id"],
        "--task",
        preset["task"],
        "--weight-format",
        weight_format,
    ]
    if preset.get("trust_remote_code", False):
        cmd.append("--trust-remote-code")
    cmd.append(str(output_dir))
    return cmd, output_dir


def _resolve_executable(name_or_path: str) -> str:
    explicit = Path(name_or_path)
    if explicit.parent != Path(".") or explicit.suffix:
        return str(explicit)

    found = shutil.which(name_or_path)
    if found:
        return found

    exe_name = name_or_path if name_or_path.lower().endswith(".exe") else f"{name_or_path}.exe"
    candidate = Path(sys.executable).resolve().parent / exe_name
    if candidate.exists():
        return str(candidate)

    # Keep unresolved command name for environments where CLI is optional.
    return name_or_path


def _run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def run_export_qwen3_openvino(
    *,
    preset_name: str,
    execute: bool = False,
    runs_dir: Path = Path("runs"),
    output_root: Path = Path("models"),
    optimum_cli: str = "optimum-cli",
    weight_format_override: str | None = None,
    now: datetime | None = None,
    runner: Any | None = None,
) -> dict[str, Any]:
    if preset_name not in PRESETS:
        raise ValueError(f"Unsupported preset: {preset_name}")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    plan_json_path = run_dir / "export_plan.json"
    stdout_path = run_dir / "export_stdout.log"
    stderr_path = run_dir / "export_stderr.log"

    command, output_dir = _build_export_command(
        preset_name=preset_name,
        output_root=output_root,
        optimum_cli=_resolve_executable(optimum_cli),
        weight_format_override=weight_format_override,
    )

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "qwen3_openvino_export",
        "status": "started",
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "export_plan_json": str(plan_json_path),
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        },
        "preset": preset_name,
        "execute": execute,
    }
    _write_json(run_json_path, run_payload)

    plan_payload: dict[str, Any] = {
        "preset": preset_name,
        "model_id": PRESETS[preset_name]["model_id"],
        "task": PRESETS[preset_name]["task"],
        "weight_format": weight_format_override or PRESETS[preset_name]["weight_format"],
        "output_dir": str(output_dir),
        "command": command,
    }
    _write_json(plan_json_path, plan_payload)

    if not execute:
        run_payload["status"] = "dry_run"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "plan_payload": plan_payload,
            "ok": True,
        }

    command_runner = _run_command if runner is None else runner
    try:
        result = command_runner(command, Path.cwd())
        stdout_text = result.stdout or ""
        stderr_text = result.stderr or ""
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")

        run_payload["returncode"] = int(result.returncode)
        if result.returncode == 0:
            run_payload["status"] = "ok"
            ok = True
        else:
            run_payload["status"] = "error"
            run_payload["error"] = "optimum-cli export failed"
            ok = False
    except Exception as exc:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(exc), encoding="utf-8")
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        run_payload["returncode"] = None
        ok = False

    _write_json(run_json_path, run_payload)
    return {
        "run_dir": run_dir,
        "run_payload": run_payload,
        "plan_payload": plan_payload,
        "ok": ok,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export fixed Qwen3 presets to OpenVINO IR with artifacts in runs/<timestamp>-qwen3-export."
    )
    parser.add_argument(
        "--preset",
        choices=tuple(PRESETS.keys()),
        required=True,
        help="Conversion preset.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run optimum-cli export. Without this flag, script runs dry-run only.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base directory for run artifacts (default: runs).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("models"),
        help="Output root for converted OpenVINO models (default: models).",
    )
    parser.add_argument(
        "--optimum-cli",
        default="optimum-cli",
        help="optimum-cli executable name/path (default: optimum-cli).",
    )
    parser.add_argument(
        "--weight-format",
        default=None,
        help="Optional override for preset weight format.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_export_qwen3_openvino(
        preset_name=args.preset,
        execute=args.execute,
        runs_dir=args.runs_dir,
        output_root=args.output_root,
        optimum_cli=args.optimum_cli,
        weight_format_override=args.weight_format,
    )
    run_dir = result["run_dir"]
    print(f"[qwen3_export] run_dir: {run_dir}")
    print(f"[qwen3_export] run_json: {run_dir / 'run.json'}")
    print(f"[qwen3_export] plan_json: {run_dir / 'export_plan.json'}")
    status = result["run_payload"]["status"]
    print(f"[qwen3_export] status: {status}")
    if status == "dry_run":
        print("[qwen3_export] dry-run only. Re-run with --execute to start conversion.")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
