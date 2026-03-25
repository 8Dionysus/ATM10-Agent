from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.grounded_reply_openvino import (  # noqa: E402
    DEFAULT_GROUNDED_REPLY_MODEL_DIR,
    OpenVINOGroundedReplyClient,
)
from src.agent_core.vlm_openvino import (  # noqa: E402
    DEFAULT_OPENVINO_VLM_MODEL_DIR,
    OpenVINOVLMClient,
)

SUMMARY_SCHEMA_VERSION = "pilot_openvino_device_benchmark_v1"
DEFAULT_VISION_DEVICES = ("GPU", "CPU", "NPU")
DEFAULT_TEXT_DEVICES = ("NPU", "CPU", "GPU")
CURRENT_DEFAULT_DEVICES = {
    "vision": "GPU",
    "grounded_reply": "NPU",
}
BENCHMARK_VISION_PROMPT = (
    'Верни JSON {"summary": "...", "next_steps": []} с одной короткой фразой о том, '
    "что видно на игровом экране ATM10."
)
BENCHMARK_TRANSCRIPT = "Что я сейчас вижу?"
BENCHMARK_VISUAL_SUMMARY = "Тёмная пещера, светящиеся блоки, вода слева."
BENCHMARK_HYBRID_SUMMARY = {
    "status": "skipped",
    "reason": "device_benchmark",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-pilot-openvino-device-bench")
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


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _parse_devices(raw_value: str | list[str] | tuple[str, ...], *, defaults: tuple[str, ...]) -> list[str]:
    if isinstance(raw_value, str):
        parts = [item.strip().upper() for item in raw_value.split(",")]
    else:
        parts = [str(item).strip().upper() for item in raw_value]
    normalized = [item for item in parts if item]
    if not normalized:
        normalized = list(defaults)
    deduped: list[str] = []
    for item in normalized:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _generate_fixture_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (640, 360), color=(18, 22, 28))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 250, 640, 360), fill=(24, 48, 32))
    draw.rectangle((430, 70, 620, 280), fill=(18, 24, 38), outline=(79, 99, 128), width=3)
    draw.rectangle((80, 120, 180, 260), fill=(26, 52, 60))
    draw.rectangle((195, 100, 240, 260), fill=(68, 121, 183))
    draw.rectangle((255, 150, 290, 260), fill=(219, 164, 67))
    draw.text((24, 22), "ATM10 device benchmark", fill=(220, 228, 235))
    draw.text((24, 54), "Dark cave, glowing blocks, water left", fill=(168, 184, 200))
    image.save(path, format="PNG")
    return path


def _error_code_from_exception(exc: Exception) -> str:
    message = str(exc).strip().lower()
    if isinstance(exc, FileNotFoundError):
        return "missing_input"
    if "unsupported" in message and "device" in message:
        return "unsupported_device"
    if "device must be one of" in message:
        return "invalid_device"
    if "model directory does not exist" in message:
        return "missing_model_dir"
    return type(exc).__name__.lower()


def _vision_output_chars(result: Mapping[str, Any]) -> int:
    summary = str(result.get("summary", "")).strip()
    next_steps = result.get("next_steps")
    next_steps = next_steps if isinstance(next_steps, list) else []
    return len(summary) + sum(len(str(item).strip()) for item in next_steps if str(item).strip())


def _reply_output_chars(result: Mapping[str, Any]) -> int:
    return len(str(result.get("answer_text", "")).strip())


def _build_recommendation(
    records: list[dict[str, Any]],
    *,
    stage: str,
    current_default: str,
) -> dict[str, Any]:
    successful = [row for row in records if row.get("stage") == stage and row.get("ok") is True]
    if not successful:
        return {
            "stage": stage,
            "recommended_device": None,
            "current_default_device": current_default,
            "current_default_is_best": False,
            "note": "No successful runs for this stage.",
        }
    best = min(successful, key=lambda row: float(row.get("latency_ms") or float("inf")))
    recommended_device = str(best.get("device", "")).strip() or None
    return {
        "stage": stage,
        "recommended_device": recommended_device,
        "current_default_device": current_default,
        "current_default_is_best": recommended_device == current_default,
        "note": (
            f"Current default {current_default} is already the fastest successful device."
            if recommended_device == current_default
            else f"Fastest successful device is {recommended_device}."
        ),
    }


def _write_summary_markdown(
    path: Path,
    *,
    summary_rows: list[dict[str, Any]],
    recommendations: Mapping[str, Mapping[str, Any]],
) -> None:
    lines = [
        "# Pilot OpenVINO Device Benchmark",
        "",
        "## Recommendations",
        "",
    ]
    for stage in ("vision", "grounded_reply"):
        recommendation = recommendations.get(stage, {})
        lines.append(
            f"- `{stage}`: recommended={recommendation.get('recommended_device')} "
            f"(current_default={recommendation.get('current_default_device')}, "
            f"current_default_is_best={recommendation.get('current_default_is_best')})"
        )
        note = str(recommendation.get("note", "")).strip()
        if note:
            lines.append(f"  note: {note}")
    lines.extend(
        [
            "",
            "## Summary Rows",
            "",
            "| stage | device | ok | latency_ms | recommended_device | error_code | output_chars |",
            "| --- | --- | --- | ---: | --- | --- | ---: |",
        ]
    )
    for row in summary_rows:
        lines.append(
            "| {stage} | {device} | {ok} | {latency_ms} | {recommended_device} | {error_code} | {output_chars} |".format(
                stage=row.get("stage"),
                device=row.get("device"),
                ok=row.get("ok"),
                latency_ms=row.get("latency_ms"),
                recommended_device=row.get("recommended_device"),
                error_code=row.get("error_code"),
                output_chars=row.get("output_chars"),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_pilot_openvino_device_benchmark(
    *,
    vision_model_dir: Path = DEFAULT_OPENVINO_VLM_MODEL_DIR,
    text_model_dir: Path = DEFAULT_GROUNDED_REPLY_MODEL_DIR,
    vision_devices: list[str] | tuple[str, ...] = DEFAULT_VISION_DEVICES,
    text_devices: list[str] | tuple[str, ...] = DEFAULT_TEXT_DEVICES,
    image_path: Path | None = None,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
    vlm_client_factory: Callable[..., Any] | None = None,
    grounded_reply_client_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    run_dir = _create_run_dir(runs_dir, now)
    run_json_path = run_dir / "run.json"
    plan_json_path = run_dir / "benchmark_plan.json"
    per_case_results_jsonl_path = run_dir / "per_case_results.jsonl"
    summary_json_path = run_dir / "summary.json"
    summary_md_path = run_dir / "summary.md"

    effective_vision_devices = _parse_devices(vision_devices, defaults=DEFAULT_VISION_DEVICES)
    effective_text_devices = _parse_devices(text_devices, defaults=DEFAULT_TEXT_DEVICES)
    effective_image_path = (
        Path(image_path)
        if image_path is not None
        else _generate_fixture_image(run_dir / "fixtures" / "generated_benchmark_screen.png")
    )
    if not effective_image_path.is_file():
        raise FileNotFoundError(f"image_path does not exist: {effective_image_path}")

    run_payload: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "benchmark_pilot_openvino_devices",
        "status": "started",
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "benchmark_plan_json": str(plan_json_path),
            "per_case_results_jsonl": str(per_case_results_jsonl_path),
            "summary_json": str(summary_json_path),
            "summary_md": str(summary_md_path),
        },
    }
    _write_json(run_json_path, run_payload)
    _write_json(
        plan_json_path,
        {
            "vision_model_dir": str(vision_model_dir),
            "text_model_dir": str(text_model_dir),
            "vision_devices": effective_vision_devices,
            "text_devices": effective_text_devices,
            "image_path": str(effective_image_path),
            "current_default_devices": dict(CURRENT_DEFAULT_DEVICES),
            "stages": ["vision", "grounded_reply", "combined"],
        },
    )

    effective_vlm_factory = vlm_client_factory or OpenVINOVLMClient.from_pretrained
    effective_text_factory = grounded_reply_client_factory or OpenVINOGroundedReplyClient.from_pretrained

    records: list[dict[str, Any]] = []
    vision_clients: dict[str, Any] = {}
    text_clients: dict[str, Any] = {}

    for device in effective_vision_devices:
        record: dict[str, Any] = {
            "model": Path(vision_model_dir).name,
            "stage": "vision",
            "device": device,
            "ok": False,
            "latency_ms": None,
            "error_code": None,
            "output_chars": 0,
        }
        try:
            client = effective_vlm_factory(
                model_dir=vision_model_dir,
                device=device,
                max_new_tokens=64,
                temperature=0.0,
            )
            started = perf_counter()
            result = client.analyze_image(
                image_path=effective_image_path,
                prompt=BENCHMARK_VISION_PROMPT,
            )
            latency_ms = round((perf_counter() - started) * 1000.0, 2)
            record.update(
                {
                    "ok": True,
                    "latency_ms": latency_ms,
                    "output_chars": _vision_output_chars(result),
                }
            )
            vision_clients[device] = client
        except Exception as exc:
            record["error_code"] = _error_code_from_exception(exc)
            record["error"] = str(exc)
        records.append(record)
        _append_jsonl(per_case_results_jsonl_path, record)

    for device in effective_text_devices:
        record = {
            "model": Path(text_model_dir).name,
            "stage": "grounded_reply",
            "device": device,
            "ok": False,
            "latency_ms": None,
            "error_code": None,
            "output_chars": 0,
        }
        try:
            client = effective_text_factory(
                model_dir=text_model_dir,
                device=device,
                max_new_tokens=96,
                temperature=0.1,
            )
            started = perf_counter()
            result = client.generate_reply(
                transcript=BENCHMARK_TRANSCRIPT,
                visual_summary=BENCHMARK_VISUAL_SUMMARY,
                citations=[],
                hybrid_summary=BENCHMARK_HYBRID_SUMMARY,
                degraded_flags=[],
                preferred_language="ru",
            )
            latency_ms = round((perf_counter() - started) * 1000.0, 2)
            record.update(
                {
                    "ok": True,
                    "latency_ms": latency_ms,
                    "output_chars": _reply_output_chars(result),
                }
            )
            text_clients[device] = client
        except Exception as exc:
            record["error_code"] = _error_code_from_exception(exc)
            record["error"] = str(exc)
        records.append(record)
        _append_jsonl(per_case_results_jsonl_path, record)

    for vision_device, vision_client in vision_clients.items():
        for text_device, text_client in text_clients.items():
            record = {
                "model": f"{Path(vision_model_dir).name}+{Path(text_model_dir).name}",
                "stage": "combined",
                "device": f"vision={vision_device};text={text_device}",
                "ok": False,
                "latency_ms": None,
                "error_code": None,
                "output_chars": 0,
            }
            try:
                started = perf_counter()
                vision_result = vision_client.analyze_image(
                    image_path=effective_image_path,
                    prompt=BENCHMARK_VISION_PROMPT,
                )
                reply_result = text_client.generate_reply(
                    transcript=BENCHMARK_TRANSCRIPT,
                    visual_summary=str(vision_result.get("summary", "")).strip() or BENCHMARK_VISUAL_SUMMARY,
                    citations=[],
                    hybrid_summary=BENCHMARK_HYBRID_SUMMARY,
                    degraded_flags=[],
                    preferred_language="ru",
                )
                latency_ms = round((perf_counter() - started) * 1000.0, 2)
                record.update(
                    {
                        "ok": True,
                        "latency_ms": latency_ms,
                        "output_chars": _reply_output_chars(reply_result),
                    }
                )
            except Exception as exc:
                record["error_code"] = _error_code_from_exception(exc)
                record["error"] = str(exc)
            records.append(record)
            _append_jsonl(per_case_results_jsonl_path, record)

    recommendations = {
        "vision": _build_recommendation(
            records,
            stage="vision",
            current_default=CURRENT_DEFAULT_DEVICES["vision"],
        ),
        "grounded_reply": _build_recommendation(
            records,
            stage="grounded_reply",
            current_default=CURRENT_DEFAULT_DEVICES["grounded_reply"],
        ),
    }
    summary_rows: list[dict[str, Any]] = []
    for record in records:
        stage = str(record.get("stage", "")).strip()
        recommendation = recommendations.get(stage, {})
        summary_rows.append(
            {
                "model": record.get("model"),
                "stage": stage,
                "device": record.get("device"),
                "ok": record.get("ok"),
                "latency_ms": record.get("latency_ms"),
                "error_code": record.get("error_code"),
                "output_chars": record.get("output_chars"),
                "recommended_device": recommendation.get("recommended_device"),
            }
        )

    summary_payload: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": "ok",
        "checked_at_utc": _utc_now(),
        "recommendations": recommendations,
        "rows": summary_rows,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "benchmark_plan_json": str(plan_json_path),
            "per_case_results_jsonl": str(per_case_results_jsonl_path),
            "summary_json": str(summary_json_path),
            "summary_md": str(summary_md_path),
        },
    }
    _write_json(summary_json_path, summary_payload)
    _write_summary_markdown(
        summary_md_path,
        summary_rows=summary_rows,
        recommendations=recommendations,
    )

    run_payload["status"] = "completed"
    _write_json(run_json_path, run_payload)
    return summary_payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark active OpenVINO pilot devices for vision and grounded reply.")
    parser.add_argument(
        "--vision-model-dir",
        type=Path,
        default=DEFAULT_OPENVINO_VLM_MODEL_DIR,
        help="OpenVINO VLM model dir (default: models/qwen2.5-vl-7b-instruct-int4-ov).",
    )
    parser.add_argument(
        "--text-model-dir",
        type=Path,
        default=DEFAULT_GROUNDED_REPLY_MODEL_DIR,
        help="OpenVINO grounded reply model dir (default: models/qwen3-8b-int4-cw-ov).",
    )
    parser.add_argument(
        "--vision-devices",
        type=str,
        default=",".join(DEFAULT_VISION_DEVICES),
        help="Comma-separated vision device list (default: GPU,CPU,NPU).",
    )
    parser.add_argument(
        "--text-devices",
        type=str,
        default=",".join(DEFAULT_TEXT_DEVICES),
        help="Comma-separated grounded-reply device list (default: NPU,CPU,GPU).",
    )
    parser.add_argument(
        "--image-path",
        type=Path,
        default=None,
        help="Optional local screenshot path. If omitted, generate a local fixture image inside the run dir.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base runs directory for benchmark artifacts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_pilot_openvino_device_benchmark(
        vision_model_dir=args.vision_model_dir,
        text_model_dir=args.text_model_dir,
        vision_devices=_parse_devices(args.vision_devices, defaults=DEFAULT_VISION_DEVICES),
        text_devices=_parse_devices(args.text_devices, defaults=DEFAULT_TEXT_DEVICES),
        image_path=args.image_path,
        runs_dir=args.runs_dir,
    )
    print(f"[benchmark_pilot_openvino_devices] summary_json: {summary['paths']['summary_json']}")
    print(f"[benchmark_pilot_openvino_devices] summary_md: {summary['paths']['summary_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
