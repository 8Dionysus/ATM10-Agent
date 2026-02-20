from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.vlm_stub import DeterministicStubVLM


# 1x1 PNG (transparent) to keep smoke deterministic and dependency-free.
PLACEHOLDER_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sUP4A0AAAAASUVORK5CYII="
)


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S")
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


def _write_placeholder_screenshot(path: Path) -> None:
    path.write_bytes(base64.b64decode(PLACEHOLDER_PNG_BASE64))


def run_phase_a_smoke(*, runs_dir: Path = Path("runs"), now: datetime | None = None) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    screenshot_path = run_dir / "screenshot.png"
    run_json_path = run_dir / "run.json"
    response_json_path = run_dir / "response.json"

    _write_placeholder_screenshot(screenshot_path)

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "phase_a_smoke",
        "screen_source": "placeholder_png",
        "paths": {
            "run_dir": str(run_dir),
            "screenshot": str(screenshot_path),
            "run_json": str(run_json_path),
            "response_json": str(response_json_path),
        },
    }
    run_json_path.write_text(json.dumps(run_payload, indent=2), encoding="utf-8")

    vlm = DeterministicStubVLM()
    response_payload = vlm.analyze_image(
        image_path=screenshot_path,
        prompt="Describe actionable ATM10 context from screenshot.",
    )
    response_json_path.write_text(json.dumps(response_payload, indent=2), encoding="utf-8")

    return {
        "run_dir": run_dir,
        "run_payload": run_payload,
        "response_payload": response_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase A smoke: screenshot -> stub VLM -> artifacts.")
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base directory for run artifacts (default: runs).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_phase_a_smoke(runs_dir=args.runs_dir)
    run_dir = result["run_dir"]
    print(f"[phase_a_smoke] run_dir: {run_dir}")
    print(f"[phase_a_smoke] run_json: {run_dir / 'run.json'}")
    print(f"[phase_a_smoke] response_json: {run_dir / 'response.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
