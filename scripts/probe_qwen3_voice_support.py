from __future__ import annotations

import argparse
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


STATUS_SUPPORTED = "supported"
STATUS_BLOCKED_UPSTREAM = "blocked_upstream"
STATUS_IMPORT_ERROR = "import_error"
STATUS_RUNTIME_ERROR = "runtime_error"

ARCHITECTURE_TAGS: dict[str, tuple[str, ...]] = {
    "qwen3_asr": ("qwen3_asr",),
    "qwen3_tts": ("qwen3_tts",),
    "qwen3_tts_tokenizer_12hz": ("qwen3_tts_tokenizer_12hz", "qwen3_tts"),
}

DEFAULT_SOURCES: dict[str, str] = {
    "qwen3_asr": "Qwen/Qwen3-ASR-0.6B",
    "qwen3_tts": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "qwen3_tts_tokenizer_12hz": "Qwen/Qwen3-TTS-Tokenizer-12Hz",
}


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-qwen3-voice-probe")
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


def _resolve_transformers_autoconfig() -> Any:
    transformers_module = importlib.import_module("transformers")
    if not hasattr(transformers_module, "AutoConfig"):
        raise RuntimeError("transformers module does not expose AutoConfig.")
    return getattr(transformers_module, "AutoConfig")


def classify_probe_error(error_message: str, architecture_tag: str) -> str:
    normalized = error_message.lower()
    architecture_tokens = ARCHITECTURE_TAGS.get(architecture_tag, (architecture_tag,))
    generic_upstream_tokens = (
        "unsupported architecture",
        "does not recognize",
        "is not supported",
        "unrecognized configuration class",
        "model type",
    )
    import_tokens = (
        "no module named",
        "cannot import name",
        "transformers import failed",
        "does not expose autoconfig",
    )

    if any(token in normalized for token in import_tokens):
        return STATUS_IMPORT_ERROR
    if any(token in normalized for token in architecture_tokens) or any(
        token in normalized for token in generic_upstream_tokens
    ):
        return STATUS_BLOCKED_UPSTREAM
    return STATUS_RUNTIME_ERROR


def probe_architecture_support(model_source: str, architecture_tag: str) -> dict[str, Any]:
    try:
        auto_config = _resolve_transformers_autoconfig()
    except Exception as exc:
        message = f"transformers import failed: {exc}"
        return {
            "architecture_tag": architecture_tag,
            "source": model_source,
            "status": STATUS_IMPORT_ERROR,
            "supported": False,
            "error": message,
            "checked_via": "transformers.AutoConfig.from_pretrained(trust_remote_code=True)",
        }

    try:
        _ = auto_config.from_pretrained(model_source, trust_remote_code=True)
        return {
            "architecture_tag": architecture_tag,
            "source": model_source,
            "status": STATUS_SUPPORTED,
            "supported": True,
            "error": None,
            "checked_via": "transformers.AutoConfig.from_pretrained(trust_remote_code=True)",
        }
    except Exception as exc:
        message = str(exc)
        return {
            "architecture_tag": architecture_tag,
            "source": model_source,
            "status": classify_probe_error(message, architecture_tag),
            "supported": False,
            "error": message,
            "checked_via": "transformers.AutoConfig.from_pretrained(trust_remote_code=True)",
        }


def diagnose_probe_result(architecture_tag: str, probe_result: Mapping[str, Any]) -> str:
    status = probe_result.get("status")
    if status == STATUS_BLOCKED_UPSTREAM:
        return (
            "Likely upstream blocker: current transformers/optimum export path does not support "
            f"{architecture_tag}."
        )
    if status == STATUS_IMPORT_ERROR:
        return "Transformers import/runtime is broken in this environment. Fix dependencies before export."
    if status == STATUS_RUNTIME_ERROR:
        return "Probe failed with non-upstream runtime error. See export_stderr.log for details."
    return "Architecture probe succeeded."


def probe_default_voice_stack(
    *,
    asr_source: str | None = None,
    tts_source: str | None = None,
    tokenizer_source: str | None = None,
) -> dict[str, dict[str, Any]]:
    resolved_asr = asr_source or DEFAULT_SOURCES["qwen3_asr"]
    resolved_tts = tts_source or DEFAULT_SOURCES["qwen3_tts"]
    resolved_tokenizer = tokenizer_source or DEFAULT_SOURCES["qwen3_tts_tokenizer_12hz"]

    return {
        "qwen3_asr": probe_architecture_support(resolved_asr, "qwen3_asr"),
        "qwen3_tts": probe_architecture_support(resolved_tts, "qwen3_tts"),
        "qwen3_tts_tokenizer_12hz": probe_architecture_support(
            resolved_tokenizer,
            "qwen3_tts_tokenizer_12hz",
        ),
    }


def run_probe_qwen3_voice_support(
    *,
    runs_dir: Path = Path("runs"),
    asr_source: str | None = None,
    tts_source: str | None = None,
    tokenizer_source: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    probe_json_path = run_dir / "probe_results.json"

    results = probe_default_voice_stack(
        asr_source=asr_source,
        tts_source=tts_source,
        tokenizer_source=tokenizer_source,
    )

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "qwen3_voice_support_probe",
        "status": "ok",
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "probe_json": str(probe_json_path),
        },
        "summary": {
            key: {
                "supported": value["supported"],
                "status": value["status"],
            }
            for key, value in results.items()
        },
    }
    _write_json(probe_json_path, results)
    _write_json(run_json_path, run_payload)

    return {"run_dir": run_dir, "run_payload": run_payload, "probe_results": results}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe transformers support for Qwen3 voice architectures and write run artifacts."
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base directory for run artifacts (default: runs).",
    )
    parser.add_argument("--asr-source", type=str, default=None, help="Optional ASR model source override.")
    parser.add_argument("--tts-source", type=str, default=None, help="Optional TTS model source override.")
    parser.add_argument(
        "--tokenizer-source",
        type=str,
        default=None,
        help="Optional TTS tokenizer source override.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_probe_qwen3_voice_support(
        runs_dir=args.runs_dir,
        asr_source=args.asr_source,
        tts_source=args.tts_source,
        tokenizer_source=args.tokenizer_source,
    )
    run_dir = result["run_dir"]
    print(f"[qwen3_voice_probe] run_dir: {run_dir}")
    print(f"[qwen3_voice_probe] run_json: {run_dir / 'run.json'}")
    print(f"[qwen3_voice_probe] probe_json: {run_dir / 'probe_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
