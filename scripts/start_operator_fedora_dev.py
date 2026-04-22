from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Sequence

FEDORA_LOCAL_DEV_PROFILE_ID = "fedora_local_dev"
FEDORA_START_COMMAND_SCHEMA = "fedora_local_dev_start_command_v1"
DEFAULT_CAPTURE_REGION = "0,0,1920,1080"


def shell_join(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def build_start_command(
    *,
    python_executable: str | Path | None = None,
    runs_dir: str | Path = "runs",
    capture_region: str | None = DEFAULT_CAPTURE_REGION,
    start_voice_runtime: bool = True,
    start_tts_runtime: bool = True,
    start_pilot_runtime: bool = True,
    extra_args: Sequence[str] = (),
) -> list[str]:
    """Build the additive Fedora dev-companion launcher command.

    This helper intentionally delegates to the canonical product launcher instead
    of creating a second startup engine. It only fixes the host profile and
    Fedora-friendly manual capture defaults.
    """

    command = [
        str(python_executable or sys.executable),
        "scripts/start_operator_product.py",
        "--runs-dir",
        str(runs_dir),
        "--host-profile",
        FEDORA_LOCAL_DEV_PROFILE_ID,
    ]

    if start_voice_runtime:
        command.append("--start-voice-runtime")
    if start_tts_runtime:
        command.append("--start-tts-runtime")
    if start_pilot_runtime:
        command.append("--start-pilot-runtime")
        normalized_region = str(capture_region or "").strip()
        if normalized_region:
            command.extend(["--capture-region", normalized_region])

    command.extend(str(arg) for arg in extra_args)
    return command


def build_start_command_payload(
    *,
    python_executable: str | Path | None = None,
    runs_dir: str | Path = "runs",
    capture_region: str | None = DEFAULT_CAPTURE_REGION,
    start_voice_runtime: bool = True,
    start_tts_runtime: bool = True,
    start_pilot_runtime: bool = True,
    extra_args: Sequence[str] = (),
) -> dict[str, object]:
    command = build_start_command(
        python_executable=python_executable,
        runs_dir=runs_dir,
        capture_region=capture_region,
        start_voice_runtime=start_voice_runtime,
        start_tts_runtime=start_tts_runtime,
        start_pilot_runtime=start_pilot_runtime,
        extra_args=extra_args,
    )
    return {
        "schema_version": FEDORA_START_COMMAND_SCHEMA,
        "host_profile": FEDORA_LOCAL_DEV_PROFILE_ID,
        "readiness_scope": "dev_companion",
        "capture_mode": "manual_region",
        "command": command,
        "shell_command": shell_join(command),
        "notes": [
            "Additive Fedora development companion path; not a Windows ATM10 product-edge replacement.",
            "Delegates to scripts/start_operator_product.py to avoid a second startup engine.",
        ],
    }


def parse_args(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Fedora local development companion launcher wrapper for ATM10-Agent.",
    )
    parser.add_argument(
        "--runs-dir",
        default=os.environ.get("ATM10_RUNS_DIR", "runs/fedora-local-dev"),
        help="Runs directory forwarded to start_operator_product.py.",
    )
    parser.add_argument(
        "--capture-region",
        default=os.environ.get("ATM10_CAPTURE_REGION", DEFAULT_CAPTURE_REGION),
        help="Manual capture region formatted as x,y,w,h. Use an empty value to omit.",
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable used to invoke scripts/start_operator_product.py.",
    )
    parser.add_argument(
        "--no-voice-runtime",
        action="store_true",
        help="Do not start the managed voice runtime.",
    )
    parser.add_argument(
        "--no-tts-runtime",
        action="store_true",
        help="Do not start the managed TTS runtime.",
    )
    parser.add_argument(
        "--no-pilot-runtime",
        action="store_true",
        help="Do not start the managed pilot runtime.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the resolved command JSON instead of launching it.",
    )
    parser.add_argument(
        "passthrough",
        nargs=argparse.REMAINDER,
        help="Arguments after -- are forwarded to start_operator_product.py.",
    )
    args = parser.parse_args(argv)
    passthrough = list(args.passthrough or [])
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    return args, passthrough


def main(argv: Sequence[str] | None = None) -> int:
    args, passthrough = parse_args(argv)
    payload = build_start_command_payload(
        python_executable=args.python_executable,
        runs_dir=args.runs_dir,
        capture_region=args.capture_region,
        start_voice_runtime=not bool(args.no_voice_runtime),
        start_tts_runtime=not bool(args.no_tts_runtime),
        start_pilot_runtime=not bool(args.no_pilot_runtime),
        extra_args=passthrough,
    )
    if args.print_only:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    command = payload["command"]
    if not isinstance(command, list):
        raise TypeError("resolved command payload is not a list")
    return int(subprocess.call([str(part) for part in command]))


if __name__ == "__main__":
    raise SystemExit(main())
