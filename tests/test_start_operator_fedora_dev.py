from __future__ import annotations

from scripts.start_operator_fedora_dev import (
    DEFAULT_CAPTURE_REGION,
    FEDORA_LOCAL_DEV_PROFILE_ID,
    FEDORA_START_COMMAND_SCHEMA,
    build_start_command,
    build_start_command_payload,
    parse_args,
)


def test_build_start_command_uses_fedora_profile_and_manual_region() -> None:
    command = build_start_command(
        python_executable="python",
        runs_dir="runs/fedora",
        capture_region="1,2,3,4",
    )

    assert command[:6] == [
        "python",
        "scripts/start_operator_product.py",
        "--runs-dir",
        "runs/fedora",
        "--host-profile",
        FEDORA_LOCAL_DEV_PROFILE_ID,
    ]
    assert "--start-voice-runtime" in command
    assert "--start-tts-runtime" in command
    assert "--start-pilot-runtime" in command
    assert command[command.index("--capture-region") + 1] == "1,2,3,4"


def test_build_start_command_can_omit_managed_runtimes() -> None:
    command = build_start_command(
        python_executable="python",
        start_voice_runtime=False,
        start_tts_runtime=False,
        start_pilot_runtime=False,
    )

    assert "--start-voice-runtime" not in command
    assert "--start-tts-runtime" not in command
    assert "--start-pilot-runtime" not in command
    assert "--capture-region" not in command


def test_build_start_payload_is_machine_readable() -> None:
    payload = build_start_command_payload(
        python_executable="python",
        runs_dir="runs/fedora",
        capture_region=DEFAULT_CAPTURE_REGION,
        extra_args=["--pilot-vlm-provider", "stub"],
    )

    assert payload["schema_version"] == FEDORA_START_COMMAND_SCHEMA
    assert payload["host_profile"] == FEDORA_LOCAL_DEV_PROFILE_ID
    assert payload["readiness_scope"] == "dev_companion"
    assert payload["capture_mode"] == "manual_region"
    assert payload["command"][-2:] == ["--pilot-vlm-provider", "stub"]
    assert "fedora_local_dev" in str(payload["shell_command"])


def test_parse_args_keeps_passthrough_after_separator() -> None:
    args, passthrough = parse_args(
        [
            "--runs-dir",
            "runs/fedora",
            "--capture-region",
            "10,20,30,40",
            "--print-only",
            "--",
            "--pilot-text-provider",
            "stub",
        ]
    )

    assert args.runs_dir == "runs/fedora"
    assert args.capture_region == "10,20,30,40"
    assert args.print_only is True
    assert passthrough == ["--pilot-text-provider", "stub"]
