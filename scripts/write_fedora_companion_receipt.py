from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.discover_instance import build_report
from scripts.start_operator_fedora_dev import build_start_command_payload
from src.agent_core.atm10_session_probe import probe_atm10_session
from src.agent_core.fedora_companion_milestone import (
    FEDORA_COMPANION_MILESTONE_RECEIPT_SCHEMA,
    evaluate_fedora_companion_milestone,
    parse_capture_region,
)
from src.agent_core.host_profiles import FEDORA_LOCAL_DEV_PROFILE_ID
from src.agent_core.readiness_scopes import evaluate_host_profile_session_readiness


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S")
    candidate = runs_dir / base_name
    if not candidate.exists():
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate
    suffix = 1
    while True:
        fallback = runs_dir / f"{base_name}_{suffix:02d}"
        if not fallback.exists():
            fallback.mkdir(parents=True, exist_ok=False)
            return fallback
        suffix += 1


def build_receipt_payload(
    *,
    env: Mapping[str, str] | None = None,
    runs_dir: Path = Path("runs/fedora-companion-receipt"),
    capture_region: str = "0,0,1920,1080",
    now: datetime | None = None,
    allow_missing_atm10_dir: bool = False,
    require_atm10_dir_exists: bool = False,
    startup_extra_args: Sequence[str] = (),
) -> dict[str, object]:
    """Build a Fedora companion milestone receipt without launching services."""

    if now is None:
        now = datetime.now(timezone.utc)
    env_map = dict(os.environ if env is None else env)
    bbox = parse_capture_region(capture_region)

    startup_payload = build_start_command_payload(
        runs_dir=runs_dir,
        capture_region=capture_region,
        start_voice_runtime=True,
        start_tts_runtime=True,
        start_pilot_runtime=True,
        extra_args=startup_extra_args,
    )
    session_probe = probe_atm10_session(
        capture_target_kind="region",
        capture_bbox=bbox,
        now=now,
        platform_name="linux",
    )
    readiness_evaluation = evaluate_host_profile_session_readiness(
        host_profile=FEDORA_LOCAL_DEV_PROFILE_ID,
        session_probe=session_probe,
    )
    instance_report = build_report(
        env_map,
        now=now,
        platform_name="linux",
    )
    receipt = evaluate_fedora_companion_milestone(
        startup_payload=startup_payload,
        session_probe=session_probe,
        readiness_evaluation=readiness_evaluation,
        instance_discovery_report=instance_report,
        require_instance_path=not allow_missing_atm10_dir,
        require_instance_exists=require_atm10_dir_exists,
    )

    return {
        "schema_version": FEDORA_COMPANION_MILESTONE_RECEIPT_SCHEMA,
        "generated_at_utc": now.astimezone(timezone.utc).isoformat(),
        "startup_payload": startup_payload,
        "session_probe": session_probe,
        "readiness_evaluation": readiness_evaluation,
        "instance_discovery_report": instance_report,
        "milestone_evaluation": receipt,
    }


def write_receipt(
    *,
    runs_dir: Path,
    capture_region: str,
    allow_missing_atm10_dir: bool,
    require_atm10_dir_exists: bool,
    startup_extra_args: Sequence[str] = (),
    now: datetime | None = None,
) -> tuple[dict[str, object], Path]:
    if now is None:
        now = datetime.now(timezone.utc)
    run_dir = _create_run_dir(runs_dir, now)
    payload = build_receipt_payload(
        runs_dir=run_dir,
        capture_region=capture_region,
        now=now,
        allow_missing_atm10_dir=allow_missing_atm10_dir,
        require_atm10_dir_exists=require_atm10_dir_exists,
        startup_extra_args=startup_extra_args,
    )
    receipt_path = run_dir / "fedora_companion_milestone_receipt.json"
    receipt_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload, receipt_path


def parse_args(argv: Sequence[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Write a Fedora local-dev companion milestone receipt without launching managed runtimes.",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs/fedora-companion-receipt"))
    parser.add_argument("--capture-region", default=os.environ.get("ATM10_CAPTURE_REGION", "0,0,1920,1080"))
    parser.add_argument(
        "--allow-missing-atm10-dir",
        action="store_true",
        help="Skip the ATM10 instance-path requirement for CI mechanics smoke.",
    )
    parser.add_argument(
        "--require-atm10-dir-exists",
        action="store_true",
        help="Require the resolved ATM10_DIR path to exist on disk.",
    )
    parser.add_argument("passthrough", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    passthrough = list(args.passthrough or [])
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    return args, passthrough


def main(argv: Sequence[str] | None = None) -> int:
    args, passthrough = parse_args(argv)
    payload, receipt_path = write_receipt(
        runs_dir=args.runs_dir,
        capture_region=args.capture_region,
        allow_missing_atm10_dir=bool(args.allow_missing_atm10_dir),
        require_atm10_dir_exists=bool(args.require_atm10_dir_exists),
        startup_extra_args=passthrough,
    )
    evaluation = payload["milestone_evaluation"]
    if not isinstance(evaluation, dict):
        raise TypeError("milestone_evaluation is not a dict")
    print(f"[fedora_companion_receipt] artifact: {receipt_path}")
    print(f"status: {evaluation.get('status')}")
    if evaluation.get("blocking_reason_codes"):
        print("blocking_reason_codes: " + ", ".join(str(code) for code in evaluation["blocking_reason_codes"]))
    return 0 if evaluation.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
