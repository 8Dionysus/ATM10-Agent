from __future__ import annotations

import argparse
import importlib
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.probe_qwen3_voice_support import diagnose_probe_result, probe_architecture_support

main_export: Any | None = None
OVConfig: Any | None = None
OVWeightQuantizationConfig: Any | None = None
AutoConfig: Any | None = None


PRESETS: dict[str, dict[str, str]] = {
    "qwen3-vl-4b": {
        "model_id": "Qwen/Qwen3-VL-4B-Instruct",
        "output_subdir": "qwen3-vl-4b-instruct-ov-custom",
        "task": "image-text-to-text",
    },
    "qwen3-asr-0.6b": {
        "model_id": "Qwen/Qwen3-ASR-0.6B",
        "output_subdir": "qwen3-asr-0.6b-ov-custom",
        "task": "automatic-speech-recognition",
    },
}


def _ensure_export_dependencies() -> None:
    global OVConfig
    global OVWeightQuantizationConfig
    global main_export

    if main_export is None:
        try:
            from optimum.exporters.openvino import main_export as imported_main_export
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Missing optional export dependency: optimum/openvino exporter. "
                "Install export toolchain before running --execute."
            ) from exc
        main_export = imported_main_export

    if OVConfig is None or OVWeightQuantizationConfig is None:
        try:
            from optimum.intel.openvino.configuration import (
                OVConfig as imported_ov_config,
                OVWeightQuantizationConfig as imported_weight_config,
            )
            OVConfig = imported_ov_config
            OVWeightQuantizationConfig = imported_weight_config
        except ModuleNotFoundError:
            # Lightweight fallback keeps tests runnable when exporters are monkeypatched.
            class _FallbackOVWeightQuantizationConfig:
                def __init__(self, *, bits: int) -> None:
                    self.bits = bits

            class _FallbackOVConfig:
                def __init__(self, *, quantization_config: Any) -> None:
                    self.quantization_config = quantization_config

            if OVConfig is None:
                OVConfig = _FallbackOVConfig
            if OVWeightQuantizationConfig is None:
                OVWeightQuantizationConfig = _FallbackOVWeightQuantizationConfig


def _ensure_transformers_dependency() -> None:
    global AutoConfig

    if AutoConfig is not None:
        return
    try:
        from transformers import AutoConfig as imported_auto_config
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing optional export dependency: transformers. "
            "Install export toolchain before running Qwen3-VL custom export."
        ) from exc
    AutoConfig = imported_auto_config


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-qwen3-custom-export")
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


def _resolve_qwen_vl_export_types() -> tuple[Any, Any]:
    module = importlib.import_module("optimum.exporters.openvino.model_configs")

    config_class_candidates = ("Qwen3VLOpenVINOConfig", "Qwen2VLOpenVINOConfig", "QwenVLOpenVINOConfig")
    behavior_class_candidates = ("Qwen3VLConfigBehavior", "QwenVLConfigBehavior", "Qwen2VLConfigBehavior")

    config_cls = next((getattr(module, name) for name in config_class_candidates if hasattr(module, name)), None)
    behavior_cls = next((getattr(module, name) for name in behavior_class_candidates if hasattr(module, name)), None)

    if config_cls is None or behavior_cls is None:
        available = sorted(name for name in dir(module) if "Qwen" in name)
        raise RuntimeError(
            "Cannot resolve Qwen VL export classes from optimum model_configs. "
            f"Found Qwen-related names: {available}"
        )
    return config_cls, behavior_cls


def _qwen3_vl_custom_configs(config: Any) -> tuple[dict[str, Any], Any]:
    if hasattr(config, "text_config") and hasattr(config.text_config, "to_dict"):
        # Optimum qwen2 text export path expects text fields on root config.
        for key, value in config.text_config.to_dict().items():
            if not hasattr(config, key):
                setattr(config, key, value)

    config_cls, behavior_cls = _resolve_qwen_vl_export_types()
    base_cfg = config_cls(config, task="image-text-to-text")
    behavior_names = ("LANGUAGE", "VISION_EMBEDDINGS", "VISION_EMBEDDINGS_MERGER", "TEXT_EMBEDDINGS")
    try:
        behaviors = [getattr(behavior_cls, name) for name in behavior_names]
    except AttributeError as exc:
        raise RuntimeError(
            f"Qwen VL behavior enum {behavior_cls.__name__} is missing expected members: {behavior_names}"
        ) from exc

    custom_export_configs: dict[str, Any] = {}
    for behavior in behaviors:
        key = f"{behavior.value}_model"
        custom_export_configs[key] = base_cfg.with_behavior(behavior)

    def _fn_get_submodels(model: Any) -> dict[str, Any]:
        parts: dict[str, Any] = {}
        for behavior in behaviors:
            key = f"{behavior.value}_model"
            parts[key] = config_cls.get_model_for_behavior(model, behavior)
        return parts

    return custom_export_configs, _fn_get_submodels


def _diagnose_export_error(preset_name: str, error_message: str) -> str:
    normalized = error_message.lower()
    if preset_name == "qwen3-asr-0.6b" and (
        "qwen3_asr" in normalized
        or "unsupported architecture" in normalized
        or "is not supported" in normalized
        or "does not recognize" in normalized
    ):
        return "Likely upstream blocker: current transformers/optimum export path does not support qwen3_asr."

    if preset_name == "qwen3-vl-4b" and ("qwen3_vl" in normalized or "unsupported architecture" in normalized):
        return "Likely upstream blocker: current optimum export path does not support qwen3_vl."

    return "See export_stderr.log for full traceback."


def _build_unlock_gate_payload(support_probe: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "architecture": "qwen3_asr",
        "required_status": "supported",
        "observed_status": support_probe.get("status"),
        "ready": bool(support_probe.get("supported")),
    }


def run_export_qwen3_custom_openvino(
    *,
    preset_name: str,
    execute: bool = False,
    runs_dir: Path = Path("runs"),
    output_root: Path = Path("models"),
    model_source: str | None = None,
    weight_bits: int = 4,
    now: datetime | None = None,
) -> dict[str, Any]:
    if preset_name not in PRESETS:
        raise ValueError(f"Unsupported preset: {preset_name}")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now=now)
    run_json_path = run_dir / "run.json"
    plan_json_path = run_dir / "export_plan.json"
    stderr_path = run_dir / "export_stderr.log"
    stdout_path = run_dir / "export_stdout.log"

    preset = PRESETS[preset_name]
    model_id = preset["model_id"]
    model_source_value = model_source or model_id
    task = preset["task"]
    output_dir = output_root / preset["output_subdir"]

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "qwen3_custom_openvino_export",
        "status": "started",
        "preset": preset_name,
        "execute": execute,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "export_plan_json": str(plan_json_path),
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        },
    }
    _write_json(run_json_path, run_payload)

    plan_payload: dict[str, Any] = {
        "preset": preset_name,
        "model_id": model_id,
        "model_source": model_source_value,
        "task": task,
        "output_dir": str(output_dir),
        "weight_bits": weight_bits,
        "path": "custom_export_configs+fn_get_submodels" if preset_name == "qwen3-vl-4b" else "main_export",
    }
    _write_json(plan_json_path, plan_payload)

    if preset_name == "qwen3-asr-0.6b":
        support_probe = probe_architecture_support(model_source_value, "qwen3_asr")
        unlock_gate = _build_unlock_gate_payload(support_probe)
        plan_payload["support_probe"] = support_probe
        plan_payload["unlock_gate"] = unlock_gate
        _write_json(plan_json_path, plan_payload)
        run_payload["unlock_gate"] = unlock_gate
        if not execute:
            run_payload["status"] = "dry_run"
            _write_json(run_json_path, run_payload)
            return {"run_dir": run_dir, "run_payload": run_payload, "plan_payload": plan_payload, "ok": True}
        if not unlock_gate["ready"]:
            reason = support_probe.get("error") or "unknown probe error"
            stderr_path.write_text(reason, encoding="utf-8")
            stdout_path.write_text("", encoding="utf-8")
            run_payload["status"] = "blocked"
            run_payload["error_code"] = "unlock_gate_blocked"
            run_payload["error"] = f"Transformers support probe failed for qwen3_asr (status={support_probe['status']})."
            run_payload["diagnostic"] = diagnose_probe_result("qwen3_asr", support_probe)
            _write_json(run_json_path, run_payload)
            return {"run_dir": run_dir, "run_payload": run_payload, "plan_payload": plan_payload, "ok": False}

    if not execute:
        run_payload["status"] = "dry_run"
        _write_json(run_json_path, run_payload)
        return {"run_dir": run_dir, "run_payload": run_payload, "plan_payload": plan_payload, "ok": True}

    try:
        _ensure_export_dependencies()
        if preset_name == "qwen3-vl-4b":
            _ensure_transformers_dependency()
            config = AutoConfig.from_pretrained(model_source_value, trust_remote_code=True)
            custom_export_configs, fn_get_submodels = _qwen3_vl_custom_configs(config)
            ov_config = OVConfig(quantization_config=OVWeightQuantizationConfig(bits=weight_bits))
            main_export(
                model_name_or_path=model_source_value,
                output=output_dir,
                task=task,
                trust_remote_code=True,
                custom_export_configs=custom_export_configs,
                fn_get_submodels=fn_get_submodels,
                ov_config=ov_config,
                convert_tokenizer=False,
            )
            stdout_path.write_text("Export completed successfully.", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            run_payload["status"] = "ok"
            run_payload["output_dir"] = str(output_dir)
            _write_json(run_json_path, run_payload)
            return {"run_dir": run_dir, "run_payload": run_payload, "plan_payload": plan_payload, "ok": True}

        if preset_name == "qwen3-asr-0.6b":
            ov_config = OVConfig(quantization_config=OVWeightQuantizationConfig(bits=weight_bits))
            main_export(
                model_name_or_path=model_source_value,
                output=output_dir,
                task=task,
                trust_remote_code=True,
                ov_config=ov_config,
            )
            stdout_path.write_text("Export completed successfully.", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            run_payload["status"] = "ok"
            run_payload["output_dir"] = str(output_dir)
            _write_json(run_json_path, run_payload)
            return {"run_dir": run_dir, "run_payload": run_payload, "plan_payload": plan_payload, "ok": True}

        raise ValueError(f"Custom execute path is not implemented for preset: {preset_name}")
    except Exception as exc:
        trace = traceback.format_exc()
        stderr_path.write_text(trace, encoding="utf-8")
        stdout_path.write_text("", encoding="utf-8")
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        run_payload["diagnostic"] = _diagnose_export_error(preset_name, str(exc))
        _write_json(run_json_path, run_payload)
        return {"run_dir": run_dir, "run_payload": run_payload, "plan_payload": plan_payload, "ok": False}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Custom OpenVINO export path for Qwen3 models (custom_export_configs + fn_get_submodels)."
    )
    parser.add_argument(
        "--preset",
        choices=tuple(PRESETS.keys()),
        required=True,
        help="Export preset.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run export. Without this flag, script runs dry-run only.",
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
        "--weight-bits",
        type=int,
        default=4,
        choices=(4, 8),
        help="Weight-only quantization bits for custom export (default: 4).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_export_qwen3_custom_openvino(
        preset_name=args.preset,
        execute=args.execute,
        runs_dir=args.runs_dir,
        output_root=args.output_root,
        model_source=args.model_source,
        weight_bits=args.weight_bits,
    )
    run_dir = result["run_dir"]
    print(f"[qwen3_custom_export] run_dir: {run_dir}")
    print(f"[qwen3_custom_export] run_json: {run_dir / 'run.json'}")
    print(f"[qwen3_custom_export] plan_json: {run_dir / 'export_plan.json'}")
    print(f"[qwen3_custom_export] status: {result['run_payload']['status']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
