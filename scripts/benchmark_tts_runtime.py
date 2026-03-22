from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.tts_runtime_service import (  # noqa: E402
    _build_piper_engine,
    _build_silero_engine,
    _build_xtts_engine,
)
from src.agent_core.service_sla import build_common_metrics, build_service_sla_summary
from src.agent_core.tts_runtime import CallbackTTSEngine, TTSRequest, TTSRuntimeError, TTSRuntimeService, make_silence_wav_bytes


SUMMARY_SCHEMA_VERSION = "tts_runtime_benchmark_summary_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-tts-runtime-bench")
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


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    if q <= 0.0:
        return float(min(values))
    if q >= 1.0:
        return float(max(values))
    sorted_values = sorted(values)
    index = int(round((len(sorted_values) - 1) * q))
    return float(sorted_values[index])


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Manifest file does not exist: {path}")
    rows: list[dict[str, Any]] = []
    for line_num, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Manifest line {line_num} must be JSON object.")
        text = str(payload.get("text", "")).strip()
        if not text:
            raise ValueError(f"Manifest line {line_num}: text must be non-empty string.")
        rows.append(
            {
                "id": str(payload.get("id") or f"sample_{line_num:03d}"),
                "text": text,
                "language": str(payload.get("language") or "en"),
                "speaker": str(payload["speaker"]) if payload.get("speaker") is not None else None,
                "service_voice": bool(payload.get("service_voice", False)),
                "chunk_chars": int(payload["chunk_chars"]) if payload.get("chunk_chars") is not None else None,
            }
        )
    if not rows:
        raise ValueError(f"No TTS samples found in: {path}")
    return rows


def _build_silence_engine(name: str, *, sample_rate: int = 22050) -> CallbackTTSEngine:
    def _prewarm() -> None:
        return None

    def _synthesize(text: str, _language: str, _speaker: str | None) -> tuple[bytes, int]:
        duration_ms = min(max(300, len(text) * 16), 1500)
        return make_silence_wav_bytes(duration_ms=duration_ms, sample_rate=sample_rate), sample_rate

    return CallbackTTSEngine(name=name, synthesize_fn=_synthesize, prewarm_fn=_prewarm)


def _wrap_engine_with_silence_fallback(
    engine: CallbackTTSEngine,
    *,
    fallback_name: str,
    fallback_sample_rate: int,
) -> CallbackTTSEngine:
    fallback_engine = _build_silence_engine(fallback_name, sample_rate=fallback_sample_rate)
    fallback_state = {"fallback_count": 0}

    def _prewarm() -> None:
        try:
            engine.prewarm()
        except Exception:
            fallback_state["fallback_count"] += 1

    def _synthesize(text: str, language: str, speaker: str | None) -> tuple[bytes, int]:
        try:
            return engine.synthesize(text=text, language=language, speaker=speaker)
        except Exception:
            fallback_state["fallback_count"] += 1
            return fallback_engine.synthesize(text=text, language=language, speaker=speaker)

    wrapped = CallbackTTSEngine(name=engine.name, synthesize_fn=_synthesize, prewarm_fn=_prewarm)
    setattr(wrapped, "_benchmark_fallback_state", fallback_state)
    return wrapped


def _build_benchmark_service(*, cache_items: int, chunk_chars: int, queue_size: int) -> TTSRuntimeService:
    xtts_engine = _wrap_engine_with_silence_fallback(
        _build_xtts_engine(),
        fallback_name="xtts_silence_fallback",
        fallback_sample_rate=24000,
    )
    piper_engine = _wrap_engine_with_silence_fallback(
        _build_piper_engine(),
        fallback_name="piper_silence_fallback",
        fallback_sample_rate=22050,
    )
    try:
        silero_raw = _build_silero_engine()
    except TTSRuntimeError:
        silero_raw = _build_silence_engine("silero_ru_service", sample_rate=24000)
    silero_engine = _wrap_engine_with_silence_fallback(
        silero_raw,
        fallback_name="silero_silence_fallback",
        fallback_sample_rate=24000,
    )
    return TTSRuntimeService(
        xtts_engine=xtts_engine,
        piper_engine=piper_engine,
        silero_engine=silero_engine,
        max_chunk_chars=chunk_chars,
        queue_size=queue_size,
        cache=None,
    )


def _engine_fallback_counts(service: TTSRuntimeService) -> dict[str, int]:
    counts: dict[str, int] = {}
    for engine in (service.xtts_engine, service.piper_engine, service.silero_engine):
        if engine is None:
            continue
        fallback_state = getattr(engine, "_benchmark_fallback_state", None)
        if isinstance(fallback_state, dict):
            counts[str(engine.name)] = int(fallback_state.get("fallback_count", 0))
    return counts


def run_benchmark_tts_runtime(
    *,
    manifest: Path = Path("tests") / "fixtures" / "tts_benchmark_sample.jsonl",
    profile: str = "baseline_first",
    policy: str = "signal_only",
    cache_items: int = 512,
    chunk_chars: int = 220,
    queue_size: int = 128,
    runs_dir: Path = Path("runs"),
    now: datetime | None = None,
    service: TTSRuntimeService | None = None,
    service_builder: Callable[..., TTSRuntimeService] | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)
    samples = _load_manifest(manifest)
    run_dir = _create_run_dir(runs_dir, now)
    run_json_path = run_dir / "run.json"
    plan_json_path = run_dir / "benchmark_plan.json"
    per_sample_jsonl_path = run_dir / "per_sample_results.jsonl"
    summary_json_path = run_dir / "summary.json"
    service_sla_summary_path = run_dir / "service_sla_summary.json"

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "benchmark_tts_runtime",
        "status": "started",
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "benchmark_plan_json": str(plan_json_path),
            "per_sample_results_jsonl": str(per_sample_jsonl_path),
            "summary_json": str(summary_json_path),
            "service_sla_summary_json": str(service_sla_summary_path),
        },
    }
    _write_json(run_json_path, run_payload)
    _write_json(
        plan_json_path,
        {
            "samples": samples,
            "profile": profile,
            "policy": policy,
            "cache_items": cache_items,
            "chunk_chars": chunk_chars,
            "queue_size": queue_size,
        },
    )

    effective_service = service
    if effective_service is None:
        builder = service_builder or _build_benchmark_service
        effective_service = builder(
            cache_items=cache_items,
            chunk_chars=chunk_chars,
            queue_size=queue_size,
        )

    prewarm_status = effective_service.prewarm()
    records: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    engine_usage: dict[str, int] = {}

    for sample in samples:
        request_payload = TTSRequest(
            text=str(sample["text"]),
            language=str(sample["language"]),
            speaker=sample["speaker"],
            service_voice=bool(sample["service_voice"]),
            chunk_chars=sample["chunk_chars"],
        )
        record: dict[str, Any] = {
            "sample_id": str(sample["id"]),
            "text": str(sample["text"]),
            "language": request_payload.language,
            "speaker": request_payload.speaker,
            "service_voice": request_payload.service_voice,
        }
        started = perf_counter()
        try:
            result = effective_service.synthesize(request_payload)
            latency_ms = (perf_counter() - started) * 1000.0
            latencies_ms.append(latency_ms)
            chunks = result.get("chunks", [])
            chunk_rows = []
            total_audio_bytes = 0
            for chunk in chunks:
                engine_name = str(chunk.engine)
                engine_usage[engine_name] = engine_usage.get(engine_name, 0) + 1
                audio_length = len(chunk.audio_wav_bytes)
                total_audio_bytes += audio_length
                chunk_rows.append(
                    {
                        "index": int(chunk.index),
                        "engine": engine_name,
                        "sample_rate": int(chunk.sample_rate),
                        "audio_bytes": audio_length,
                        "cached": bool(chunk.cached),
                    }
                )
            non_empty_audio = bool(chunk_rows) and all(int(item["audio_bytes"]) > 0 for item in chunk_rows)
            record.update(
                {
                    "status": "ok",
                    "latency_ms": latency_ms,
                    "chunk_count": int(result.get("chunk_count", 0)),
                    "cache_hits": int(result.get("cache_hits", 0)),
                    "router_chain": list(result.get("router_chain", [])),
                    "non_empty_audio": non_empty_audio,
                    "total_audio_bytes": total_audio_bytes,
                    "chunks": chunk_rows,
                }
            )
        except Exception as exc:
            record["status"] = "error"
            record["error"] = str(exc)
        records.append(record)

    with per_sample_jsonl_path.open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    ok_records = [record for record in records if record.get("status") == "ok"]
    total_chunk_count = sum(int(record.get("chunk_count", 0)) for record in ok_records)
    total_cache_hits = sum(int(record.get("cache_hits", 0)) for record in ok_records)
    non_empty_audio_count = sum(1 for record in ok_records if bool(record.get("non_empty_audio")))
    chunk_count_mean = (
        sum(int(record.get("chunk_count", 0)) for record in ok_records) / len(ok_records)
        if ok_records
        else None
    )
    summary_payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "timestamp_utc": _utc_now(),
        "num_samples": len(samples),
        "profile": profile,
        "policy": policy,
        "prewarm": prewarm_status,
        "engine_fallback_counts": _engine_fallback_counts(effective_service),
        "summary": {
            "num_ok": len(ok_records),
            "num_error": len(records) - len(ok_records),
            "latency_ms": {
                "min": min(latencies_ms) if latencies_ms else None,
                "max": max(latencies_ms) if latencies_ms else None,
                "avg": (sum(latencies_ms) / len(latencies_ms)) if latencies_ms else None,
                "p50": _percentile(latencies_ms, 0.50),
                "p95": _percentile(latencies_ms, 0.95),
            },
            "chunk_count_mean": chunk_count_mean,
            "cache_hit_rate": (float(total_cache_hits) / float(total_chunk_count)) if total_chunk_count > 0 else None,
            "non_empty_audio_rate": (
                float(non_empty_audio_count) / float(len(ok_records)) if ok_records else None
            ),
            "engine_usage": engine_usage,
        },
    }
    _write_json(summary_json_path, summary_payload)

    status = "ok"
    breaches: list[str] = []
    if len(ok_records) != len(records):
        status = "error"
        breaches.append("sample_errors_present")
    if ok_records and non_empty_audio_count != len(ok_records):
        status = "error"
        breaches.append("empty_audio_detected")

    service_sla_summary = build_service_sla_summary(
        service_name="voice_tts",
        surface="benchmark",
        backend="in_process",
        profile=profile,
        policy=policy,
        status=status,
        metrics=build_common_metrics(
            sample_count=len(records),
            success_count=len(ok_records),
            latency_values_ms=latencies_ms,
        ),
        quality={
            "non_empty_audio_rate": summary_payload["summary"]["non_empty_audio_rate"],
            "chunk_count_mean": chunk_count_mean,
            "cache_hit_rate": summary_payload["summary"]["cache_hit_rate"],
        },
        thresholds={},
        warnings=[],
        breaches=breaches,
        paths={
            "run_dir": run_dir,
            "run_json": run_json_path,
            "benchmark_plan_json": plan_json_path,
            "per_sample_results_jsonl": per_sample_jsonl_path,
            "summary_json": summary_json_path,
            "service_sla_summary_json": service_sla_summary_path,
        },
    )
    _write_json(service_sla_summary_path, service_sla_summary)

    run_payload["status"] = "ok"
    _write_json(run_json_path, run_payload)
    return {
        "ok": True,
        "run_dir": run_dir,
        "run_payload": run_payload,
        "summary_payload": summary_payload,
        "service_sla_summary": service_sla_summary,
        "records": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark in-process TTS runtime baseline on fixture text cases.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("tests") / "fixtures" / "tts_benchmark_sample.jsonl",
        help="JSONL manifest with fields: id, text, language?, speaker?, service_voice?, chunk_chars?.",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="baseline_first",
        help="Profile label for normalized SLA summary (default: baseline_first).",
    )
    parser.add_argument(
        "--policy",
        choices=("signal_only", "fail_on_breach"),
        default="signal_only",
        help="Normalized SLA policy label (default: signal_only).",
    )
    parser.add_argument("--cache-items", type=int, default=512, help="Phrase cache max entries (default: 512).")
    parser.add_argument("--chunk-chars", type=int, default=220, help="Chunk size for long text (default: 220).")
    parser.add_argument("--queue-size", type=int, default=128, help="Queue max size (default: 128).")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_benchmark_tts_runtime(
        manifest=args.manifest,
        profile=args.profile,
        policy=args.policy,
        cache_items=args.cache_items,
        chunk_chars=args.chunk_chars,
        queue_size=args.queue_size,
        runs_dir=args.runs_dir,
    )
    run_dir = result["run_dir"]
    print(f"[benchmark_tts_runtime] run_dir: {run_dir}")
    print(f"[benchmark_tts_runtime] run_json: {run_dir / 'run.json'}")
    print(f"[benchmark_tts_runtime] summary_json: {run_dir / 'summary.json'}")
    print(f"[benchmark_tts_runtime] service_sla_summary_json: {run_dir / 'service_sla_summary.json'}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
