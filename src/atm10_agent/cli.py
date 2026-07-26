"""Command-line interface for the autonomous companion package."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from atm10_agent import __version__
from atm10_agent.app import CompanionApp
from atm10_agent.contracts import TurnRequest
from atm10_agent.evals import run_suite
from atm10_agent.memory import EmbeddedMemoryStore, consolidate_memory
from atm10_agent.windows_acceptance import (
    run_windows_live_acceptance,
    verify_windows_live_acceptance,
)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timestamp must be ISO-8601") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive finite number")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atm10", description="Autonomous ATM10 companion")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run one deterministic companion turn")
    run_parser.add_argument("--prompt", default="Describe actionable ATM10 context.")
    run_parser.add_argument("--query", default="steel tools")
    run_parser.add_argument("--image", type=Path)
    run_parser.add_argument("--world-docs", type=Path)
    run_parser.add_argument("--topk", type=int, default=3)
    run_parser.add_argument(
        "--action-intent",
        choices=("open_quest_book", "check_inventory_tool", "open_world_map"),
    )
    run_parser.add_argument("--voice", action="store_true")
    run_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    run_parser.add_argument("--state-dir", type=Path, default=Path(".atm10-state"))
    run_parser.add_argument("--memory-dir", type=Path, default=Path(".atm10-memory"))

    replay_parser = subparsers.add_parser("replay", help="replay a saved turn without providers")
    replay_parser.add_argument("turn_json", type=Path)
    replay_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    replay_parser.add_argument("--state-dir", type=Path, default=Path(".atm10-state"))
    replay_parser.add_argument("--memory-dir", type=Path, default=Path(".atm10-memory"))

    eval_parser = subparsers.add_parser(
        "eval",
        help="run a dependency-light executable product eval",
    )
    eval_parser.add_argument(
        "--suite",
        default="companion-core",
        choices=("companion-core",),
    )
    eval_parser.add_argument("--runs-dir", type=Path, default=Path("runs/eval"))
    eval_parser.add_argument("--state-dir", type=Path, default=Path(".atm10-state/eval"))
    eval_parser.add_argument("--reports-dir", type=Path, default=Path("eval-results"))
    eval_parser.add_argument("--memory-dir", type=Path, default=Path(".atm10-memory/eval"))
    eval_parser.add_argument("--now", type=_timestamp)

    memory_parser = subparsers.add_parser(
        "consolidate-memory",
        help="derive proposed semantic/procedural memory candidates",
    )
    memory_parser.add_argument("--memory-dir", type=Path, default=Path(".atm10-memory"))
    memory_parser.add_argument("--now", type=_timestamp)

    subparsers.add_parser("doctor", help="show the dependency-light core posture")
    windows_parser = subparsers.add_parser(
        "windows-acceptance",
        help="collect one live Windows 11 ATM10 acceptance receipt",
    )
    windows_parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("runs/windows-live-acceptance"),
    )
    windows_parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path(".atm10-state/windows-live-acceptance"),
    )
    windows_parser.add_argument("--repo-root", type=Path, default=Path("."))
    windows_parser.add_argument("--source-revision")
    windows_parser.add_argument("--settle-seconds", type=float, default=5.0)
    verify_windows_parser = subparsers.add_parser(
        "verify-windows-acceptance",
        help="verify a transferred Windows acceptance receipt and artifact bundle",
    )
    verify_windows_parser.add_argument("receipt", type=Path)
    verify_windows_parser.add_argument("--source-revision", required=True)
    verify_windows_parser.add_argument(
        "--max-age-hours",
        type=_positive_float,
        default=24.0,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "doctor":
        print(
            json.dumps(
                {
                    "schema_version": "atm10_doctor_v1",
                    "status": "ok",
                    "package_version": __version__,
                    "core_dependencies": [],
                    "default_provider": "deterministic_stub_v1",
                    "action_default": "dry_run_only",
                },
                indent=2,
            )
        )
        return 0

    if args.command == "windows-acceptance":
        payload, receipt_path = run_windows_live_acceptance(
            evidence_root=args.evidence_dir,
            state_dir=args.state_dir,
            repo_root=args.repo_root,
            source_revision=args.source_revision,
            settle_seconds=args.settle_seconds,
        )
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "receipt": str(receipt_path),
                    "degraded": payload["degraded"],
                    "errors": payload["errors"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0 if payload["status"] == "pass" else 2

    if args.command == "verify-windows-acceptance":
        result = verify_windows_live_acceptance(
            receipt_path=args.receipt,
            expected_revision=args.source_revision,
            max_age_hours=args.max_age_hours,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["status"] == "pass" else 2

    if args.command == "eval":
        result = run_suite(
            args.suite,
            runs_dir=args.runs_dir,
            state_dir=args.state_dir,
            reports_dir=args.reports_dir,
            memory_dir=args.memory_dir,
            now=args.now,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["status"] == "pass" else 2

    if args.command == "consolidate-memory":
        observed_at = args.now or datetime.now(timezone.utc)
        result = consolidate_memory(
            store=EmbeddedMemoryStore(args.memory_dir),
            observed_at_utc=observed_at.astimezone(timezone.utc).isoformat(),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["status"] == "ok" else 2

    app = CompanionApp(
        runs_dir=args.runs_dir,
        state_dir=args.state_dir,
        memory_dir=args.memory_dir,
    )
    if args.command == "replay":
        result = app.replay(args.turn_json)
    else:
        result = app.run(
            TurnRequest(
                prompt=args.prompt,
                query=args.query,
                image_path=args.image,
                world_docs=args.world_docs,
                topk=args.topk,
                action_intent=args.action_intent,
                voice=args.voice,
            )
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0
