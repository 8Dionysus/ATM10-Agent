from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.operator_product_snapshot import (  # noqa: E402
    OPERATOR_PRODUCT_STARTUP_SCHEMA,
    PILOT_RUNTIME_STATUS_FILENAME,
    PILOT_RUNTIME_STATUS_SCHEMA,
    PILOT_TURN_SCHEMA,
    load_json_object,
    load_latest_operator_startup_status,
)
from src.agent_core.atm10_session_probe import ATM10_SESSION_PROBE_SCHEMA  # noqa: E402
from src.agent_core.combo_a_profile import COMBO_A_PROFILE  # noqa: E402
from src.agent_core.live_hud_state import LIVE_HUD_STATE_SCHEMA  # noqa: E402

SCHEMA_VERSION = "pilot_runtime_readiness_v1"
READINESS_ROOT_SUBDIR = "pilot-runtime-readiness"
READINESS_SUMMARY_FILENAME = "readiness_summary.json"
FRESHNESS_WINDOW = timedelta(hours=2)
LIVE_AUDIO_MODE = "push_to_talk_recorded_microphone"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _create_run_dir(root: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-pilot-runtime-readiness")
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


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _timestamp_from_mapping(payload: Mapping[str, Any], *keys: str) -> datetime | None:
    observed: list[datetime] = []
    for key in keys:
        parsed = _parse_iso_datetime(payload.get(key))
        if parsed is not None:
            observed.append(parsed)
    if not observed:
        return None
    return max(observed)


def _is_fresh(timestamp: datetime | None, *, now: datetime) -> bool:
    if timestamp is None:
        return False
    return now - timestamp <= FRESHNESS_WINDOW


def _coalesce_pilot_runs_dir(startup_snapshot: Mapping[str, Any] | None, runs_dir: Path) -> Path:
    pilot_runs_dir_value = None if startup_snapshot is None else startup_snapshot.get("artifact_roots", {})
    if not isinstance(pilot_runs_dir_value, Mapping):
        pilot_runs_dir_value = {}
    candidate = pilot_runs_dir_value.get("pilot_runtime_runs_dir")
    if not isinstance(candidate, str) or not candidate.strip():
        session_state = None if startup_snapshot is None else startup_snapshot.get("session_state", {})
        session_state = session_state if isinstance(session_state, Mapping) else {}
        pilot_runtime = session_state.get("pilot_runtime", {})
        pilot_runtime = pilot_runtime if isinstance(pilot_runtime, Mapping) else {}
        candidate = pilot_runtime.get("runs_dir")
    if isinstance(candidate, str) and candidate.strip():
        return Path(candidate)
    return Path(runs_dir) / "pilot-runtime"


def _pilot_runtime_configured(startup_snapshot: Mapping[str, Any] | None) -> bool:
    if not isinstance(startup_snapshot, Mapping):
        return False
    session_state = startup_snapshot.get("session_state", {})
    session_state = session_state if isinstance(session_state, Mapping) else {}
    pilot_runtime = session_state.get("pilot_runtime", {})
    pilot_runtime = pilot_runtime if isinstance(pilot_runtime, Mapping) else {}
    if bool(pilot_runtime.get("configured")):
        return True
    managed_processes = startup_snapshot.get("managed_processes", {})
    managed_processes = managed_processes if isinstance(managed_processes, Mapping) else {}
    pilot_plan = managed_processes.get("pilot_runtime", {})
    pilot_plan = pilot_plan if isinstance(pilot_plan, Mapping) else {}
    return bool(pilot_plan.get("configured"))


def _capture_configured(pilot_status: Mapping[str, Any] | None) -> bool:
    if not isinstance(pilot_status, Mapping):
        return False
    effective_config = pilot_status.get("effective_config", {})
    effective_config = effective_config if isinstance(effective_config, Mapping) else {}
    if effective_config.get("capture_monitor") is not None:
        return True
    capture_region = effective_config.get("capture_region")
    return isinstance(capture_region, list) and len(capture_region) == 4


def _source_entry(
    *,
    path: Path | None,
    status: str,
    timestamp: datetime | None = None,
    fresh_within_window: bool | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": None if path is None else str(path),
        "status": status,
        "freshness_window_hours": int(FRESHNESS_WINDOW.total_seconds() // 3600),
    }
    if timestamp is not None:
        payload["checked_at_utc"] = timestamp.isoformat()
    if fresh_within_window is not None:
        payload["fresh_within_window"] = bool(fresh_within_window)
    return payload


def _reason_to_next_step(reason_code: str) -> tuple[str, str]:
    mapping = {
        "startup_artifact_missing": (
            "launch_operator_product",
            "Launch the operator product so it publishes a fresh startup artifact.",
        ),
        "startup_artifact_invalid": (
            "inspect_startup_artifact",
            "Inspect the latest startup artifact and fix the invalid contract before rerunning the operator product.",
        ),
        "startup_artifact_stale": (
            "relaunch_operator_product",
            "Relaunch the operator product so the startup evidence is fresh within the acceptance window.",
        ),
        "pilot_runtime_not_configured": (
            "enable_pilot_runtime",
            "Relaunch the operator product with pilot runtime enabled so acceptance can observe it.",
        ),
        "pilot_status_missing": (
            "start_pilot_runtime",
            "Start the pilot runtime and wait for `pilot_runtime_status_latest.json` to appear.",
        ),
        "pilot_status_invalid": (
            "repair_pilot_status_contract",
            "Repair the pilot runtime status artifact so the readiness checker can load it.",
        ),
        "capture_not_configured": (
            "configure_capture",
            "Relaunch the pilot runtime with `--capture-monitor` or `--capture-region` configured.",
        ),
        "pilot_session_probe_missing": (
            "complete_live_pilot_turn",
            "Complete one live push-to-talk turn so the pilot publishes ATM10 session evidence.",
        ),
        "pilot_session_probe_invalid": (
            "repair_session_probe_contract",
            "Repair the ATM10 session probe artifact so the readiness checker can load it.",
        ),
        "pilot_session_window_not_found": (
            "focus_atm10_window",
            "Bring the ATM10 game window on screen and complete another live push-to-talk turn.",
        ),
        "pilot_session_not_atm10_probable": (
            "retarget_atm10_capture",
            "Retarget capture to the ATM10 game window or monitor, then complete another live turn.",
        ),
        "pilot_session_not_foreground": (
            "focus_atm10_window",
            "Focus the ATM10 game window before running another live push-to-talk turn.",
        ),
        "pilot_hud_state_missing": (
            "complete_live_pilot_turn",
            "Complete another live push-to-talk turn so the pilot publishes a fresh live_hud_state artifact.",
        ),
        "pilot_hud_state_invalid": (
            "repair_live_hud_state_contract",
            "Repair the live_hud_state artifact so the readiness checker can load it.",
        ),
        "pilot_hud_state_error": (
            "inspect_live_hud_state",
            "Inspect the latest live_hud_state artifact and resolve the capture/OCR/mod-hook issue before rerunning.",
        ),
        "pilot_turn_missing": (
            "complete_live_pilot_turn",
            "Complete one live push-to-talk turn so the pilot publishes a fresh turn artifact.",
        ),
        "pilot_turn_invalid": (
            "repair_pilot_turn_contract",
            "Repair the latest pilot turn artifact so the readiness checker can load it.",
        ),
        "pilot_turn_error": (
            "inspect_last_pilot_turn",
            "Open the latest `pilot_turn.json`, fix the failing stage, and rerun one live turn.",
        ),
        "pilot_turn_not_completed": (
            "complete_live_pilot_turn",
            "Wait for the current pilot turn to complete successfully, or rerun one clean live push-to-talk turn.",
        ),
        "pilot_turn_stale": (
            "repeat_live_pilot_turn",
            "Complete another live push-to-talk turn so the acceptance evidence is fresh.",
        ),
        "pilot_turn_degraded": (
            "repeat_live_pilot_turn",
            "Resolve the degraded pilot condition, then complete another live push-to-talk turn.",
        ),
        "pilot_turn_not_live_evidence": (
            "complete_live_pilot_turn",
            "Run one real push-to-talk turn; fixture or smoke turns do not satisfy live acceptance.",
        ),
        "hybrid_profile_not_combo_a": (
            "inspect_combo_a_routing",
            "Verify the pilot runtime is grounding through `hybrid_query(profile=combo_a)`.",
        ),
        "hybrid_result_degraded": (
            "repeat_live_pilot_turn",
            "Resolve the degraded hybrid path and publish another clean live turn.",
        ),
        "pilot_session_stopped": (
            "relaunch_pilot_runtime",
            "Relaunch the pilot runtime to keep the live session available after the last good turn.",
        ),
        "pilot_session_error": (
            "repair_and_relaunch_pilot_runtime",
            "Repair the pilot runtime failure and relaunch it before trusting the last good turn as live readiness evidence.",
        ),
    }
    return mapping.get(
        reason_code,
        ("inspect_pilot_acceptance", "Inspect the pilot readiness artifacts and refresh the missing evidence."),
    )


def _build_actionable_message(readiness_status: str, reason_codes: list[str]) -> str:
    if readiness_status == "ready":
        return (
            "Pilot live acceptance is green: startup, capture, live push-to-talk evidence, "
            "and non-degraded combo_a grounding are all present."
        )
    if not reason_codes:
        return "Pilot readiness is not available yet."
    primary = reason_codes[0]
    if primary == "pilot_turn_not_live_evidence":
        return "Pilot evidence is valid, but it comes from fixture/smoke artifacts instead of a live push-to-talk turn."
    if primary == "pilot_turn_stale":
        return "Pilot acceptance evidence exists, but the latest turn is stale."
    if primary == "pilot_turn_degraded":
        return "Pilot acceptance evidence exists, but the latest turn is degraded."
    if primary == "pilot_session_window_not_found":
        return "Pilot evidence is present, but the runtime could not find an ATM10 game window."
    if primary == "pilot_session_not_atm10_probable":
        return "Pilot evidence is present, but the current capture target is not confidently ATM10."
    if primary == "pilot_session_not_foreground":
        return "Pilot evidence is present, but the ATM10 window is not in the foreground."
    if primary == "pilot_hud_state_error":
        return "Pilot evidence is present, but the live HUD extraction failed for the latest turn."
    if primary == "pilot_turn_not_completed":
        return "Pilot acceptance evidence is present, but the latest turn has not completed with status=ok yet."
    if primary == "pilot_session_stopped":
        return "Pilot acceptance evidence is recent, but the pilot session is currently stopped."
    next_step_code, next_step = _reason_to_next_step(primary)
    _ = next_step_code
    return next_step


def _render_summary_md(summary_payload: Mapping[str, Any]) -> str:
    evidence = summary_payload.get("evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    lines = [
        "# Pilot Runtime Readiness Summary",
        "",
        f"- `status`: {summary_payload.get('status')}",
        f"- `readiness_status`: {summary_payload.get('readiness_status')}",
        f"- `actionable_message`: {summary_payload.get('actionable_message')}",
        f"- `next_step_code`: {summary_payload.get('next_step_code')}",
        "",
        "| source | status | fresh_within_window |",
        "|---|---|---|",
    ]
    sources = summary_payload.get("sources")
    sources = sources if isinstance(sources, Mapping) else {}
    for source_name in ("startup", "pilot_runtime_status", "pilot_turn"):
        source = sources.get(source_name)
        source = source if isinstance(source, Mapping) else {}
        lines.append(
            "| {source} | {status} | {fresh} |".format(
                source=source_name,
                status=source.get("status", "-"),
                fresh=source.get("fresh_within_window", "-"),
            )
        )
    lines.extend(
        [
            "",
            "| evidence | value |",
            "|---|---|",
            f"| startup_fresh | {evidence.get('startup_fresh_within_window')} |",
            f"| capture_configured | {evidence.get('capture_configured')} |",
            f"| live_turn_evidence | {evidence.get('live_turn_evidence')} |",
            f"| last_turn_fresh | {evidence.get('last_turn_fresh_within_window')} |",
            f"| session_window_found | {evidence.get('session_window_found')} |",
            f"| session_atm10_probable | {evidence.get('session_atm10_probable')} |",
            f"| session_foreground | {evidence.get('session_foreground')} |",
            f"| hud_state_status | {evidence.get('hud_state_status')} |",
            f"| hybrid_profile | {evidence.get('hybrid_profile')} |",
            f"| hybrid_planner_status | {evidence.get('hybrid_planner_status')} |",
            f"| hybrid_degraded | {evidence.get('hybrid_degraded')} |",
        ]
    )
    return "\n".join(lines) + "\n"


def run_check_pilot_runtime_readiness(
    *,
    runs_dir: Path = Path("runs"),
    operator_runs_dir: Path | None = None,
    summary_json: Path | None = None,
    summary_md: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    effective_now = now or datetime.now(timezone.utc)
    readiness_root = Path(runs_dir) / READINESS_ROOT_SUBDIR
    run_dir = _create_run_dir(readiness_root, effective_now)
    run_json_path = run_dir / "run.json"
    history_summary_path = run_dir / READINESS_SUMMARY_FILENAME
    history_summary_md_path = run_dir / "summary.md"
    summary_out_path = summary_json if summary_json is not None else readiness_root / READINESS_SUMMARY_FILENAME
    summary_md_out_path = summary_md if summary_md is not None else readiness_root / "summary.md"
    effective_operator_runs_dir = Path(operator_runs_dir) if operator_runs_dir is not None else Path(runs_dir)

    run_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": effective_now.isoformat(),
        "mode": "check_pilot_runtime_readiness",
        "status": "started",
        "request": {
            "runs_dir": str(runs_dir),
            "operator_runs_dir": str(effective_operator_runs_dir),
        },
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "summary_json": str(summary_out_path),
            "history_summary_json": str(history_summary_path),
            "summary_md": str(summary_md_out_path),
            "history_summary_md": str(history_summary_md_path),
        },
    }
    _write_json(run_json_path, run_payload)

    try:
        warnings: list[str] = []
        reason_codes: list[str] = []

        startup_snapshot, startup_warnings = load_latest_operator_startup_status(effective_operator_runs_dir)
        warnings.extend(startup_warnings)
        startup_run_json_value = None if startup_snapshot is None else startup_snapshot.get("paths", {}).get("run_json")
        startup_run_json = (
            Path(str(startup_run_json_value))
            if isinstance(startup_run_json_value, str) and startup_run_json_value.strip()
            else None
        )
        startup_source_status = "present"
        if startup_snapshot is None:
            startup_source_status = "invalid" if startup_warnings else "missing"
        startup_timestamp = (
            None
            if startup_snapshot is None
            else _timestamp_from_mapping(
                startup_snapshot,
                "finished_at_utc",
                "stopped_at_utc",
                "started_at_utc",
                "timestamp_utc",
            )
        )
        startup_fresh = _is_fresh(startup_timestamp, now=effective_now)
        sources = {
            "startup": _source_entry(
                path=startup_run_json,
                status=startup_source_status,
                timestamp=startup_timestamp,
                fresh_within_window=startup_fresh if startup_snapshot is not None else None,
            )
        }

        if startup_snapshot is None:
            reason_codes.append(
                "startup_artifact_invalid" if startup_source_status == "invalid" else "startup_artifact_missing"
            )
        elif not startup_fresh:
            reason_codes.append("startup_artifact_stale")

        pilot_configured = _pilot_runtime_configured(startup_snapshot)
        if startup_snapshot is not None and not pilot_configured:
            reason_codes.append("pilot_runtime_not_configured")

        pilot_runs_dir = _coalesce_pilot_runs_dir(startup_snapshot, Path(runs_dir))
        pilot_status_path = pilot_runs_dir / PILOT_RUNTIME_STATUS_FILENAME
        pilot_status_payload, pilot_status_error = load_json_object(pilot_status_path)
        pilot_status: dict[str, Any] | None = None
        pilot_status_source_status = "present"
        if pilot_status_payload is None:
            pilot_status_source_status = "missing" if pilot_status_error and pilot_status_error.startswith("missing file:") else "invalid"
            if pilot_status_error is not None and pilot_status_source_status == "invalid":
                warnings.append(f"{pilot_status_path}: skipped ({pilot_status_error})")
        elif str(pilot_status_payload.get("schema_version", "")).strip() != PILOT_RUNTIME_STATUS_SCHEMA:
            pilot_status_source_status = "invalid"
            warnings.append(
                f"{pilot_status_path}: skipped (schema_version={pilot_status_payload.get('schema_version')!r} "
                f"expected={PILOT_RUNTIME_STATUS_SCHEMA!r})"
            )
        else:
            pilot_status = pilot_status_payload
        pilot_status_timestamp = (
            None if pilot_status is None else _timestamp_from_mapping(pilot_status, "timestamp_utc")
        )
        sources["pilot_runtime_status"] = _source_entry(
            path=pilot_status_path,
            status=pilot_status_source_status,
            timestamp=pilot_status_timestamp,
            fresh_within_window=_is_fresh(pilot_status_timestamp, now=effective_now) if pilot_status is not None else None,
        )

        if pilot_status is None:
            reason_codes.append(
                "pilot_status_invalid" if pilot_status_source_status == "invalid" else "pilot_status_missing"
            )

        capture_configured = _capture_configured(pilot_status)
        if pilot_status is not None and not capture_configured:
            reason_codes.append("capture_not_configured")

        turn_json_value = None if pilot_status is None else pilot_status.get("paths", {}).get("last_turn_json")
        turn_json_path = (
            Path(str(turn_json_value))
            if isinstance(turn_json_value, str) and turn_json_value.strip()
            else None
        )
        pilot_turn_payload: dict[str, Any] | None = None
        pilot_turn_source_status = "present"
        if turn_json_path is None:
            pilot_turn_source_status = "missing"
        else:
            loaded_turn_payload, turn_load_error = load_json_object(turn_json_path)
            if loaded_turn_payload is None:
                pilot_turn_source_status = "missing" if turn_load_error and turn_load_error.startswith("missing file:") else "invalid"
                if turn_load_error is not None and pilot_turn_source_status == "invalid":
                    warnings.append(f"{turn_json_path}: skipped ({turn_load_error})")
            elif str(loaded_turn_payload.get("schema_version", "")).strip() != PILOT_TURN_SCHEMA:
                pilot_turn_source_status = "invalid"
                warnings.append(
                    f"{turn_json_path}: skipped (schema_version={loaded_turn_payload.get('schema_version')!r} "
                    f"expected={PILOT_TURN_SCHEMA!r})"
                )
            else:
                pilot_turn_payload = loaded_turn_payload
        turn_timestamp = (
            None
            if pilot_turn_payload is None
            else _timestamp_from_mapping(pilot_turn_payload, "completed_at_utc", "timestamp_utc")
        )
        turn_fresh = _is_fresh(turn_timestamp, now=effective_now)
        sources["pilot_turn"] = _source_entry(
            path=turn_json_path,
            status=pilot_turn_source_status,
            timestamp=turn_timestamp,
            fresh_within_window=turn_fresh if pilot_turn_payload is not None else None,
        )

        if pilot_turn_payload is None:
            reason_codes.append(
                "pilot_turn_invalid" if pilot_turn_source_status == "invalid" else "pilot_turn_missing"
            )

        turn_paths_payload = None if pilot_turn_payload is None else pilot_turn_payload.get("paths", {})
        turn_paths_payload = turn_paths_payload if isinstance(turn_paths_payload, Mapping) else {}

        session_probe_json_value = turn_paths_payload.get("session_probe_json")
        session_probe_json_path = (
            Path(str(session_probe_json_value))
            if isinstance(session_probe_json_value, str) and session_probe_json_value.strip()
            else None
        )
        session_probe_payload: dict[str, Any] | None = None
        session_probe_source_status = "present"
        if session_probe_json_path is None:
            session_probe_source_status = "missing"
        else:
            loaded_session_payload, session_load_error = load_json_object(session_probe_json_path)
            if loaded_session_payload is None:
                session_probe_source_status = (
                    "missing" if session_load_error and session_load_error.startswith("missing file:") else "invalid"
                )
                if session_load_error is not None and session_probe_source_status == "invalid":
                    warnings.append(f"{session_probe_json_path}: skipped ({session_load_error})")
            elif str(loaded_session_payload.get("schema_version", "")).strip() != ATM10_SESSION_PROBE_SCHEMA:
                session_probe_source_status = "invalid"
                warnings.append(
                    f"{session_probe_json_path}: skipped (schema_version={loaded_session_payload.get('schema_version')!r} "
                    f"expected={ATM10_SESSION_PROBE_SCHEMA!r})"
                )
            else:
                session_probe_payload = loaded_session_payload
        session_probe_timestamp = (
            None
            if session_probe_payload is None
            else _timestamp_from_mapping(session_probe_payload, "checked_at_utc")
        )
        sources["session_probe"] = _source_entry(
            path=session_probe_json_path,
            status=session_probe_source_status,
            timestamp=session_probe_timestamp,
            fresh_within_window=_is_fresh(session_probe_timestamp, now=effective_now)
            if session_probe_payload is not None
            else None,
        )
        if pilot_turn_payload is not None and session_probe_payload is None:
            reason_codes.append(
                "pilot_session_probe_invalid"
                if session_probe_source_status == "invalid"
                else "pilot_session_probe_missing"
            )

        live_hud_state_json_value = turn_paths_payload.get("live_hud_state_json")
        live_hud_state_json_path = (
            Path(str(live_hud_state_json_value))
            if isinstance(live_hud_state_json_value, str) and live_hud_state_json_value.strip()
            else None
        )
        live_hud_state_payload: dict[str, Any] | None = None
        live_hud_state_source_status = "present"
        if live_hud_state_json_path is None:
            live_hud_state_source_status = "missing"
        else:
            loaded_hud_payload, hud_load_error = load_json_object(live_hud_state_json_path)
            if loaded_hud_payload is None:
                live_hud_state_source_status = (
                    "missing" if hud_load_error and hud_load_error.startswith("missing file:") else "invalid"
                )
                if hud_load_error is not None and live_hud_state_source_status == "invalid":
                    warnings.append(f"{live_hud_state_json_path}: skipped ({hud_load_error})")
            elif str(loaded_hud_payload.get("schema_version", "")).strip() != LIVE_HUD_STATE_SCHEMA:
                live_hud_state_source_status = "invalid"
                warnings.append(
                    f"{live_hud_state_json_path}: skipped (schema_version={loaded_hud_payload.get('schema_version')!r} "
                    f"expected={LIVE_HUD_STATE_SCHEMA!r})"
                )
            else:
                live_hud_state_payload = loaded_hud_payload
        live_hud_state_timestamp = (
            None
            if live_hud_state_payload is None
            else _timestamp_from_mapping(live_hud_state_payload, "checked_at_utc")
        )
        sources["live_hud_state"] = _source_entry(
            path=live_hud_state_json_path,
            status=live_hud_state_source_status,
            timestamp=live_hud_state_timestamp,
            fresh_within_window=_is_fresh(live_hud_state_timestamp, now=effective_now)
            if live_hud_state_payload is not None
            else None,
        )
        if pilot_turn_payload is not None and live_hud_state_payload is None:
            reason_codes.append(
                "pilot_hud_state_invalid"
                if live_hud_state_source_status == "invalid"
                else "pilot_hud_state_missing"
            )

        turn_status = None if pilot_turn_payload is None else str(pilot_turn_payload.get("status", "")).strip().lower()
        if turn_status == "error":
            reason_codes.append("pilot_turn_error")
        elif turn_status == "degraded":
            reason_codes.append("pilot_turn_degraded")
        elif pilot_turn_payload is not None and turn_status != "ok":
            reason_codes.append("pilot_turn_not_completed")
        elif pilot_turn_payload is not None and not turn_fresh:
            reason_codes.append("pilot_turn_stale")

        audio_payload = None if pilot_turn_payload is None else pilot_turn_payload.get("audio", {})
        audio_payload = audio_payload if isinstance(audio_payload, Mapping) else {}
        live_turn_evidence = str(audio_payload.get("mode", "")).strip() == LIVE_AUDIO_MODE
        if pilot_turn_payload is not None and not live_turn_evidence:
            reason_codes.append("pilot_turn_not_live_evidence")

        session_window_found = bool(
            session_probe_payload.get("window_found")
        ) if isinstance(session_probe_payload, Mapping) else False
        session_atm10_probable = bool(
            session_probe_payload.get("atm10_probable")
        ) if isinstance(session_probe_payload, Mapping) else False
        session_foreground = bool(
            session_probe_payload.get("foreground")
        ) if isinstance(session_probe_payload, Mapping) else False
        if pilot_turn_payload is not None and session_probe_payload is not None:
            if not session_window_found:
                reason_codes.append("pilot_session_window_not_found")
            if not session_atm10_probable:
                reason_codes.append("pilot_session_not_atm10_probable")
            if not session_foreground:
                reason_codes.append("pilot_session_not_foreground")

        hud_state_status = (
            None
            if live_hud_state_payload is None
            else str(live_hud_state_payload.get("status", "")).strip().lower()
        )
        if live_hud_state_payload is not None and hud_state_status == "error":
            reason_codes.append("pilot_hud_state_error")

        hybrid_payload = None if pilot_turn_payload is None else pilot_turn_payload.get("hybrid", {})
        hybrid_payload = hybrid_payload if isinstance(hybrid_payload, Mapping) else {}
        hybrid_profile = str(hybrid_payload.get("profile", "")).strip()
        hybrid_planner_status = str(hybrid_payload.get("planner_status", "")).strip()
        hybrid_degraded = bool(hybrid_payload.get("degraded"))
        if pilot_turn_payload is not None and hybrid_profile != COMBO_A_PROFILE:
            reason_codes.append("hybrid_profile_not_combo_a")
        elif pilot_turn_payload is not None and (
            hybrid_degraded or hybrid_planner_status == "retrieval_only_fallback"
        ):
            reason_codes.append("hybrid_result_degraded")

        startup_status = "" if startup_snapshot is None else str(startup_snapshot.get("status", "")).strip().lower()
        pilot_status_state = "" if pilot_status is None else str(pilot_status.get("status", "")).strip().lower()
        turn_is_good = bool(
            pilot_turn_payload is not None
            and turn_status == "ok"
            and turn_fresh
            and live_turn_evidence
            and session_window_found
            and session_atm10_probable
            and session_foreground
            and hud_state_status in {"ok", "partial"}
            and hybrid_profile == COMBO_A_PROFILE
            and not hybrid_degraded
            and hybrid_planner_status != "retrieval_only_fallback"
        )
        if turn_is_good and (startup_status == "stopped" or pilot_status_state == "stopped"):
            reason_codes.append("pilot_session_stopped")
        if turn_is_good and (startup_status == "error" or pilot_status_state == "error"):
            reason_codes.append("pilot_session_error")

        deduped_reason_codes = []
        seen_reason_codes: set[str] = set()
        for reason_code in reason_codes:
            normalized = str(reason_code).strip()
            if not normalized or normalized in seen_reason_codes:
                continue
            seen_reason_codes.add(normalized)
            deduped_reason_codes.append(normalized)
        reason_codes = deduped_reason_codes

        blocked_reason_codes = {
            "startup_artifact_missing",
            "startup_artifact_invalid",
            "pilot_runtime_not_configured",
            "pilot_status_missing",
            "pilot_status_invalid",
            "capture_not_configured",
            "pilot_session_probe_missing",
            "pilot_session_probe_invalid",
            "pilot_session_window_not_found",
            "pilot_session_not_atm10_probable",
            "pilot_session_not_foreground",
            "pilot_hud_state_missing",
            "pilot_hud_state_invalid",
            "pilot_hud_state_error",
            "pilot_turn_missing",
            "pilot_turn_invalid",
            "pilot_turn_error",
            "pilot_turn_not_completed",
            "hybrid_profile_not_combo_a",
            "pilot_session_error",
        }
        readiness_status = "ready"
        if any(reason_code in blocked_reason_codes for reason_code in reason_codes):
            readiness_status = "blocked"
        elif reason_codes:
            readiness_status = "attention"

        next_step_code, next_step = (
            ("none", "No action required.")
            if not reason_codes
            else _reason_to_next_step(reason_codes[0])
        )
        actionable_message = _build_actionable_message(readiness_status, reason_codes)

        summary_payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "status": "ok",
            "checked_at_utc": effective_now.isoformat(),
            "readiness_status": readiness_status,
            "actionable_message": actionable_message,
            "blocking_reason_codes": reason_codes,
            "next_step_code": next_step_code,
            "next_step": next_step,
            "sources": sources,
            "evidence": {
                "startup_status": startup_status or None,
                "startup_schema_version": OPERATOR_PRODUCT_STARTUP_SCHEMA if startup_snapshot is not None else None,
                "startup_fresh_within_window": startup_fresh if startup_snapshot is not None else False,
                "pilot_runtime_configured": pilot_configured,
                "pilot_runtime_status": pilot_status_state or None,
                "capture_configured": capture_configured,
                "last_turn_status": turn_status,
                "last_turn_fresh_within_window": turn_fresh if pilot_turn_payload is not None else False,
                "live_turn_evidence": live_turn_evidence if pilot_turn_payload is not None else False,
                "turn_audio_mode": audio_payload.get("mode"),
                "session_window_found": session_window_found if session_probe_payload is not None else False,
                "session_atm10_probable": session_atm10_probable if session_probe_payload is not None else False,
                "session_foreground": session_foreground if session_probe_payload is not None else False,
                "session_capture_target_kind": None if session_probe_payload is None else session_probe_payload.get("capture_target_kind"),
                "session_reason_codes": []
                if session_probe_payload is None
                else session_probe_payload.get("reason_codes", []),
                "hud_state_status": hud_state_status,
                "hud_line_count": None if live_hud_state_payload is None else live_hud_state_payload.get("hud_line_count"),
                "hud_has_player_state": None if live_hud_state_payload is None else live_hud_state_payload.get("has_player_state"),
                "hud_reason_codes": []
                if live_hud_state_payload is None
                else live_hud_state_payload.get("reason_codes", []),
                "hybrid_profile": hybrid_profile or None,
                "hybrid_planner_status": hybrid_planner_status or None,
                "hybrid_degraded": hybrid_degraded if pilot_turn_payload is not None else None,
            },
            "warnings": warnings,
            "error": None,
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
                "history_summary_json": str(history_summary_path),
                "summary_md": str(summary_md_out_path),
                "history_summary_md": str(history_summary_md_path),
            },
        }
        summary_text = _render_summary_md(summary_payload)
        _write_json(history_summary_path, summary_payload)
        if summary_out_path != history_summary_path:
            _write_json(summary_out_path, summary_payload)
        _write_text(history_summary_md_path, summary_text)
        if summary_md_out_path != history_summary_md_path:
            _write_text(summary_md_out_path, summary_text)

        run_payload["status"] = "ok"
        run_payload["result"] = {
            "readiness_status": readiness_status,
            "blocking_reason_codes": reason_codes,
            "next_step_code": next_step_code,
        }
        _write_json(run_json_path, run_payload)
        return {
            "ok": True,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
            "summary_text": summary_text,
            "exit_code": 0,
        }
    except Exception as exc:
        summary_payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "error",
            "checked_at_utc": effective_now.isoformat(),
            "readiness_status": "blocked",
            "actionable_message": "Pilot readiness failed before it could evaluate the current evidence.",
            "blocking_reason_codes": ["readiness_check_error"],
            "next_step_code": "inspect_readiness_checker",
            "next_step": "Inspect the readiness checker error and rerun the evaluation.",
            "sources": {},
            "evidence": {},
            "warnings": [],
            "error": str(exc),
            "paths": {
                "run_dir": str(run_dir),
                "run_json": str(run_json_path),
                "summary_json": str(summary_out_path),
                "history_summary_json": str(history_summary_path),
                "summary_md": str(summary_md_out_path),
                "history_summary_md": str(history_summary_md_path),
            },
        }
        summary_text = _render_summary_md(summary_payload)
        _write_json(history_summary_path, summary_payload)
        if summary_out_path != history_summary_path:
            _write_json(summary_out_path, summary_payload)
        _write_text(history_summary_md_path, summary_text)
        if summary_md_out_path != history_summary_md_path:
            _write_text(summary_md_out_path, summary_text)
        run_payload["status"] = "error"
        run_payload["error"] = str(exc)
        _write_json(run_json_path, run_payload)
        return {
            "ok": False,
            "run_dir": run_dir,
            "run_payload": run_payload,
            "summary_payload": summary_payload,
            "summary_text": summary_text,
            "exit_code": 2,
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate observer pilot live-readiness from published artifacts.")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Run artifact base directory.")
    parser.add_argument(
        "--operator-runs-dir",
        type=Path,
        default=None,
        help="Optional operator startup artifact root. Defaults to --runs-dir.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional output path for the canonical readiness summary.",
    )
    parser.add_argument(
        "--summary-md",
        type=Path,
        default=None,
        help="Optional output path for the human-readable readiness summary.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_check_pilot_runtime_readiness(
        runs_dir=args.runs_dir,
        operator_runs_dir=args.operator_runs_dir,
        summary_json=args.summary_json,
        summary_md=args.summary_md,
    )
    summary_payload = result["summary_payload"]
    print(f"[check_pilot_runtime_readiness] status: {summary_payload['status']}")
    print(f"[check_pilot_runtime_readiness] readiness_status: {summary_payload['readiness_status']}")
    print(f"[check_pilot_runtime_readiness] next_step_code: {summary_payload['next_step_code']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
