from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_core.io_voice import (  # noqa: E402
    DEFAULT_QWEN3_ASR_MODEL,
    DEFAULT_WHISPER_GENAI_MODEL_DIR,
    QwenASRClient,
    WhisperGenAIASRClient,
)


SUPPORTED_BACKENDS = ("qwen_asr", "whisper_genai")
ARCHIVED_BACKENDS = ("qwen_asr",)


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-asr-backend-bench")
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


def _normalize_text(value: str) -> str:
    lowered = value.lower()
    alnum_space = re.sub(r"[^0-9a-zа-яё\s]+", " ", lowered, flags=re.IGNORECASE)
    return " ".join(alnum_space.split())


def _text_similarity(reference: str, hypothesis: str) -> float:
    a = _normalize_text(reference)
    b = _normalize_text(hypothesis)
    if not a and not b:
        return 1.0
    return float(SequenceMatcher(None, a, b).ratio())


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    if q <= 0.0:
        return float(min(values))
    if q >= 1.0:
        return float(max(values))
    sorted_values = sorted(values)
    idx = int(round((len(sorted_values) - 1) * q))
    return float(sorted_values[idx])


def _load_manifest_samples(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file does not exist: {manifest_path}")
    samples: list[dict[str, Any]] = []
    with manifest_path.open("r", encoding="utf-8") as handle:
        for line_num, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"Manifest line {line_num} must be JSON object.")
            audio_path_value = payload.get("audio_path")
            if not isinstance(audio_path_value, str) or not audio_path_value.strip():
                raise ValueError(f"Manifest line {line_num}: audio_path must be non-empty string.")
            sample_id_value = payload.get("id")
            sample_id = str(sample_id_value) if sample_id_value is not None else f"sample_{line_num:03d}"
            reference = payload.get("reference_text")
            samples.append(
                {
                    "id": sample_id,
                    "audio_path": audio_path_value,
                    "reference_text": str(reference) if isinstance(reference, str) else None,
                }
            )
    return samples


def _build_samples(inputs: Iterable[Path], manifest: Path | None) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for idx, path in enumerate(inputs, start=1):
        sample_id = f"input_{idx:02d}_{path.stem}"
        samples.append({"id": sample_id, "audio_path": str(path), "reference_text": None})

    if manifest is not None:
        samples.extend(_load_manifest_samples(manifest))

    if not samples:
        raise ValueError("No input samples provided. Use --inputs and/or --manifest.")
    return samples


def _build_backend_factories(
    *,
    enabled_backends: set[str],
    qwen_model_id: str,
    qwen_device_map: str,
    qwen_dtype: str,
    qwen_max_new_tokens: int,
    whisper_model_dir: Path,
    whisper_device: str,
    whisper_task: str,
    whisper_language: str | None,
    whisper_max_new_tokens: int,
) -> dict[str, Callable[[], Any]]:
    factories: dict[str, Callable[[], Any]] = {}
    if "qwen_asr" in enabled_backends:
        factories["qwen_asr"] = lambda: QwenASRClient.from_pretrained(
            model_id=qwen_model_id,
            device_map=qwen_device_map,
            dtype=qwen_dtype,
            max_new_tokens=qwen_max_new_tokens,
        )
    if "whisper_genai" in enabled_backends:
        factories["whisper_genai"] = lambda: WhisperGenAIASRClient.from_pretrained(
            model_dir=whisper_model_dir,
            device=whisper_device,
            task=whisper_task,
            max_new_tokens=whisper_max_new_tokens,
            static_language=whisper_language,
        )
    return factories


def _summarize_backend(records: list[dict[str, Any]], load_time_sec: float | None, init_error: str | None) -> dict[str, Any]:
    ok_records = [r for r in records if r.get("status") == "ok"]
    latencies = [float(r["latency_sec"]) for r in ok_records if r.get("latency_sec") is not None]
    similarities = [float(r["similarity"]) for r in ok_records if r.get("similarity") is not None]
    return {
        "load_time_sec": load_time_sec,
        "init_error": init_error,
        "num_samples": len(records),
        "num_ok": len(ok_records),
        "num_error": len(records) - len(ok_records),
        "latency_sec": {
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
            "avg": (sum(latencies) / len(latencies)) if latencies else None,
            "p50": _percentile(latencies, 0.50) if latencies else None,
            "p95": _percentile(latencies, 0.95) if latencies else None,
        },
        "text_similarity_avg": (sum(similarities) / len(similarities)) if similarities else None,
    }


def _render_summary_markdown(summary_payload: Mapping[str, Any]) -> str:
    lines = [
        "# ASR Backend Benchmark Summary",
        "",
        "| backend | load_sec | ok/total | avg_sec | p50_sec | p95_sec | sim_avg |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    per_backend = summary_payload.get("per_backend", {})
    for backend in SUPPORTED_BACKENDS:
        if backend not in per_backend:
            continue
        item = per_backend[backend]
        latency = item.get("latency_sec", {})
        load_sec = item.get("load_time_sec")
        ok = item.get("num_ok")
        total = item.get("num_samples")
        lines.append(
            "| {backend} | {load} | {ok}/{total} | {avg} | {p50} | {p95} | {sim} |".format(
                backend=backend,
                load=f"{load_sec:.3f}" if isinstance(load_sec, (float, int)) else "-",
                ok=ok,
                total=total,
                avg=f"{latency['avg']:.3f}" if isinstance(latency.get("avg"), (float, int)) else "-",
                p50=f"{latency['p50']:.3f}" if isinstance(latency.get("p50"), (float, int)) else "-",
                p95=f"{latency['p95']:.3f}" if isinstance(latency.get("p95"), (float, int)) else "-",
                sim=f"{item['text_similarity_avg']:.3f}"
                if isinstance(item.get("text_similarity_avg"), (float, int))
                else "-",
            )
        )
    return "\n".join(lines) + "\n"


def run_asr_backend_benchmark(
    *,
    inputs: Iterable[Path],
    manifest: Path | None,
    backends: Iterable[str],
    qwen_model_id: str = DEFAULT_QWEN3_ASR_MODEL,
    qwen_device_map: str = "auto",
    qwen_dtype: str = "auto",
    qwen_max_new_tokens: int = 512,
    whisper_model_dir: Path = Path(DEFAULT_WHISPER_GENAI_MODEL_DIR),
    whisper_device: str = "NPU",
    whisper_task: str = "transcribe",
    whisper_language: str | None = None,
    whisper_max_new_tokens: int = 128,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
    backend_factories: Mapping[str, Callable[[], Any]] | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)
    selected_backends = [b for b in backends if b in SUPPORTED_BACKENDS]
    if not selected_backends:
        raise ValueError(f"No valid backends selected. Choose from: {', '.join(SUPPORTED_BACKENDS)}")

    samples = _build_samples(inputs, manifest)
    run_dir = _create_run_dir(runs_dir, now)
    run_json_path = run_dir / "run.json"
    plan_json_path = run_dir / "benchmark_plan.json"
    per_sample_jsonl_path = run_dir / "per_sample_results.jsonl"
    summary_json_path = run_dir / "summary.json"
    summary_md_path = run_dir / "summary.md"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "asr_backend_benchmark",
        "status": "started",
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "benchmark_plan_json": str(plan_json_path),
            "per_sample_results_jsonl": str(per_sample_jsonl_path),
            "summary_json": str(summary_json_path),
            "summary_md": str(summary_md_path),
        },
    }
    _write_json(run_json_path, run_payload)

    plan_payload = {
        "samples": samples,
        "backends": selected_backends,
        "qwen": {
            "model_id": qwen_model_id,
            "device_map": qwen_device_map,
            "dtype": qwen_dtype,
            "max_new_tokens": qwen_max_new_tokens,
        },
        "whisper_genai": {
            "model_dir": str(whisper_model_dir),
            "device": whisper_device,
            "task": whisper_task,
            "language": whisper_language,
            "max_new_tokens": whisper_max_new_tokens,
        },
    }
    _write_json(plan_json_path, plan_payload)

    factories = dict(backend_factories or _build_backend_factories(
        enabled_backends=set(selected_backends),
        qwen_model_id=qwen_model_id,
        qwen_device_map=qwen_device_map,
        qwen_dtype=qwen_dtype,
        qwen_max_new_tokens=qwen_max_new_tokens,
        whisper_model_dir=whisper_model_dir,
        whisper_device=whisper_device,
        whisper_task=whisper_task,
        whisper_language=whisper_language,
        whisper_max_new_tokens=whisper_max_new_tokens,
    ))

    all_records: list[dict[str, Any]] = []
    summary_per_backend: dict[str, Any] = {}

    for backend in selected_backends:
        factory = factories.get(backend)
        if factory is None:
            summary_per_backend[backend] = _summarize_backend(
                [],
                load_time_sec=None,
                init_error=f"Backend factory is not configured: {backend}",
            )
            continue

        client = None
        init_error: str | None = None
        load_time_sec: float | None = None
        t0_load = perf_counter()
        try:
            client = factory()
            load_time_sec = perf_counter() - t0_load
        except Exception as exc:  # pragma: no cover - runtime path
            init_error = str(exc)

        backend_records: list[dict[str, Any]] = []
        if client is not None:
            for sample in samples:
                audio_path = Path(str(sample["audio_path"]))
                sample_id = str(sample["id"])
                reference_text = sample.get("reference_text")
                record: dict[str, Any] = {
                    "backend": backend,
                    "sample_id": sample_id,
                    "audio_path": str(audio_path),
                    "reference_text": reference_text,
                }
                if not audio_path.exists():
                    record["status"] = "error"
                    record["error"] = f"audio_path does not exist: {audio_path}"
                    backend_records.append(record)
                    continue
                t0 = perf_counter()
                try:
                    result = client.transcribe_path(audio_path=audio_path, context="", language=None)
                    latency_sec = perf_counter() - t0
                    text = str(result.get("text", ""))
                    record["status"] = "ok"
                    record["latency_sec"] = latency_sec
                    record["text"] = text
                    record["language"] = str(result.get("language", ""))
                    if isinstance(reference_text, str):
                        record["similarity"] = _text_similarity(reference_text, text)
                except Exception as exc:  # pragma: no cover - runtime path
                    record["status"] = "error"
                    record["error"] = str(exc)
                backend_records.append(record)

        summary_per_backend[backend] = _summarize_backend(
            backend_records,
            load_time_sec=load_time_sec,
            init_error=init_error,
        )
        all_records.extend(backend_records)

    with per_sample_jsonl_path.open("w", encoding="utf-8") as handle:
        for row in all_records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary_payload = {
        "timestamp_utc": _utc_now(),
        "num_samples": len(samples),
        "backends": selected_backends,
        "per_backend": summary_per_backend,
    }
    _write_json(summary_json_path, summary_payload)
    summary_md_path.write_text(_render_summary_markdown(summary_payload), encoding="utf-8")

    run_payload["status"] = "ok"
    _write_json(run_json_path, run_payload)
    return {
        "run_dir": run_dir,
        "run_payload": run_payload,
        "summary_payload": summary_payload,
        "records": all_records,
        "ok": True,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark ASR backends on the same WAV dataset. "
            "whisper_genai is active; qwen_asr is archived."
        )
    )
    parser.add_argument(
        "--inputs",
        type=Path,
        nargs="*",
        default=[],
        help="Input audio files to benchmark.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional JSONL manifest with fields: id, audio_path, reference_text.",
    )
    parser.add_argument(
        "--backends",
        nargs="+",
        choices=SUPPORTED_BACKENDS,
        default=["whisper_genai"],
        help="Backends to include in benchmark (default: whisper_genai only).",
    )
    parser.add_argument(
        "--include-archived-qwen-asr",
        action="store_true",
        help=(
            "Include archived backend(s) in addition to selected backends: "
            + ", ".join(ARCHIVED_BACKENDS)
            + "."
        ),
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")

    parser.add_argument("--qwen-model", type=str, default=DEFAULT_QWEN3_ASR_MODEL, help="Qwen ASR model id/path.")
    parser.add_argument("--qwen-device-map", type=str, default="auto", help="Qwen ASR device_map.")
    parser.add_argument(
        "--qwen-dtype",
        type=str,
        default="auto",
        choices=("auto", "float16", "bfloat16", "float32"),
        help="Qwen ASR dtype.",
    )
    parser.add_argument("--qwen-max-new-tokens", type=int, default=512, help="Qwen ASR max_new_tokens.")

    parser.add_argument(
        "--whisper-model-dir",
        type=Path,
        default=Path(DEFAULT_WHISPER_GENAI_MODEL_DIR),
        help="Whisper OpenVINO model directory.",
    )
    parser.add_argument(
        "--whisper-device",
        type=str,
        default="NPU",
        choices=("CPU", "GPU", "NPU"),
        help="Whisper GenAI device.",
    )
    parser.add_argument(
        "--whisper-task",
        type=str,
        default="transcribe",
        choices=("transcribe", "translate"),
        help="Whisper task.",
    )
    parser.add_argument("--whisper-language", type=str, default=None, help="Optional static language hint.")
    parser.add_argument("--whisper-max-new-tokens", type=int, default=128, help="Whisper max_new_tokens.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected_backends = list(args.backends)
    if args.include_archived_qwen_asr and "qwen_asr" not in selected_backends:
        selected_backends.append("qwen_asr")
    result = run_asr_backend_benchmark(
        inputs=args.inputs,
        manifest=args.manifest,
        backends=selected_backends,
        qwen_model_id=args.qwen_model,
        qwen_device_map=args.qwen_device_map,
        qwen_dtype=args.qwen_dtype,
        qwen_max_new_tokens=args.qwen_max_new_tokens,
        whisper_model_dir=args.whisper_model_dir,
        whisper_device=args.whisper_device,
        whisper_task=args.whisper_task,
        whisper_language=args.whisper_language,
        whisper_max_new_tokens=args.whisper_max_new_tokens,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[asr_backend_bench] run_dir: {run_dir}")
    print(f"[asr_backend_bench] run_json: {run_dir / 'run.json'}")
    print(f"[asr_backend_bench] summary_json: {run_dir / 'summary.json'}")
    print(f"[asr_backend_bench] summary_md: {run_dir / 'summary.md'}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
