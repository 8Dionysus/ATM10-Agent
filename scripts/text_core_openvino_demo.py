from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.io_voice import VoiceRuntimeUnavailableError

DEFAULT_TEXT_CORE_MODEL_DIR = Path("models") / "qwen3-8b-int4-cw-ov"


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-text-core-openvino")
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


def _load_openvino_genai() -> Any:
    try:
        import openvino_genai as ov_genai
    except Exception as exc:  # pragma: no cover - dependency presence
        raise VoiceRuntimeUnavailableError(
            "OpenVINO GenAI runtime is not installed. Install dependency: openvino-genai."
        ) from exc
    return ov_genai


def _extract_output_text(result: Any) -> str:
    text_attr = getattr(result, "text", None)
    if text_attr is not None:
        return str(text_attr)

    texts_attr = getattr(result, "texts", None)
    if isinstance(texts_attr, (list, tuple)) and texts_attr:
        return str(texts_attr[0])

    if isinstance(result, str):
        return result

    return str(result)


def run_text_core_openvino_demo(
    *,
    model_dir: Path = DEFAULT_TEXT_CORE_MODEL_DIR,
    prompt: str,
    device: str = "NPU",
    max_new_tokens: int = 128,
    temperature: float = 0.0,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    response_json_path = run_dir / "response.json"

    normalized_prompt = prompt.strip()
    normalized_device = device.upper()

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "text_core_openvino_demo",
        "status": "started",
        "runtime": {
            "model_dir": str(model_dir),
            "device": normalized_device,
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
        },
        "request": {
            "prompt": normalized_prompt,
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "response_json": str(response_json_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        if not normalized_prompt:
            raise ValueError("prompt must be non-empty.")
        if max_new_tokens <= 0:
            raise ValueError("max_new_tokens must be > 0.")
        if not model_dir.exists():
            raise FileNotFoundError(f"Text core model directory does not exist: {model_dir}")

        ov_genai = _load_openvino_genai()
        pipeline = ov_genai.LLMPipeline(str(model_dir), normalized_device)
        result = pipeline.generate(
            normalized_prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )
        output_text = _extract_output_text(result)
        response_payload = {
            "prompt": normalized_prompt,
            "text": output_text,
        }
        _write_json(response_json_path, response_payload)

        run_payload["status"] = "ok"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "response_payload": response_payload,
            "ok": True,
        }
    except Exception as exc:
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        if isinstance(exc, VoiceRuntimeUnavailableError):
            run_payload["error_code"] = "runtime_missing_dependency"
        elif isinstance(exc, FileNotFoundError):
            run_payload["error_code"] = "model_path_missing"
        elif isinstance(exc, ValueError):
            run_payload["error_code"] = "invalid_request"
        else:
            run_payload["error_code"] = "text_core_openvino_failed"
        _write_json(run_json_path, run_payload)
        return {
            "run_dir": run_dir,
            "run_payload": run_payload,
            "response_payload": None,
            "ok": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OpenVINO GenAI text-core demo (Qwen3-8B profile): prompt -> response artifact."
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=DEFAULT_TEXT_CORE_MODEL_DIR,
        help="Path to OpenVINO text model directory (default: models/qwen3-8b-int4-cw-ov).",
    )
    parser.add_argument("--prompt", required=True, help="Prompt text.")
    parser.add_argument(
        "--device",
        type=str,
        default="NPU",
        choices=("CPU", "GPU", "NPU"),
        help="OpenVINO device for LLMPipeline (default: NPU).",
    )
    parser.add_argument("--max-new-tokens", type=int, default=128, help="Generation max_new_tokens (default: 128).")
    parser.add_argument("--temperature", type=float, default=0.0, help="Generation temperature (default: 0.0).")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_text_core_openvino_demo(
        model_dir=args.model_dir,
        prompt=args.prompt,
        device=args.device,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[text_core_openvino_demo] run_dir: {run_dir}")
    print(f"[text_core_openvino_demo] run_json: {run_dir / 'run.json'}")
    print(f"[text_core_openvino_demo] response_json: {run_dir / 'response.json'}")
    if not result["ok"]:
        print(f"[text_core_openvino_demo] error: {result['run_payload']['error']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
