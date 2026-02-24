from __future__ import annotations

import argparse
import os


def build_runbook_url(*, anchor: str, fallback_path: str = "docs/RUNBOOK.md", env: dict[str, str] | None = None) -> str:
    if env is None:
        env = os.environ

    anchor_clean = anchor.lstrip("#")
    fallback_url = f"{fallback_path}#{anchor_clean}"

    server = env.get("GITHUB_SERVER_URL", "").strip()
    repo = env.get("GITHUB_REPOSITORY", "").strip()
    ref_name = env.get("GITHUB_REF_NAME", "").strip()

    if not server or not repo:
        return fallback_url
    if not ref_name:
        ref_name = "main"
    return f"{server}/{repo}/blob/{ref_name}/{fallback_path}#{anchor_clean}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build RUNBOOK markdown URL for CI summaries.")
    parser.add_argument("--anchor", required=True, help="RUNBOOK anchor id (with or without '#').")
    parser.add_argument("--fallback-path", default="docs/RUNBOOK.md", help="Relative fallback markdown path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(build_runbook_url(anchor=args.anchor, fallback_path=args.fallback_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
