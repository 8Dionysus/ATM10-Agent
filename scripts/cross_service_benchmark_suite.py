from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import wave
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping
from urllib import error as url_error
from urllib import request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmark_asr_backends import run_asr_backend_benchmark
from scripts.benchmark_tts_runtime import run_benchmark_tts_runtime
from scripts.eval_kag_file import run_eval_kag_file
from scripts.eval_kag_neo4j import run_eval_kag_neo4j
from scripts.eval_retrieval import run_eval_retrieval
from src.agent_core.combo_a_profile import (
    COMBO_A_PROFILE,
    DEFAULT_COMBO_A_NEO4J_DATABASE,
    DEFAULT_COMBO_A_NEO4J_URL,
    DEFAULT_COMBO_A_NEO4J_USER,
    DEFAULT_COMBO_A_QDRANT_URL,
    DEFAULT_PROFILE,
    qdrant_host_port_from_url,
    seed_combo_a_fixture_data,
)
from src.agent_core.service_sla import (
    CROSS_SERVICE_BENCHMARK_SUITE_SCHEMA,
    build_common_metrics,
    build_service_sla_summary,
    build_suite_summary_row,
    degraded_services as build_degraded_services,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-cross-service-suite")
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


def _write_summary_md(path: Path, *, suite_payload: Mapping[str, Any]) -> None:
    lines = [
        "# Cross-Service Benchmark Suite Summary",
        "",
        f"- `status`: {suite_payload.get('status', 'n/a')}",
        f"- `overall_sla_status`: {suite_payload.get('overall_sla_status', 'n/a')}",
        "",
        "| source | backend | status | sla_status | sample_count | latency_p95_ms | quality |",
        "|---|---|---|---|---:|---:|---|",
    ]
    rows = suite_payload.get("summary_matrix", [])
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            quality_name = row.get("quality_primary_name")
            quality_value = row.get("quality_primary_value")
            quality_cell = "-"
            if quality_name is not None and quality_value is not None:
                quality_cell = f"{quality_name}={quality_value}"
            lines.append(
                "| {source} | {backend} | {status} | {sla_status} | {sample_count} | {latency_p95_ms} | {quality_cell} |".format(
                    source=str(row.get("source", "")),
                    backend=str(row.get("backend", "")),
                    status=str(row.get("status", "")),
                    sla_status=str(row.get("sla_status", "")),
                    sample_count=row.get("sample_count", "-"),
                    latency_p95_ms=row.get("latency_p95_ms", "-"),
                    quality_cell=quality_cell,
                )
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _generate_tone_wav(path: Path, *, frequency_hz: float, duration_sec: float = 0.20, sample_rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    num_samples = max(1, int(sample_rate * duration_sec))
    frames = bytearray()
    amplitude = 0.12
    for index in range(num_samples):
        value = amplitude * math.sin(2.0 * math.pi * frequency_hz * (index / sample_rate))
        pcm16 = int(max(-1.0, min(1.0, value)) * 32767.0)
        frames.extend(struct.pack("<h", pcm16))
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(frames))


def _create_default_asr_manifest(run_dir: Path) -> Path:
    fixture_dir = run_dir / "generated-fixtures" / "voice_asr"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    samples = (
        ("whisper_fixture_alpha", 440.0),
        ("whisper_fixture_beta", 554.37),
    )
    for sample_id, frequency_hz in samples:
        audio_path = fixture_dir / f"{sample_id}.wav"
        _generate_tone_wav(audio_path, frequency_hz=frequency_hz)
        rows.append(
            {
                "id": sample_id,
                "audio_path": str(audio_path),
                "reference_text": sample_id,
            }
        )
    manifest_path = fixture_dir / "manifest.jsonl"
    manifest_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _smoke_stub_backend_factories(*, enabled: bool, backend_name: str) -> Mapping[str, Callable[[], Any]] | None:
    if not enabled:
        return None

    class _FakeASRClient:
        def transcribe_path(self, *, audio_path: Path, context: str, language: str | None) -> dict[str, str]:
            _ = context, language
            return {"text": audio_path.stem, "language": "en"}

    return {backend_name: lambda: _FakeASRClient()}


def _load_required_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"required summary artifact missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"required summary root must be object: {path}")
    return payload


def _normalize_text(value: str) -> str:
    return " ".join(str(value).lower().split())


def _text_similarity(reference: str | None, hypothesis: str | None) -> float | None:
    if reference is None:
        return None
    return float(SequenceMatcher(None, _normalize_text(reference), _normalize_text(hypothesis or "")).ratio())


def _request_json(*, method: str, url: str, payload: Mapping[str, Any] | None, timeout_sec: float) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        method=method,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout_sec) as response:
            raw = response.read().decode("utf-8")
    except url_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from service: {details}") from exc
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc
    parsed = json.loads(raw) if raw else {}
    if not isinstance(parsed, dict):
        raise RuntimeError("service response root must be object")
    return parsed


def _write_live_benchmark_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_jsonl_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"manifest line {line_no} must be JSON object")
        rows.append(payload)
    if not rows:
        raise ValueError(f"manifest is empty: {path}")
    return rows


def _create_named_child_run_dir(root: Path, name: str, now: datetime) -> Path:
    base_name = now.strftime(f"%Y%m%d_%H%M%S-{name}")
    run_dir = root / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir
    suffix = 1
    while True:
        candidate = root / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def run_live_voice_asr_service_benchmark(
    *,
    service_url: str,
    manifest: Path,
    profile: str,
    policy: str,
    runs_dir: Path,
    timeout_sec: float = 120.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)
    run_dir = _create_named_child_run_dir(runs_dir, "voice-asr-service-bench", now)
    run_json_path = run_dir / "run.json"
    per_sample_jsonl_path = run_dir / "per_sample_results.jsonl"
    summary_json_path = run_dir / "summary.json"
    service_sla_summary_path = run_dir / "service_sla_summary.json"
    rows = _load_jsonl_manifest(manifest)
    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "voice_asr_service_benchmark",
        "status": "started",
        "profile": profile,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "per_sample_results_jsonl": str(per_sample_jsonl_path),
            "summary_json": str(summary_json_path),
            "service_sla_summary_json": str(service_sla_summary_path),
        },
    }
    _write_live_benchmark_json(run_json_path, run_payload)
    records: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    try:
        for row in rows:
            started = perf_counter()
            record: dict[str, Any] = {
                "id": str(row.get("id", "")),
                "audio_path": str(row.get("audio_path", "")),
                "reference_text": row.get("reference_text"),
            }
            try:
                response = _request_json(
                    method="POST",
                    url=f"{service_url.rstrip('/')}/asr",
                    payload={
                        "audio_path": str(row.get("audio_path", "")),
                        "context": "",
                        "language": "en",
                    },
                    timeout_sec=timeout_sec,
                )
                result_payload = response.get("result")
                result_payload = result_payload if isinstance(result_payload, Mapping) else {}
                latency_ms = (perf_counter() - started) * 1000.0
                latencies_ms.append(latency_ms)
                record.update(
                    {
                        "status": "ok",
                        "latency_ms": latency_ms,
                        "text": result_payload.get("text"),
                        "language": result_payload.get("language"),
                        "text_similarity": _text_similarity(
                            row.get("reference_text"),
                            result_payload.get("text"),
                        ),
                    }
                )
            except Exception as exc:
                record["status"] = "error"
                record["error"] = str(exc)
            records.append(record)

        with per_sample_jsonl_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        ok_records = [record for record in records if record.get("status") == "ok"]
        similarities = [
            float(record["text_similarity"])
            for record in ok_records
            if record.get("text_similarity") is not None
        ]
        summary_payload = {
            "schema_version": "voice_asr_service_benchmark_summary_v1",
            "profile": profile,
            "policy": policy,
            "status": "ok" if len(ok_records) == len(records) else "error",
            "service_url": service_url,
            "summary": {
                "num_samples": len(records),
                "num_ok": len(ok_records),
                "num_error": len(records) - len(ok_records),
                "text_similarity_avg": (sum(similarities) / len(similarities)) if similarities else None,
            },
        }
        _write_live_benchmark_json(summary_json_path, summary_payload)
        service_sla_summary = build_service_sla_summary(
            service_name="voice_asr",
            surface="benchmark",
            backend="voice_runtime_service",
            profile=profile,
            policy=policy,
            status=summary_payload["status"],
            metrics=build_common_metrics(
                sample_count=len(records),
                success_count=len(ok_records),
                latency_values_ms=latencies_ms,
            ),
            quality={"text_similarity_avg": summary_payload["summary"]["text_similarity_avg"]},
            thresholds={},
            warnings=[],
            breaches=[] if len(ok_records) == len(records) else ["sample_errors_present"],
            paths={
                "run_dir": run_dir,
                "run_json": run_json_path,
                "per_sample_results_jsonl": per_sample_jsonl_path,
                "summary_json": summary_json_path,
                "service_sla_summary_json": service_sla_summary_path,
            },
        )
        _write_live_benchmark_json(service_sla_summary_path, service_sla_summary)
        run_payload["status"] = summary_payload["status"]
        _write_live_benchmark_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "service_sla_summary": service_sla_summary,
        }
    except Exception as exc:
        service_sla_summary = build_service_sla_summary(
            service_name="voice_asr",
            surface="benchmark",
            backend="voice_runtime_service",
            profile=profile,
            policy=policy,
            status="error",
            metrics=build_common_metrics(sample_count=0, success_count=0, error_count=1, latency_values_ms=[]),
            quality={},
            thresholds={},
            warnings=[],
            breaches=[f"service_error: {exc}"],
            paths={
                "run_dir": run_dir,
                "run_json": run_json_path,
                "summary_json": summary_json_path,
                "service_sla_summary_json": service_sla_summary_path,
            },
        )
        _write_live_benchmark_json(service_sla_summary_path, service_sla_summary)
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_live_benchmark_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "service_sla_summary": service_sla_summary,
        }


def run_live_tts_service_benchmark(
    *,
    service_url: str,
    manifest: Path,
    profile: str,
    policy: str,
    runs_dir: Path,
    timeout_sec: float = 120.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)
    run_dir = _create_named_child_run_dir(runs_dir, "voice-tts-service-bench", now)
    run_json_path = run_dir / "run.json"
    per_sample_jsonl_path = run_dir / "per_sample_results.jsonl"
    summary_json_path = run_dir / "summary.json"
    service_sla_summary_path = run_dir / "service_sla_summary.json"
    rows = _load_jsonl_manifest(manifest)
    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "voice_tts_service_benchmark",
        "status": "started",
        "profile": profile,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "per_sample_results_jsonl": str(per_sample_jsonl_path),
            "summary_json": str(summary_json_path),
            "service_sla_summary_json": str(service_sla_summary_path),
        },
    }
    _write_live_benchmark_json(run_json_path, run_payload)
    records: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    try:
        for row in rows:
            started = perf_counter()
            record: dict[str, Any] = {
                "id": str(row.get("id", "")),
                "text": str(row.get("text", "")),
            }
            try:
                request_payload = {
                    "text": str(row.get("text", "")),
                    "language": str(row.get("language") or "en"),
                    "speaker": row.get("speaker"),
                    "service_voice": bool(row.get("service_voice", False)),
                }
                if row.get("chunk_chars") is not None:
                    request_payload["chunk_chars"] = int(row["chunk_chars"])
                response = _request_json(
                    method="POST",
                    url=f"{service_url.rstrip('/')}/tts",
                    payload=request_payload,
                    timeout_sec=timeout_sec,
                )
                result_payload = response.get("result")
                result_payload = result_payload if isinstance(result_payload, Mapping) else {}
                chunks = result_payload.get("chunks")
                chunks = chunks if isinstance(chunks, list) else []
                latency_ms = (perf_counter() - started) * 1000.0
                latencies_ms.append(latency_ms)
                non_empty_audio = bool(chunks) and all(
                    isinstance(chunk, Mapping) and bool(str(chunk.get("audio_wav_b64", "")).strip())
                    for chunk in chunks
                )
                record.update(
                    {
                        "status": "ok",
                        "latency_ms": latency_ms,
                        "chunk_count": int(result_payload.get("chunk_count", 0)),
                        "cache_hits": int(result_payload.get("cache_hits", 0)),
                        "non_empty_audio": non_empty_audio,
                    }
                )
            except Exception as exc:
                record["status"] = "error"
                record["error"] = str(exc)
            records.append(record)

        with per_sample_jsonl_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

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
            "schema_version": "voice_tts_service_benchmark_summary_v1",
            "profile": profile,
            "policy": policy,
            "status": "ok" if len(ok_records) == len(records) else "error",
            "service_url": service_url,
            "summary": {
                "num_samples": len(records),
                "num_ok": len(ok_records),
                "num_error": len(records) - len(ok_records),
                "non_empty_audio_rate": (
                    float(non_empty_audio_count) / float(len(ok_records)) if ok_records else None
                ),
                "chunk_count_mean": chunk_count_mean,
                "cache_hit_rate": (
                    float(total_cache_hits) / float(total_chunk_count) if total_chunk_count > 0 else None
                ),
            },
        }
        _write_live_benchmark_json(summary_json_path, summary_payload)
        breaches: list[str] = []
        if len(ok_records) != len(records):
            breaches.append("sample_errors_present")
        if ok_records and non_empty_audio_count != len(ok_records):
            breaches.append("empty_audio_detected")
        service_sla_summary = build_service_sla_summary(
            service_name="voice_tts",
            surface="benchmark",
            backend="tts_runtime_service",
            profile=profile,
            policy=policy,
            status="ok" if not breaches else "error",
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
                "per_sample_results_jsonl": per_sample_jsonl_path,
                "summary_json": summary_json_path,
                "service_sla_summary_json": service_sla_summary_path,
            },
        )
        _write_live_benchmark_json(service_sla_summary_path, service_sla_summary)
        run_payload["status"] = service_sla_summary["status"]
        _write_live_benchmark_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "service_sla_summary": service_sla_summary,
        }
    except Exception as exc:
        service_sla_summary = build_service_sla_summary(
            service_name="voice_tts",
            surface="benchmark",
            backend="tts_runtime_service",
            profile=profile,
            policy=policy,
            status="error",
            metrics=build_common_metrics(sample_count=0, success_count=0, error_count=1, latency_values_ms=[]),
            quality={},
            thresholds={},
            warnings=[],
            breaches=[f"service_error: {exc}"],
            paths={
                "run_dir": run_dir,
                "run_json": run_json_path,
                "summary_json": summary_json_path,
                "service_sla_summary_json": service_sla_summary_path,
            },
        )
        _write_live_benchmark_json(service_sla_summary_path, service_sla_summary)
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_live_benchmark_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "service_sla_summary": service_sla_summary,
        }


def run_cross_service_benchmark_suite(
    *,
    profile: str = "baseline_first",
    policy: str = "signal_only",
    voice_asr_primary_backend: str = "whisper_genai",
    smoke_stub_voice_asr: bool = False,
    tts_manifest: Path = Path("tests") / "fixtures" / "tts_benchmark_sample.jsonl",
    retrieval_docs_path: Path = Path("tests") / "fixtures" / "retrieval_docs_sample.jsonl",
    retrieval_eval_path: Path = Path("tests") / "fixtures" / "retrieval_eval_sample.jsonl",
    kag_docs_path: Path = Path("tests") / "fixtures" / "kag_neo4j_docs_sample.jsonl",
    kag_eval_path: Path = Path("tests") / "fixtures" / "kag_neo4j_eval_sample.jsonl",
    voice_service_url: str = "http://127.0.0.1:8765",
    tts_service_url: str = "http://127.0.0.1:8780",
    qdrant_url: str = DEFAULT_COMBO_A_QDRANT_URL,
    neo4j_url: str = DEFAULT_COMBO_A_NEO4J_URL,
    neo4j_database: str = DEFAULT_COMBO_A_NEO4J_DATABASE,
    neo4j_user: str = DEFAULT_COMBO_A_NEO4J_USER,
    neo4j_password: str | None = None,
    runs_dir: Path = Path("runs"),
    summary_json: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if profile not in {DEFAULT_PROFILE, COMBO_A_PROFILE}:
        raise ValueError(f"profile must be one of {[DEFAULT_PROFILE, COMBO_A_PROFILE]!r}.")
    if policy not in {"signal_only", "fail_on_breach"}:
        raise ValueError("policy must be signal_only or fail_on_breach.")
    if now is None:
        now = datetime.now(timezone.utc)

    run_dir = _create_run_dir(runs_dir, now)
    run_json_path = run_dir / "run.json"
    suite_summary_history_path = run_dir / "cross_service_benchmark_suite.json"
    suite_summary_out_path = summary_json if summary_json is not None else suite_summary_history_path
    summary_md_path = run_dir / "summary.md"
    child_runs_root = run_dir / "child_runs"
    child_runs_root.mkdir(parents=True, exist_ok=True)

    run_payload: dict[str, Any] = {
        "timestamp_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": "cross_service_benchmark_suite",
        "status": "started",
        "profile": profile,
        "policy": policy,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(suite_summary_out_path),
            "history_summary_json": str(suite_summary_history_path),
            "summary_md": str(summary_md_path),
            "child_runs_root": str(child_runs_root),
        },
    }
    _write_json(run_json_path, run_payload)

    warnings: list[str] = []
    services: dict[str, dict[str, Any]] = {}
    child_paths: dict[str, dict[str, str | None]] = {}
    try:
        asr_manifest = _create_default_asr_manifest(run_dir)
        combo_a_seed_result = None
        qdrant_host, qdrant_port = qdrant_host_port_from_url(qdrant_url)

        if profile == COMBO_A_PROFILE:
            combo_a_seed_result = seed_combo_a_fixture_data(
                scope="cross_service_suite",
                docs_path=kag_docs_path,
                runs_dir=child_runs_root / "combo_a_seed",
                qdrant_host=qdrant_host,
                qdrant_port=qdrant_port,
                neo4j_url=neo4j_url,
                neo4j_database=neo4j_database,
                neo4j_user=neo4j_user,
                neo4j_password=neo4j_password,
                now=now,
            )
            if not combo_a_seed_result["ok"]:
                raise RuntimeError(str(combo_a_seed_result["run_payload"].get("error", "combo_a seed failed")))
            warnings.append("combo_a_seed_completed")

            asr_result = run_live_voice_asr_service_benchmark(
                service_url=voice_service_url,
                manifest=asr_manifest,
                profile=profile,
                policy=policy,
                runs_dir=child_runs_root / "voice_asr",
                now=now,
            )
            tts_result = run_live_tts_service_benchmark(
                service_url=tts_service_url,
                manifest=tts_manifest,
                profile=profile,
                policy=policy,
                runs_dir=child_runs_root / "voice_tts",
                now=now,
            )
        else:
            asr_result = run_asr_backend_benchmark(
                inputs=[],
                manifest=asr_manifest,
                backends=[voice_asr_primary_backend],
                primary_backend=voice_asr_primary_backend,
                profile=profile,
                policy=policy,
                runs_dir=child_runs_root / "voice_asr",
                now=now,
                backend_factories=_smoke_stub_backend_factories(
                    enabled=smoke_stub_voice_asr,
                    backend_name=voice_asr_primary_backend,
                ),
            )
            if smoke_stub_voice_asr:
                warnings.append("voice_asr_smoke_stub_factory_enabled")
            tts_result = run_benchmark_tts_runtime(
                manifest=tts_manifest,
                profile=profile,
                policy=policy,
                runs_dir=child_runs_root / "voice_tts",
                now=now,
            )

        voice_asr_summary_path = Path(str(asr_result["run_payload"]["paths"]["service_sla_summary_json"]))
        services["voice_asr"] = _load_required_summary(voice_asr_summary_path)
        child_paths["voice_asr"] = {
            "run_dir": str(asr_result["run_dir"]),
            "run_json": str(asr_result["run_dir"] / "run.json"),
            "summary_json": str(voice_asr_summary_path),
        }

        voice_tts_summary_path = Path(str(tts_result["run_payload"]["paths"]["service_sla_summary_json"]))
        services["voice_tts"] = _load_required_summary(voice_tts_summary_path)
        child_paths["voice_tts"] = {
            "run_dir": str(tts_result["run_dir"]),
            "run_json": str(tts_result["run_dir"] / "run.json"),
            "summary_json": str(voice_tts_summary_path),
        }

        if profile == COMBO_A_PROFILE:
            assert combo_a_seed_result is not None
            retrieval_result = run_eval_retrieval(
                backend="qdrant",
                docs_path=retrieval_docs_path,
                eval_path=retrieval_eval_path,
                topk=3,
                candidate_k=10,
                reranker="none",
                collection=combo_a_seed_result["summary_payload"]["qdrant"]["collection"],
                host=qdrant_host,
                port=qdrant_port,
                vector_size=combo_a_seed_result["summary_payload"]["qdrant"]["vector_size"],
                runs_dir=child_runs_root / "retrieval",
                profile=profile,
                policy=policy,
                now=now,
            )
        else:
            retrieval_result = run_eval_retrieval(
                backend="in_memory",
                docs_path=retrieval_docs_path,
                eval_path=retrieval_eval_path,
                topk=3,
                candidate_k=10,
                reranker="none",
                runs_dir=child_runs_root / "retrieval",
                profile=profile,
                policy=policy,
                now=now,
            )
        retrieval_summary_path = Path(
            str(retrieval_result["run_payload"]["paths"]["service_sla_summary_json"])
        )
        services["retrieval"] = _load_required_summary(retrieval_summary_path)
        child_paths["retrieval"] = {
            "run_dir": str(retrieval_result["run_dir"]),
            "run_json": str(retrieval_result["run_dir"] / "run.json"),
            "summary_json": str(retrieval_summary_path),
        }

        if profile == COMBO_A_PROFILE:
            assert combo_a_seed_result is not None
            kag_result = run_eval_kag_neo4j(
                eval_path=kag_eval_path,
                topk=5,
                neo4j_url=neo4j_url,
                neo4j_database=neo4j_database,
                neo4j_user=neo4j_user,
                neo4j_password=neo4j_password,
                neo4j_dataset_tag=combo_a_seed_result["summary_payload"]["neo4j"]["dataset_tag"],
                runs_dir=child_runs_root / "kag_neo4j",
                profile=profile,
                policy=policy,
                now=now,
            )
            kag_service_key = "kag_neo4j"
        else:
            kag_result = run_eval_kag_file(
                docs_path=kag_docs_path,
                eval_path=kag_eval_path,
                topk=5,
                max_entities_per_doc=128,
                runs_dir=child_runs_root / "kag_file",
                profile=profile,
                policy=policy,
                now=now,
            )
            kag_service_key = "kag_file"
        kag_summary_path = Path(
            str(kag_result["run_payload"]["paths"]["service_sla_summary_json"])
        )
        services[kag_service_key] = _load_required_summary(kag_summary_path)
        child_paths[kag_service_key] = {
            "run_dir": str(kag_result["run_dir"]),
            "run_json": str(kag_result["run_dir"] / "run.json"),
            "summary_json": str(kag_summary_path),
        }

        degraded = build_degraded_services(services)
        summary_matrix = [
            build_suite_summary_row(source=source, summary=summary)
            for source, summary in services.items()
        ]
        suite_payload = {
            "schema_version": CROSS_SERVICE_BENCHMARK_SUITE_SCHEMA,
            "checked_at_utc": _utc_now(),
            "profile": profile,
            "policy": policy,
            "status": "ok",
            "overall_sla_status": "pass" if not degraded else "breach",
            "services": services,
            "summary_matrix": summary_matrix,
            "degraded_services": degraded,
            "warnings": warnings,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(suite_summary_out_path),
                "history_summary_json": str(suite_summary_history_path),
                "summary_md": str(summary_md_path),
                "child_runs_root": str(child_runs_root),
                "child_runs": child_paths,
                "combo_a_seed_run_dir": (
                    None if combo_a_seed_result is None else str(combo_a_seed_result["run_dir"])
                ),
            },
        }
        _write_json(suite_summary_history_path, suite_payload)
        if suite_summary_out_path != suite_summary_history_path:
            _write_json(suite_summary_out_path, suite_payload)
        _write_summary_md(summary_md_path, suite_payload=suite_payload)
        run_payload["status"] = "ok"
        run_payload["result"] = {
            "service_count": len(services),
            "degraded_service_count": len(degraded),
            "overall_sla_status": suite_payload["overall_sla_status"],
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": suite_payload,
        }
    except Exception as exc:
        suite_payload = {
            "schema_version": CROSS_SERVICE_BENCHMARK_SUITE_SCHEMA,
            "checked_at_utc": _utc_now(),
            "profile": profile,
            "policy": policy,
            "status": "error",
            "overall_sla_status": "breach",
            "services": services,
            "summary_matrix": [
                build_suite_summary_row(source=source, summary=summary)
                for source, summary in services.items()
            ],
            "degraded_services": sorted(set(list(services.keys()) + ["suite_orchestration"])),
            "warnings": warnings,
            "error": str(exc),
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(suite_summary_out_path),
                "history_summary_json": str(suite_summary_history_path),
                "summary_md": str(summary_md_path),
                "child_runs_root": str(child_runs_root),
                "child_runs": child_paths,
            },
        }
        _write_json(suite_summary_history_path, suite_payload)
        if suite_summary_out_path != suite_summary_history_path:
            _write_json(suite_summary_out_path, suite_payload)
        _write_summary_md(summary_md_path, suite_payload=suite_payload)
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": suite_payload,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the baseline-first cross-service SLA benchmark suite.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional output path for canonical machine-readable suite summary.",
    )
    parser.add_argument(
        "--profile",
        choices=(DEFAULT_PROFILE, COMBO_A_PROFILE),
        default=DEFAULT_PROFILE,
        help="Suite profile label: baseline_first (default) or combo_a.",
    )
    parser.add_argument(
        "--policy",
        choices=("signal_only", "fail_on_breach"),
        default="signal_only",
        help="Normalized SLA policy label (default: signal_only).",
    )
    parser.add_argument(
        "--voice-asr-primary-backend",
        choices=("whisper_genai", "qwen_asr"),
        default="whisper_genai",
        help="Primary ASR backend for suite benchmark (default: whisper_genai).",
    )
    parser.add_argument(
        "--smoke-stub-voice-asr",
        action="store_true",
        help="Use a synthetic in-process ASR stub for reproducible smoke paths.",
    )
    parser.add_argument(
        "--tts-manifest",
        type=Path,
        default=Path("tests") / "fixtures" / "tts_benchmark_sample.jsonl",
        help="JSONL manifest for in-process TTS benchmark.",
    )
    parser.add_argument(
        "--retrieval-docs",
        type=Path,
        default=Path("tests") / "fixtures" / "retrieval_docs_sample.jsonl",
        help="Docs fixture for retrieval eval.",
    )
    parser.add_argument(
        "--retrieval-eval",
        type=Path,
        default=Path("tests") / "fixtures" / "retrieval_eval_sample.jsonl",
        help="Eval fixture for retrieval eval.",
    )
    parser.add_argument(
        "--kag-docs",
        type=Path,
        default=Path("tests") / "fixtures" / "kag_neo4j_docs_sample.jsonl",
        help="Docs fixture for file-backed KAG eval.",
    )
    parser.add_argument(
        "--kag-eval",
        type=Path,
        default=Path("tests") / "fixtures" / "kag_neo4j_eval_sample.jsonl",
        help="Eval fixture for file-backed KAG eval.",
    )
    parser.add_argument("--voice-service-url", default="http://127.0.0.1:8765", help="Voice runtime service URL.")
    parser.add_argument("--tts-service-url", default="http://127.0.0.1:8780", help="TTS runtime service URL.")
    parser.add_argument("--qdrant-url", default=DEFAULT_COMBO_A_QDRANT_URL, help="Combo A Qdrant URL.")
    parser.add_argument("--neo4j-url", default=DEFAULT_COMBO_A_NEO4J_URL, help="Combo A Neo4j URL.")
    parser.add_argument(
        "--neo4j-database",
        default=DEFAULT_COMBO_A_NEO4J_DATABASE,
        help="Combo A Neo4j database name.",
    )
    parser.add_argument(
        "--neo4j-user",
        default=DEFAULT_COMBO_A_NEO4J_USER,
        help="Combo A Neo4j user.",
    )
    parser.add_argument(
        "--neo4j-password",
        default=None,
        help="Combo A Neo4j password (or use NEO4J_PASSWORD env var).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_cross_service_benchmark_suite(
        profile=args.profile,
        policy=args.policy,
        voice_asr_primary_backend=args.voice_asr_primary_backend,
        smoke_stub_voice_asr=bool(args.smoke_stub_voice_asr),
        tts_manifest=args.tts_manifest,
        retrieval_docs_path=args.retrieval_docs,
        retrieval_eval_path=args.retrieval_eval,
        kag_docs_path=args.kag_docs,
        kag_eval_path=args.kag_eval,
        voice_service_url=args.voice_service_url,
        tts_service_url=args.tts_service_url,
        qdrant_url=args.qdrant_url,
        neo4j_url=args.neo4j_url,
        neo4j_database=args.neo4j_database,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        runs_dir=args.runs_dir,
        summary_json=args.summary_json,
    )
    run_dir = result["run_dir"]
    summary_payload = result["summary_payload"]
    print(f"[cross_service_benchmark_suite] run_dir: {run_dir}")
    print(f"[cross_service_benchmark_suite] run_json: {run_dir / 'run.json'}")
    print(f"[cross_service_benchmark_suite] summary_json: {summary_payload['paths']['summary_json']}")
    print(f"[cross_service_benchmark_suite] summary_md: {run_dir / 'summary.md'}")
    print(f"[cross_service_benchmark_suite] status: {summary_payload['status']}")
    print(f"[cross_service_benchmark_suite] overall_sla_status: {summary_payload['overall_sla_status']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
