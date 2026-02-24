from __future__ import annotations

import argparse
import contextlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts.probe_qwen3_voice_support import diagnose_probe_result, probe_architecture_support
except ModuleNotFoundError:  # Supports direct execution: `python scripts/export_qwen3_tts_openvino.py ...`
    from probe_qwen3_voice_support import diagnose_probe_result, probe_architecture_support


PRESET: dict[str, str] = {
    "model_id": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "tokenizer_id": "Qwen/Qwen3-TTS-Tokenizer-12Hz",
    "output_subdir": "qwen3-tts-12hz-0.6b-ov-custom",
    "task": "text-to-audio",
}
BACKEND_SCAFFOLD = "scaffold"
BACKEND_NOTEBOOK_HELPER = "notebook_helper"
WEIGHTS_QUANT_NONE = "none"
WEIGHTS_QUANT_INT4_ASYM = "int4_asym"
WEIGHTS_QUANT_INT4_SYM = "int4_sym"
WEIGHTS_QUANT_INT8 = "int8"
WEIGHTS_QUANT_INT8_ASYM = "int8_asym"
WEIGHTS_QUANT_INT8_SYM = "int8_sym"


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-qwen3-tts-export")
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


def _diagnose_tts_error(error_message: str) -> str:
    normalized = error_message.lower()
    if "qwen3_tts" in normalized or "unsupported architecture" in normalized or "does not recognize" in normalized:
        return "Likely upstream blocker: current transformers/optimum export path does not support qwen3_tts yet."
    return "Custom TTS export pipeline is not finalized yet. See export_stderr.log."


def _diagnose_notebook_helper_error(error_message: str) -> str:
    normalized = error_message.lower()
    if "no module named" in normalized and "qwen_3_tts_helper" in normalized:
        return (
            "Notebook helper module is not importable. "
            "Provide --helper-module-name or add qwen_3_tts_helper.py to PYTHONPATH."
        )
    if "attribute" in normalized and "convert_qwen3_tts_model" in normalized:
        return "Notebook helper module is missing required conversion functions."
    if "nncf is required" in normalized:
        return "NNCF is required for INT8 weight compression. Install nncf in the active environment."
    return "Notebook helper export failed. See export_stderr.log for details."


def _resolve_helper_quantization_config(weights_quantization: str) -> dict[str, Any] | None:
    if weights_quantization == WEIGHTS_QUANT_NONE:
        return None

    try:
        import nncf  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency absence path
        raise RuntimeError("nncf is required for INT8 weight compression in notebook_helper backend.") from exc

    mode_map = {
        WEIGHTS_QUANT_INT4_ASYM: nncf.CompressWeightsMode.INT4_ASYM,
        WEIGHTS_QUANT_INT4_SYM: nncf.CompressWeightsMode.INT4_SYM,
        WEIGHTS_QUANT_INT8: nncf.CompressWeightsMode.INT8,
        WEIGHTS_QUANT_INT8_ASYM: nncf.CompressWeightsMode.INT8_ASYM,
        WEIGHTS_QUANT_INT8_SYM: nncf.CompressWeightsMode.INT8_SYM,
    }
    mode = mode_map.get(weights_quantization)
    if mode is None:
        raise RuntimeError(f"Unsupported weights quantization mode: {weights_quantization}")
    return {"mode": mode}


def _build_unlock_gate_payload(model_probe: Mapping[str, Any], tokenizer_probe: Mapping[str, Any]) -> dict[str, Any]:
    statuses = {
        "qwen3_tts": model_probe.get("status"),
        "qwen3_tts_tokenizer_12hz": tokenizer_probe.get("status"),
    }
    blocked_architectures = [name for name, status in statuses.items() if status != "supported"]
    if not blocked_architectures:
        gate_status = "ready"
    elif any(statuses[name] == "import_error" for name in blocked_architectures):
        gate_status = "import_error"
    elif any(statuses[name] == "runtime_error" for name in blocked_architectures):
        gate_status = "runtime_error"
    elif any(statuses[name] == "blocked_upstream" for name in blocked_architectures):
        gate_status = "blocked_upstream"
    else:
        gate_status = "unknown"

    return {
        "required_status": "supported",
        "architecture_statuses": statuses,
        "blocked_architectures": blocked_architectures,
        "status": gate_status,
        "ready": not blocked_architectures,
    }


def run_export_qwen3_tts_openvino(
    *,
    execute: bool = False,
    runs_dir: Path = Path("runs"),
    output_root: Path = Path("models"),
    model_source: str | None = None,
    tokenizer_source: str | None = None,
    backend: str = BACKEND_SCAFFOLD,
    helper_module_name: str = "qwen_3_tts_helper",
    weights_quantization: str = WEIGHTS_QUANT_NONE,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    plan_json_path = run_dir / "export_plan.json"
    stderr_path = run_dir / "export_stderr.log"
    stdout_path = run_dir / "export_stdout.log"

    model_source_value = model_source or PRESET["model_id"]
    tokenizer_source_value = tokenizer_source or PRESET["tokenizer_id"]
    output_dir = output_root / PRESET["output_subdir"]

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "qwen3_tts_openvino_export",
        "status": "started",
        "execute": execute,
        "backend": backend,
        "weights_quantization": weights_quantization,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "export_plan_json": str(plan_json_path),
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        },
    }
    _write_json(run_json_path, run_payload)

    model_probe = probe_architecture_support(model_source_value, "qwen3_tts")
    tokenizer_probe = probe_architecture_support(tokenizer_source_value, "qwen3_tts_tokenizer_12hz")
    unlock_gate = _build_unlock_gate_payload(model_probe, tokenizer_probe)
    model_supported = bool(model_probe["supported"])
    tokenizer_supported = bool(tokenizer_probe["supported"])
    model_probe_error = model_probe.get("error")
    tokenizer_probe_error = tokenizer_probe.get("error")

    plan_payload: dict[str, Any] = {
        "preset": "qwen3-tts-12hz-0.6b",
        "model_id": PRESET["model_id"],
        "tokenizer_id": PRESET["tokenizer_id"],
        "model_source": model_source_value,
        "tokenizer_source": tokenizer_source_value,
        "backend": backend,
        "helper_module_name": helper_module_name,
        "weights_quantization": weights_quantization,
        "task": PRESET["task"],
        "output_dir": str(output_dir),
        "path": "custom_pipeline_backlog" if backend == BACKEND_SCAFFOLD else "notebook_helper_experimental",
        "model_probe": model_probe,
        "tokenizer_probe": tokenizer_probe,
        "unlock_gate": unlock_gate,
        "model_support": model_supported,
        "model_probe_error": model_probe_error,
        "tokenizer_support": tokenizer_supported,
        "tokenizer_probe_error": tokenizer_probe_error,
        "planned_components": [
            "acoustic_model",
            "tokenizer",
            "vocoder_or_decoder",
        ],
    }
    _write_json(plan_json_path, plan_payload)
    run_payload["unlock_gate"] = unlock_gate

    if not execute:
        run_payload["status"] = "dry_run"
        _write_json(run_json_path, run_payload)
        return {"run_dir": run_dir, "run_payload": run_payload, "plan_payload": plan_payload, "ok": True}

    if backend == BACKEND_NOTEBOOK_HELPER:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        helper_steps: list[dict[str, str]] = []
        quantization_config = _resolve_helper_quantization_config(weights_quantization)

        try:
            with (
                stdout_path.open("w", encoding="utf-8") as stdout_file,
                stderr_path.open("w", encoding="utf-8") as stderr_file,
                contextlib.redirect_stdout(stdout_file),
                contextlib.redirect_stderr(stderr_file),
            ):
                helper_module = importlib.import_module(helper_module_name)
                convert_speech_tokenizer = getattr(helper_module, "convert_speech_tokenizer")
                convert_qwen3_tts_model = getattr(helper_module, "convert_qwen3_tts_model")
                if not callable(convert_speech_tokenizer) or not callable(convert_qwen3_tts_model):
                    raise AttributeError(
                        f"{helper_module_name} must define callable convert_speech_tokenizer and convert_qwen3_tts_model"
                    )

                convert_speech_tokenizer(tokenizer_source_value, output_dir, use_local_dir=False)
                helper_steps.append({"name": "convert_speech_tokenizer", "status": "ok"})
                convert_qwen3_tts_model(
                    model_source_value,
                    output_dir,
                    quantization_config=quantization_config,
                    use_local_dir=False,
                )
                helper_steps.append({"name": "convert_qwen3_tts_model", "status": "ok"})
        except Exception as exc:
            run_payload["status"] = "error"
            run_payload["error_code"] = "notebook_helper_failed"
            run_payload["error"] = str(exc)
            run_payload["diagnostic"] = _diagnose_notebook_helper_error(str(exc))
            run_payload["helper_steps"] = helper_steps
            _write_json(run_json_path, run_payload)
            return {"run_dir": run_dir, "run_payload": run_payload, "plan_payload": plan_payload, "ok": False}

        run_payload["status"] = "completed"
        run_payload["helper_steps"] = helper_steps
        run_payload["unlock_gate"] = unlock_gate
        _write_json(run_json_path, run_payload)
        return {"run_dir": run_dir, "run_payload": run_payload, "plan_payload": plan_payload, "ok": True}

    errors: list[str] = []
    if not unlock_gate["ready"]:
        if not model_supported and model_probe_error:
            errors.append(f"model probe failed: {model_probe_error}")
        if not tokenizer_supported and tokenizer_probe_error:
            errors.append(f"tokenizer probe failed: {tokenizer_probe_error}")
        if not errors:
            errors.append("unlock gate blocked by unsupported architecture status.")
    else:
        errors.append("Custom TTS export implementation is not available yet.")

    stderr_text = "\n\n".join(errors)
    stderr_path.write_text(stderr_text, encoding="utf-8")
    stdout_path.write_text("", encoding="utf-8")

    if not unlock_gate["ready"]:
        run_payload["status"] = "blocked"
        run_payload["error_code"] = "unlock_gate_blocked"
        run_payload["error"] = f"Qwen3 TTS unlock gate blocked (status={unlock_gate['status']})."
        if not model_supported:
            run_payload["diagnostic"] = diagnose_probe_result("qwen3_tts", model_probe)
        elif not tokenizer_supported:
            run_payload["diagnostic"] = diagnose_probe_result("qwen3_tts_tokenizer_12hz", tokenizer_probe)
        else:
            run_payload["diagnostic"] = _diagnose_tts_error(stderr_text)
    else:
        run_payload["status"] = "error"
        run_payload["error_code"] = "export_not_implemented"
        run_payload["error"] = "Qwen3 TTS custom export is not implemented yet after unlock gate passed."
        run_payload["diagnostic"] = _diagnose_tts_error(stderr_text)
    _write_json(run_json_path, run_payload)
    return {"run_dir": run_dir, "run_payload": run_payload, "plan_payload": plan_payload, "ok": False}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold custom OpenVINO export pipeline for Qwen3 TTS with run artifacts in runs/<timestamp>-qwen3-tts-export."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run probe + execute scaffold. Without this flag, script runs dry-run only.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base directory for run artifacts (default: runs).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("models"),
        help="Output root for converted OpenVINO models (default: models).",
    )
    parser.add_argument(
        "--model-source",
        type=str,
        default=None,
        help="Optional model source override (HF repo id or local path).",
    )
    parser.add_argument(
        "--tokenizer-source",
        type=str,
        default=None,
        help="Optional tokenizer source override (HF repo id or local path).",
    )
    parser.add_argument(
        "--backend",
        choices=[BACKEND_SCAFFOLD, BACKEND_NOTEBOOK_HELPER],
        default=BACKEND_SCAFFOLD,
        help="Export backend: scaffold (default) or notebook_helper (experimental).",
    )
    parser.add_argument(
        "--helper-module-name",
        type=str,
        default="qwen_3_tts_helper",
        help="Python module name for notebook helper backend (default: qwen_3_tts_helper).",
    )
    parser.add_argument(
        "--weights-quantization",
        choices=[
            WEIGHTS_QUANT_NONE,
            WEIGHTS_QUANT_INT4_ASYM,
            WEIGHTS_QUANT_INT4_SYM,
            WEIGHTS_QUANT_INT8,
            WEIGHTS_QUANT_INT8_ASYM,
            WEIGHTS_QUANT_INT8_SYM,
        ],
        default=WEIGHTS_QUANT_NONE,
        help="Weight compression mode for notebook_helper backend (default: none).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_export_qwen3_tts_openvino(
        execute=args.execute,
        runs_dir=args.runs_dir,
        output_root=args.output_root,
        model_source=args.model_source,
        tokenizer_source=args.tokenizer_source,
        backend=args.backend,
        helper_module_name=args.helper_module_name,
        weights_quantization=args.weights_quantization,
    )
    run_dir = result["run_dir"]
    print(f"[qwen3_tts_export] run_dir: {run_dir}")
    print(f"[qwen3_tts_export] run_json: {run_dir / 'run.json'}")
    print(f"[qwen3_tts_export] plan_json: {run_dir / 'export_plan.json'}")
    print(f"[qwen3_tts_export] status: {result['run_payload']['status']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
