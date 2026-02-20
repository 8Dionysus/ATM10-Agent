from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.vlm import VLMClient
from src.agent_core.vlm_openai import DEFAULT_VLM_MODEL, OpenAIResponsesVLM
from src.agent_core.vlm_stub import DeterministicStubVLM


# 1x1 PNG (transparent) to keep smoke deterministic and dependency-free.
PLACEHOLDER_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sUP4A0AAAAASUVORK5CYII="
)
DEFAULT_PROMPT = "Describe actionable ATM10 context from screenshot."
SUPPORTED_VLM_PROVIDERS = ("auto", "stub", "openai")


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


def _resolve_provider(*, requested_provider: str, has_openai_key: bool) -> str:
    provider = requested_provider.lower()
    if provider not in SUPPORTED_VLM_PROVIDERS:
        raise ValueError(f"Unsupported --vlm-provider: {requested_provider}")
    if provider == "auto":
        return "openai" if has_openai_key else "stub"
    return provider


def _build_vlm_client(
    *,
    provider: str,
    vlm_model: str,
    openai_api_key: str | None,
    openai_api_base: str,
) -> VLMClient:
    if provider == "stub":
        return DeterministicStubVLM()
    if provider == "openai":
        return OpenAIResponsesVLM(
            api_key=openai_api_key or "",
            model=vlm_model,
            api_base=openai_api_base,
        )
    raise ValueError(f"Unsupported provider: {provider}")


def run_phase_a_smoke(
    *,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
    vlm_provider: str = "auto",
    vlm_model: str | None = None,
    allow_vlm_fallback: bool = True,
    openai_api_key: str | None = None,
    openai_api_base: str | None = None,
    prompt: str = DEFAULT_PROMPT,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    effective_model = vlm_model or os.getenv("OPENAI_VLM_MODEL", DEFAULT_VLM_MODEL)
    effective_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
    effective_api_base = openai_api_base or os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    resolved_provider = _resolve_provider(
        requested_provider=vlm_provider,
        has_openai_key=bool(effective_api_key),
    )

    run_dir = _create_run_dir(runs_dir, now=now)
    screenshot_path = run_dir / "screenshot.png"
    run_json_path = run_dir / "run.json"
    response_json_path = run_dir / "response.json"

    _write_placeholder_screenshot(screenshot_path)

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "phase_a_smoke",
        "screen_source": "placeholder_png",
        "vlm": {
            "requested": vlm_provider.lower(),
            "resolved": resolved_provider,
            "model": effective_model,
            "fallback_used": False,
            "fallback_reason": None,
            "provider_failed": None,
        },
        "paths": {
            "run_dir": str(run_dir),
            "screenshot": str(screenshot_path),
            "run_json": str(run_json_path),
            "response_json": str(response_json_path),
        },
    }

    try:
        vlm = _build_vlm_client(
            provider=resolved_provider,
            vlm_model=effective_model,
            openai_api_key=effective_api_key,
            openai_api_base=effective_api_base,
        )
        response_payload = vlm.analyze_image(
            image_path=screenshot_path,
            prompt=prompt,
        )
    except Exception as exc:
        if not allow_vlm_fallback or resolved_provider == "stub":
            raise
        run_payload["vlm"]["fallback_used"] = True
        run_payload["vlm"]["fallback_reason"] = str(exc)
        run_payload["vlm"]["provider_failed"] = resolved_provider
        run_payload["vlm"]["resolved"] = "stub"
        vlm = DeterministicStubVLM()
        response_payload = vlm.analyze_image(
            image_path=screenshot_path,
            prompt=prompt,
        )

    run_json_path.write_text(json.dumps(run_payload, indent=2), encoding="utf-8")
    response_json_path.write_text(json.dumps(response_payload, indent=2), encoding="utf-8")

    return {
        "run_dir": run_dir,
        "run_payload": run_payload,
        "response_payload": response_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase A smoke: screenshot -> VLM -> artifacts.")
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base directory for run artifacts (default: runs).",
    )
    parser.add_argument(
        "--vlm-provider",
        choices=SUPPORTED_VLM_PROVIDERS,
        default=os.getenv("PHASE_A_VLM_PROVIDER", "auto"),
        help="VLM provider: auto|stub|openai (default: auto).",
    )
    parser.add_argument(
        "--vlm-model",
        default=os.getenv("OPENAI_VLM_MODEL", DEFAULT_VLM_MODEL),
        help="Model id for provider=openai (default: OPENAI_VLM_MODEL or gpt-4.1-mini).",
    )
    parser.add_argument(
        "--openai-api-base",
        default=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        help="OpenAI API base URL (default: OPENAI_API_BASE or https://api.openai.com/v1).",
    )
    parser.add_argument(
        "--strict-vlm",
        action="store_true",
        help="Disable fallback to stub when provider fails.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_phase_a_smoke(
        runs_dir=args.runs_dir,
        vlm_provider=args.vlm_provider,
        vlm_model=args.vlm_model,
        allow_vlm_fallback=not args.strict_vlm,
        openai_api_base=args.openai_api_base,
    )
    run_dir = result["run_dir"]
    print(f"[phase_a_smoke] run_dir: {run_dir}")
    print(f"[phase_a_smoke] run_json: {run_dir / 'run.json'}")
    print(f"[phase_a_smoke] response_json: {run_dir / 'response.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
