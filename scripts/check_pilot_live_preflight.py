from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.operator_product_snapshot import PILOT_RUNTIME_STATUS_SCHEMA, load_json_object
from scripts.pilot_runtime_loop import (
    DEFAULT_PILOT_ASR_LANGUAGE,
    DEFAULT_PILOT_SAMPLE_RATE,
    PushToTalkRecorder,
    _evaluate_transcript_quality,
    _prepare_asr_audio_input,
    call_voice_asr,
)

SCHEMA_VERSION = "pilot_live_preflight_v1"
PRECHECK_ROOT_SUBDIR = "pilot-live-preflight"
SUMMARY_FILENAME = "summary.json"
SUMMARY_MD_FILENAME = "summary.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _create_run_dir(root: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-pilot-live-preflight")
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


def _request_json(
    *,
    url: str,
    timeout_sec: float,
    service_token: str | None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if isinstance(service_token, str) and service_token.strip():
        headers["X-ATM10-Token"] = service_token.strip()
    req = Request(url=url, method="GET", headers=headers)
    try:
        with urlopen(req, timeout=max(0.2, float(timeout_sec))) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            if not isinstance(parsed, dict):
                raise RuntimeError(f"Expected JSON object from {url}.")
            return parsed
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"connection failed: {reason}") from exc


def _normalize_url(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    return value.rstrip("/")


def _resolve_service_urls(
    *,
    pilot_status: Mapping[str, Any] | None,
    gateway_url: str | None,
    voice_runtime_url: str | None,
    tts_runtime_url: str | None,
) -> dict[str, str]:
    effective_config = pilot_status.get("effective_config", {}) if isinstance(pilot_status, Mapping) else {}
    effective_config = effective_config if isinstance(effective_config, Mapping) else {}
    resolved_gateway = _normalize_url(gateway_url) or _normalize_url(effective_config.get("gateway_url")) or "http://127.0.0.1:8770"
    resolved_voice = _normalize_url(voice_runtime_url) or _normalize_url(effective_config.get("voice_runtime_url")) or "http://127.0.0.1:8765"
    resolved_tts = _normalize_url(tts_runtime_url) or _normalize_url(effective_config.get("tts_runtime_url")) or "http://127.0.0.1:8780"
    return {
        "gateway_url": resolved_gateway,
        "voice_runtime_url": resolved_voice,
        "tts_runtime_url": resolved_tts,
    }


def _probe_http_health(
    *,
    url: str,
    timeout_sec: float,
    service_token: str | None,
    request_json_func: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        payload = request_json_func(url=url, timeout_sec=timeout_sec, service_token=service_token)
        return {
            "status": "ok",
            "url": url,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "payload": payload,
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "error",
            "url": url,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "payload": None,
            "error": str(exc),
        }


def _provider_status(provider_init: Mapping[str, Any], key: str) -> dict[str, Any]:
    row = provider_init.get(key, {})
    row = row if isinstance(row, Mapping) else {}
    warmup = row.get("warmup", {})
    warmup = warmup if isinstance(warmup, Mapping) else {}
    return {
        "status": str(row.get("status", "missing")),
        "provider": row.get("provider"),
        "device": row.get("device"),
        "warmup_ok": bool(warmup.get("ok")),
        "warmup_latency_sec": warmup.get("latency_sec"),
    }


def _run_microphone_probe(
    *,
    run_dir: Path,
    voice_runtime_url: str,
    pilot_status: Mapping[str, Any] | None,
    mic_probe_seconds: float,
    mic_probe_language: str | None,
    service_token: str | None,
    sleep_func: Callable[[float], None],
    recorder_factory: Callable[..., Any],
    asr_func: Callable[..., dict[str, Any]],
    prepare_audio_func: Callable[..., dict[str, Any]],
    transcript_quality_func: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    effective_config = pilot_status.get("effective_config", {}) if isinstance(pilot_status, Mapping) else {}
    effective_config = effective_config if isinstance(effective_config, Mapping) else {}
    preferred_input_device_index = effective_config.get("input_device_index")
    if not isinstance(preferred_input_device_index, int):
        preferred_input_device_index = None

    recorder = recorder_factory(
        sample_rate=DEFAULT_PILOT_SAMPLE_RATE,
        preferred_input_device_index=preferred_input_device_index,
    )
    audio_path = run_dir / "mic_probe.wav"
    started = time.perf_counter()
    start_meta: dict[str, Any] | None = None
    stop_meta: dict[str, Any] | None = None
    prepared_audio: dict[str, Any] | None = None
    asr_payload: dict[str, Any] | None = None
    transcript_quality: dict[str, Any] | None = None
    try:
        start_meta = recorder.start()
        sleep_func(max(0.2, float(mic_probe_seconds)))
        stop_meta = recorder.stop_to_wav(output_path=audio_path)
        prepared_audio = prepare_audio_func(audio_path=audio_path, turn_dir=run_dir / "tmp")
        prepared_audio_path = Path(prepared_audio["audio_path"])
        asr_payload = asr_func(
            voice_runtime_url=voice_runtime_url,
            audio_path=prepared_audio_path,
            language=mic_probe_language,
            service_token=service_token,
        )
        transcript = str(asr_payload.get("text", ""))
        transcript_quality = transcript_quality_func(
            transcript=transcript,
            transcript_language=asr_payload.get("language"),
            expected_language=mic_probe_language,
            audio_signal=prepared_audio.get("signal"),
        )
        status = "ok" if transcript_quality.get("status") == "ok" else "error"
        return {
            "status": status,
            "duration_sec": round(time.perf_counter() - started, 6),
            "mic_probe_seconds": float(mic_probe_seconds),
            "start": start_meta,
            "audio": stop_meta,
            "prepared_audio": {
                "audio_path": str(prepared_audio_path),
                "signal": prepared_audio.get("signal"),
                "asr_preprocess": prepared_audio.get("asr_preprocess"),
            },
            "asr": {
                "text": asr_payload.get("text"),
                "language": asr_payload.get("language"),
            },
            "transcript_quality": transcript_quality,
            "error": None,
        }
    except Exception as exc:
        try:
            recorder.discard()
        except Exception:
            pass
        return {
            "status": "error",
            "duration_sec": round(time.perf_counter() - started, 6),
            "mic_probe_seconds": float(mic_probe_seconds),
            "start": start_meta,
            "audio": stop_meta,
            "prepared_audio": prepared_audio,
            "asr": asr_payload,
            "transcript_quality": transcript_quality,
            "error": str(exc),
        }


def _render_summary_md(summary_payload: Mapping[str, Any]) -> str:
    checks = summary_payload.get("checks", {})
    checks = checks if isinstance(checks, Mapping) else {}
    lines = [
        "# Pilot Live Preflight Summary",
        "",
        f"- `status`: {summary_payload.get('status')}",
        f"- `readiness_status`: {summary_payload.get('readiness_status')}",
        f"- `next_step_code`: {summary_payload.get('next_step_code')}",
        f"- `actionable_message`: {summary_payload.get('actionable_message')}",
        "",
        "| check | status | detail |",
        "|---|---|---|",
    ]
    for key in (
        "pilot_runtime_status",
        "gateway_health",
        "voice_health",
        "tts_health",
        "provider_vlm",
        "provider_text",
        "microphone_probe",
    ):
        row = checks.get(key, {})
        row = row if isinstance(row, Mapping) else {}
        detail = row.get("error") or row.get("note") or row.get("url") or "-"
        lines.append(f"| {key} | {row.get('status', '-')} | {detail} |")
    return "\n".join(lines) + "\n"


def run_check_pilot_live_preflight(
    *,
    runs_dir: Path = Path("runs"),
    summary_json: Path | None = None,
    summary_md: Path | None = None,
    pilot_status_json: Path | None = None,
    gateway_url: str | None = None,
    voice_runtime_url: str | None = None,
    tts_runtime_url: str | None = None,
    timeout_sec: float = 8.0,
    mic_probe_seconds: float = 2.0,
    mic_probe_language: str | None = DEFAULT_PILOT_ASR_LANGUAGE,
    skip_mic_probe: bool = False,
    service_token: str | None = None,
    now: datetime | None = None,
    request_json_func: Callable[..., dict[str, Any]] = _request_json,
    sleep_func: Callable[[float], None] = time.sleep,
    recorder_factory: Callable[..., Any] = PushToTalkRecorder,
    asr_func: Callable[..., dict[str, Any]] = call_voice_asr,
    prepare_audio_func: Callable[..., dict[str, Any]] = _prepare_asr_audio_input,
    transcript_quality_func: Callable[..., dict[str, Any]] = _evaluate_transcript_quality,
) -> dict[str, Any]:
    effective_now = now or datetime.now(timezone.utc)
    runs_dir = Path(runs_dir)
    preflight_root = runs_dir / PRECHECK_ROOT_SUBDIR
    run_dir = _create_run_dir(preflight_root, effective_now)

    summary_json_path = Path(summary_json) if summary_json is not None else preflight_root / SUMMARY_FILENAME
    summary_md_path = Path(summary_md) if summary_md is not None else preflight_root / SUMMARY_MD_FILENAME
    pilot_status_json_path = (
        Path(pilot_status_json)
        if pilot_status_json is not None
        else Path(runs_dir) / "pilot-runtime" / "pilot_runtime_status_latest.json"
    )

    blocking_reason_codes: list[str] = []
    attention_reason_codes: list[str] = []
    checks: dict[str, Any] = {}

    pilot_status_payload, pilot_status_error = load_json_object(pilot_status_json_path)
    if pilot_status_payload is None:
        checks["pilot_runtime_status"] = {
            "status": "error",
            "path": str(pilot_status_json_path),
            "error": pilot_status_error or "missing pilot runtime status",
        }
        blocking_reason_codes.append("pilot_status_missing")
        pilot_status_payload = {}
    elif str(pilot_status_payload.get("schema_version", "")).strip() != PILOT_RUNTIME_STATUS_SCHEMA:
        checks["pilot_runtime_status"] = {
            "status": "error",
            "path": str(pilot_status_json_path),
            "error": (
                f"invalid schema_version={pilot_status_payload.get('schema_version')!r} "
                f"(expected {PILOT_RUNTIME_STATUS_SCHEMA!r})"
            ),
        }
        blocking_reason_codes.append("pilot_status_invalid")
    else:
        runtime_status = str(pilot_status_payload.get("status", "")).strip().lower()
        runtime_state = str(pilot_status_payload.get("state", "")).strip().lower()
        checks["pilot_runtime_status"] = {
            "status": "ok" if runtime_status == "running" else "error",
            "path": str(pilot_status_json_path),
            "runtime_status": runtime_status or None,
            "runtime_state": runtime_state or None,
            "run_dir": pilot_status_payload.get("paths", {}).get("run_dir")
            if isinstance(pilot_status_payload.get("paths"), Mapping)
            else None,
            "error": None if runtime_status == "running" else f"pilot runtime status is {runtime_status or 'unknown'}",
        }
        if runtime_status != "running":
            blocking_reason_codes.append("pilot_not_running")

    resolved_urls = _resolve_service_urls(
        pilot_status=pilot_status_payload if isinstance(pilot_status_payload, Mapping) else None,
        gateway_url=gateway_url,
        voice_runtime_url=voice_runtime_url,
        tts_runtime_url=tts_runtime_url,
    )

    gateway_probe = _probe_http_health(
        url=f"{resolved_urls['gateway_url']}/healthz",
        timeout_sec=timeout_sec,
        service_token=service_token,
        request_json_func=request_json_func,
    )
    checks["gateway_health"] = gateway_probe
    if gateway_probe["status"] != "ok":
        blocking_reason_codes.append("gateway_unreachable")

    voice_probe = _probe_http_health(
        url=f"{resolved_urls['voice_runtime_url']}/health",
        timeout_sec=timeout_sec,
        service_token=service_token,
        request_json_func=request_json_func,
    )
    checks["voice_health"] = voice_probe
    if voice_probe["status"] != "ok":
        blocking_reason_codes.append("voice_runtime_unreachable")

    tts_probe = _probe_http_health(
        url=f"{resolved_urls['tts_runtime_url']}/health",
        timeout_sec=timeout_sec,
        service_token=service_token,
        request_json_func=request_json_func,
    )
    checks["tts_health"] = tts_probe
    if tts_probe["status"] != "ok":
        blocking_reason_codes.append("tts_runtime_unreachable")
    else:
        tts_payload = tts_probe.get("payload", {})
        tts_payload = tts_payload if isinstance(tts_payload, Mapping) else {}
        piper_ok = bool(
            isinstance(tts_payload.get("engines"), Mapping)
            and isinstance(tts_payload.get("engines", {}).get("piper"), Mapping)
            and tts_payload.get("engines", {}).get("piper", {}).get("ok")
        )
        if not piper_ok:
            attention_reason_codes.append("tts_piper_unavailable")

    provider_init = pilot_status_payload.get("provider_init", {}) if isinstance(pilot_status_payload, Mapping) else {}
    provider_init = provider_init if isinstance(provider_init, Mapping) else {}
    provider_vlm = _provider_status(provider_init, "vlm")
    provider_text = _provider_status(provider_init, "text")
    checks["provider_vlm"] = provider_vlm
    checks["provider_text"] = provider_text
    if provider_vlm["status"] != "ok":
        blocking_reason_codes.append("vlm_provider_not_ready")
    if provider_text["status"] != "ok":
        blocking_reason_codes.append("text_provider_not_ready")

    if skip_mic_probe:
        checks["microphone_probe"] = {
            "status": "skipped",
            "note": "microphone probe skipped by --skip-mic-probe",
        }
        attention_reason_codes.append("microphone_probe_skipped")
    else:
        mic_probe = _run_microphone_probe(
            run_dir=run_dir,
            voice_runtime_url=resolved_urls["voice_runtime_url"],
            pilot_status=pilot_status_payload if isinstance(pilot_status_payload, Mapping) else None,
            mic_probe_seconds=mic_probe_seconds,
            mic_probe_language=mic_probe_language,
            service_token=service_token,
            sleep_func=sleep_func,
            recorder_factory=recorder_factory,
            asr_func=asr_func,
            prepare_audio_func=prepare_audio_func,
            transcript_quality_func=transcript_quality_func,
        )
        checks["microphone_probe"] = mic_probe
        if mic_probe.get("status") != "ok":
            blocking_reason_codes.append("microphone_probe_failed")

    readiness_status = "ready"
    if blocking_reason_codes:
        readiness_status = "blocked"
    elif attention_reason_codes:
        readiness_status = "attention"

    if readiness_status == "ready":
        next_step_code = "run_live_f8_turn"
        actionable_message = "Preflight passed. You can launch ATM10 and run one live F8 turn."
    elif readiness_status == "attention":
        next_step_code = "review_preflight_warnings"
        actionable_message = "Preflight is mostly healthy, but review attention warnings before running ATM10."
    else:
        primary = blocking_reason_codes[0] if blocking_reason_codes else "preflight_blocked"
        mapping = {
            "pilot_status_missing": "start_pilot_runtime",
            "pilot_status_invalid": "repair_pilot_status_contract",
            "pilot_not_running": "relaunch_pilot_runtime",
            "gateway_unreachable": "start_gateway_service",
            "voice_runtime_unreachable": "start_voice_runtime",
            "tts_runtime_unreachable": "start_tts_runtime",
            "vlm_provider_not_ready": "repair_vlm_provider_init",
            "text_provider_not_ready": "repair_text_provider_init",
            "microphone_probe_failed": "fix_microphone_capture",
        }
        next_step_code = mapping.get(primary, "inspect_pilot_live_preflight")
        actionable_message = (
            "Preflight blocked before ATM10 run. Resolve the first blocking reason and rerun this check."
        )

    summary_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": effective_now.astimezone(timezone.utc).isoformat(),
        "status": "ok",
        "readiness_status": readiness_status,
        "next_step_code": next_step_code,
        "actionable_message": actionable_message,
        "blocking_reason_codes": blocking_reason_codes,
        "attention_reason_codes": attention_reason_codes,
        "checks": checks,
        "resolved_urls": resolved_urls,
        "paths": {
            "run_dir": str(run_dir),
            "summary_json": str(summary_json_path),
            "summary_md": str(summary_md_path),
            "pilot_status_json": str(pilot_status_json_path),
        },
        "checked_at_utc": _utc_now(),
    }
    _write_json(run_dir / "summary.json", summary_payload)
    _write_json(summary_json_path, summary_payload)
    _write_text(summary_md_path, _render_summary_md(summary_payload))
    _write_text(run_dir / "summary.md", _render_summary_md(summary_payload))

    return {
        "summary_payload": summary_payload,
        "summary_json_path": summary_json_path,
        "summary_md_path": summary_md_path,
        "run_dir": run_dir,
        "exit_code": 0,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preflight checks for pilot live stack before launching ATM10."
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Base runs directory.")
    parser.add_argument("--summary-json", type=Path, default=None, help="Optional summary JSON output path.")
    parser.add_argument("--summary-md", type=Path, default=None, help="Optional summary Markdown output path.")
    parser.add_argument(
        "--pilot-status-json",
        type=Path,
        default=None,
        help="Optional explicit pilot runtime status JSON path.",
    )
    parser.add_argument("--gateway-url", type=str, default=None, help="Optional gateway URL override.")
    parser.add_argument("--voice-runtime-url", type=str, default=None, help="Optional voice runtime URL override.")
    parser.add_argument("--tts-runtime-url", type=str, default=None, help="Optional TTS runtime URL override.")
    parser.add_argument("--timeout-sec", type=float, default=8.0, help="Health probe timeout in seconds.")
    parser.add_argument(
        "--mic-probe-seconds",
        type=float,
        default=2.0,
        help="Microphone capture duration for ASR preflight probe.",
    )
    parser.add_argument(
        "--mic-probe-language",
        type=str,
        default=DEFAULT_PILOT_ASR_LANGUAGE,
        help=f"Language hint for microphone ASR probe (default: {DEFAULT_PILOT_ASR_LANGUAGE}).",
    )
    parser.add_argument(
        "--skip-mic-probe",
        action="store_true",
        help="Skip microphone ASR probe (faster but does not validate speech capture).",
    )
    parser.add_argument(
        "--service-token",
        type=str,
        default=None,
        help="Optional service token for local runtime endpoints (fallback: ATM10_SERVICE_TOKEN).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    service_token = args.service_token or os.getenv("ATM10_SERVICE_TOKEN")
    result = run_check_pilot_live_preflight(
        runs_dir=args.runs_dir,
        summary_json=args.summary_json,
        summary_md=args.summary_md,
        pilot_status_json=args.pilot_status_json,
        gateway_url=args.gateway_url,
        voice_runtime_url=args.voice_runtime_url,
        tts_runtime_url=args.tts_runtime_url,
        timeout_sec=float(args.timeout_sec),
        mic_probe_seconds=float(args.mic_probe_seconds),
        mic_probe_language=args.mic_probe_language,
        skip_mic_probe=bool(args.skip_mic_probe),
        service_token=service_token,
    )
    summary = result["summary_payload"]
    print(f"[check_pilot_live_preflight] status: {summary.get('status')}")
    print(f"[check_pilot_live_preflight] readiness_status: {summary.get('readiness_status')}")
    print(f"[check_pilot_live_preflight] next_step_code: {summary.get('next_step_code')}")
    return int(result.get("exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
