"""Owner-typed live acceptance for the Windows 11 ATM10 product edge."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from atm10_agent import __version__
from atm10_agent.agent_core.atm10_session_probe import (
    find_best_atm10_window,
    probe_atm10_session,
)
from atm10_agent.app import CompanionApp
from atm10_agent.contracts import TurnRequest
from atm10_agent.perception.windows_capture import capture_screen_image
from atm10_agent.trace import write_json


WINDOWS_LIVE_ACCEPTANCE_SCHEMA = "atm10_windows_live_acceptance_v1"
REQUIRED_CHECKS = (
    "windows_11",
    "powershell_7",
    "source_revision_pinned",
    "atm10_window_found",
    "atm10_window_foreground",
    "atm10_session_probable",
    "capture_intersects_window",
    "capture_backend_identified",
    "screenshot_written",
    "live_image_consumed",
    "cited_response_present",
    "companion_trace_written",
    "action_trace_correlated",
    "dry_run_true",
    "input_not_executed",
)


def _utc_now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc)


def _create_evidence_dir(root: Path, now: datetime) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stem = now.strftime("%Y%m%d_%H%M%S-windows-live")
    candidate = root / stem
    suffix = 1
    while candidate.exists():
        candidate = root / f"{stem}-{suffix:02d}"
        suffix += 1
    candidate.mkdir()
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: str | Path, evidence_dir: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(evidence_dir.resolve()))
    except ValueError:
        return resolved.name


def _resolve_source_revision(repo_root: Path, explicit: str | None) -> str | None:
    candidate = str(explicit or "").strip()
    if candidate:
        normalized = candidate.lower()
        is_hex_revision = len(normalized) == 40 and all(
            char in "0123456789abcdef" for char in normalized
        )
        return normalized if is_hex_revision else None
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    revision = result.stdout.strip()
    if result.returncode != 0 or len(revision) != 40:
        return None
    return revision


def _windows_build() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        return int(sys.getwindowsversion().build)
    except (AttributeError, TypeError, ValueError):
        return None


def _powershell_version() -> dict[str, Any]:
    result = subprocess.run(
        [
            "pwsh",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$PSVersionTable.PSVersion.ToString()",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    version = result.stdout.strip()
    major: int | None = None
    if result.returncode == 0 and version:
        try:
            major = int(version.split(".", 1)[0])
        except ValueError:
            major = None
    return {
        "command": "pwsh",
        "version": version or None,
        "major": major,
        "returncode": int(result.returncode),
    }


def _settle_for_window(seconds: float) -> None:
    if seconds <= 0:
        return
    print(
        f"[atm10] Focus the live ATM10 window; capture starts in {seconds:g} seconds.",
        file=sys.stderr,
        flush=True,
    )
    time.sleep(seconds)


def _bounds(candidate: Mapping[str, Any]) -> tuple[int, int, int, int] | None:
    raw = candidate.get("window_bounds")
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    try:
        left, top, right, bottom = (int(item) for item in raw)
    except (TypeError, ValueError):
        return None
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _run_companion_turn(
    *,
    screenshot_path: Path,
    evidence_dir: Path,
    state_dir: Path,
    now: datetime,
) -> dict[str, Any]:
    app = CompanionApp(
        runs_dir=evidence_dir / "turn-runs",
        state_dir=state_dir,
    )
    return app.run(
        TurnRequest(
            prompt="Describe the captured live ATM10 context.",
            query="steel tools",
            image_path=screenshot_path,
            action_intent="open_quest_book",
        ),
        now=now,
    )


def _turn_trace_matches(path: Path, turn_id: str) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, Mapping) and payload.get("turn_id") == turn_id


def _append_trace_contains(path: Path, turn_id: str) -> bool:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, Mapping) and payload.get("turn_id") == turn_id:
            return True
    return False


def _write_receipt(
    *,
    evidence_dir: Path,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    receipt_path = evidence_dir / "windows_live_acceptance.json"
    write_json(receipt_path, payload)
    return payload, receipt_path


def run_windows_live_acceptance(
    *,
    evidence_root: Path,
    state_dir: Path,
    repo_root: Path = Path("."),
    source_revision: str | None = None,
    settle_seconds: float = 5.0,
    now: datetime | None = None,
) -> tuple[dict[str, Any], Path]:
    """Collect one real Windows acceptance receipt without emitting input."""

    observed_at = _utc_now(now)
    evidence_dir = _create_evidence_dir(evidence_root, observed_at)
    checks = {name: False for name in REQUIRED_CHECKS}
    payload: dict[str, Any] = {
        "schema_version": WINDOWS_LIVE_ACCEPTANCE_SCHEMA,
        "status": "started",
        "degraded": False,
        "timestamp_utc": observed_at.isoformat(),
        "source_revision": None,
        "package_version": __version__,
        "platform": {
            "sys_platform": sys.platform,
            "windows_build": None,
            "powershell": None,
        },
        "checks": checks,
        "warnings": [],
        "errors": [],
        "session": None,
        "capture": None,
        "turn": None,
        "artifacts": {
            "receipt": "windows_live_acceptance.json",
            "screenshot": None,
            "turn_json": None,
            "append_only_trace": None,
        },
        "mutable_state_separate": True,
        "claim_limit": (
            "One current local Windows session and dry-run companion turn; "
            "does not validate optional model, store, or voice providers."
        ),
    }

    if sys.platform != "win32":
        payload["status"] = "blocked"
        payload["errors"].append("platform_not_windows")
        return _write_receipt(evidence_dir=evidence_dir, payload=payload)

    try:
        windows_build = _windows_build()
        payload["platform"]["windows_build"] = windows_build
        checks["windows_11"] = windows_build is not None and windows_build >= 22000

        powershell = _powershell_version()
        payload["platform"]["powershell"] = powershell
        checks["powershell_7"] = powershell.get("major") is not None and int(powershell["major"]) >= 7

        revision = _resolve_source_revision(repo_root, source_revision)
        payload["source_revision"] = revision
        checks["source_revision_pinned"] = revision is not None

        _settle_for_window(max(float(settle_seconds), 0.0))
        candidate = find_best_atm10_window(platform_name="win32")
        checks["atm10_window_found"] = candidate is not None
        if candidate is None:
            raise RuntimeError("ATM10 window was not found.")
        window_bounds = _bounds(candidate)
        if window_bounds is None:
            raise RuntimeError("ATM10 window has invalid bounds.")
        left, top, right, bottom = window_bounds

        session = probe_atm10_session(
            capture_target_kind="region",
            capture_bbox=[left, top, right, bottom],
            now=observed_at,
            platform_name="win32",
        )
        payload["session"] = session
        checks["atm10_window_foreground"] = bool(session.get("foreground"))
        checks["atm10_session_probable"] = session.get("atm10_probable") is True
        checks["capture_intersects_window"] = session.get("capture_intersects_window") is True

        screenshot_path = evidence_dir / "screenshot.png"
        capture = capture_screen_image(
            output_path=screenshot_path,
            region=(left, top, right - left, bottom - top),
            window_title=str(candidate.get("window_title", "")),
            window_bounds=window_bounds,
        )
        capture_payload = dict(capture)
        capture_payload["screenshot_path"] = "screenshot.png"
        capture_payload["screenshot_sha256"] = _sha256(screenshot_path)
        payload["capture"] = capture_payload
        capture_backend = str(capture.get("capture_backend", ""))
        checks["capture_backend_identified"] = (
            capture_backend.startswith("dxcam_")
            or capture_backend.startswith("pillow_imagegrab_")
        )
        checks["screenshot_written"] = (
            screenshot_path.is_file()
            and int(capture.get("width", 0)) > 0
            and int(capture.get("height", 0)) > 0
        )
        payload["artifacts"]["screenshot"] = "screenshot.png"
        if capture.get("backend_errors"):
            payload["degraded"] = True
            payload["warnings"].append("dxcam_failed_pillow_fallback_used")

        turn = _run_companion_turn(
            screenshot_path=screenshot_path,
            evidence_dir=evidence_dir,
            state_dir=state_dir,
            now=observed_at,
        )
        action = turn.get("action")
        action = action if isinstance(action, Mapping) else {}
        trace = turn.get("trace")
        trace = trace if isinstance(trace, Mapping) else {}
        turn_json_value = str(trace.get("turn_json", "")).strip()
        append_only_trace_value = str(trace.get("append_only_trace", "")).strip()
        turn_json = Path(turn_json_value) if turn_json_value else None
        append_only_trace = (
            Path(append_only_trace_value) if append_only_trace_value else None
        )
        turn_id = str(turn.get("turn_id", ""))
        stages = turn.get("stages")
        stages = stages if isinstance(stages, Mapping) else {}
        perception = stages.get("perception")
        perception = perception if isinstance(perception, Mapping) else {}
        citations = turn.get("citations")
        checks["live_image_consumed"] = perception.get("source") == "provided_image"
        checks["cited_response_present"] = isinstance(citations, list) and bool(citations)
        checks["companion_trace_written"] = (
            bool(turn_id)
            and turn_json is not None
            and append_only_trace is not None
            and _turn_trace_matches(turn_json, turn_id)
            and _append_trace_contains(append_only_trace, turn_id)
        )
        checks["action_trace_correlated"] = (
            bool(turn_id)
            and action.get("trace_id") == turn_id
            and bool(action.get("intent_id"))
        )
        checks["dry_run_true"] = action.get("dry_run") is True
        checks["input_not_executed"] = action.get("executed") is False
        payload["turn"] = {
            "turn_id": turn.get("turn_id"),
            "status": turn.get("status"),
            "degraded": bool(turn.get("degraded")),
            "perception_source": perception.get("source"),
            "citations_count": len(citations) if isinstance(citations, list) else 0,
            "action": {
                "intent": action.get("intent"),
                "intent_id": action.get("intent_id"),
                "trace_id": action.get("trace_id"),
                "dry_run": action.get("dry_run"),
                "executed": action.get("executed"),
            },
        }
        payload["artifacts"]["turn_json"] = (
            _relative(turn_json, evidence_dir) if turn_json is not None else None
        )
        payload["artifacts"]["append_only_trace"] = (
            _relative(append_only_trace, evidence_dir)
            if append_only_trace is not None
            else None
        )
    except Exception as exc:
        payload["errors"].append(f"{type(exc).__name__}: {exc}")

    failed_checks = [name for name, passed in checks.items() if not passed]
    if failed_checks:
        payload["errors"].extend(
            f"required_check_failed:{name}" for name in failed_checks
        )
        payload["status"] = "fail"
    else:
        payload["status"] = "pass"
    return _write_receipt(evidence_dir=evidence_dir, payload=payload)
