"""Command-line interface for the autonomous companion package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from atm10_agent import __version__
from atm10_agent.app import CompanionApp
from atm10_agent.contracts import TurnRequest


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

    replay_parser = subparsers.add_parser("replay", help="replay a saved turn without providers")
    replay_parser.add_argument("turn_json", type=Path)
    replay_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    replay_parser.add_argument("--state-dir", type=Path, default=Path(".atm10-state"))

    subparsers.add_parser("doctor", help="show the dependency-light core posture")
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

    app = CompanionApp(runs_dir=args.runs_dir, state_dir=args.state_dir)
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
