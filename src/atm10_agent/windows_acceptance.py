"""Owner-typed live acceptance for the Windows 11 ATM10 product edge."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
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


WINDOWS_LIVE_ACCEPTANCE_SCHEMA = "atm10_windows_live_acceptance_v2"
WINDOWS_LIVE_ACCEPTANCE_VERIFICATION_SCHEMA = (
    "atm10_windows_live_acceptance_verification_v1"
)
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
    "audio_posture_explicit",
    "live_image_consumed",
    "cited_response_present",
    "companion_trace_written",
    "action_trace_correlated",
    "dry_run_true",
    "input_not_executed",
)
VERIFICATION_CHECKS = (
    "receipt_schema",
    "status_pass",
    "source_revision_matches",
    "receipt_fresh",
    "windows_11",
    "powershell_7",
    "producer_checks_pass",
    "session_consistent",
    "audio_posture_explicit",
    "degradation_honest",
    "capture_consistent",
    "screenshot_integrity",
    "turn_consistent",
    "turn_json_integrity",
    "append_only_trace_integrity",
    "dry_run_fence",
    "errors_empty",
    "mutable_state_separate",
)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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
        return resolved.relative_to(evidence_dir.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"artifact_outside_evidence_dir:{resolved.name}") from exc


def _artifact(path: Path, evidence_dir: Path) -> dict[str, str]:
    return {
        "path": _relative(path, evidence_dir),
        "sha256": _sha256(path),
    }


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
        "audio": None,
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

        payload["audio"] = {
            "mode": "degraded_no_audio",
            "status": "degraded",
            "push_to_talk_exercised": False,
            "reason": "audio_input_not_exercised",
        }
        checks["audio_posture_explicit"] = True
        payload["degraded"] = True
        payload["warnings"].append("audio_input_not_exercised")

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
        screenshot_artifact = _artifact(screenshot_path, evidence_dir)
        capture_payload["screenshot_sha256"] = screenshot_artifact["sha256"]
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
        payload["artifacts"]["screenshot"] = screenshot_artifact
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
            _artifact(turn_json, evidence_dir) if turn_json is not None else None
        )
        payload["artifacts"]["append_only_trace"] = (
            _artifact(append_only_trace, evidence_dir)
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


def _empty_verification(
    *,
    receipt_path: Path,
    expected_revision: str,
    max_age_hours: float,
) -> dict[str, Any]:
    return {
        "schema_version": WINDOWS_LIVE_ACCEPTANCE_VERIFICATION_SCHEMA,
        "status": "fail",
        "receipt": str(receipt_path),
        "expected_source_revision": expected_revision,
        "observed_source_revision": None,
        "max_age_hours": max_age_hours,
        "degraded": None,
        "checks": {name: False for name in VERIFICATION_CHECKS},
        "warnings": [],
        "errors": [],
        "claim_limit": (
            "Offline consistency and artifact-integrity verification of one "
            "ATM10-produced receipt; it does not independently attest that the "
            "operator presented a physical Windows session."
        ),
    }


def _safe_artifact_path(
    *,
    receipt_path: Path,
    record: object,
) -> tuple[Path | None, str | None]:
    if not isinstance(record, Mapping):
        return None, None
    relative = record.get("path")
    digest = record.get("sha256")
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or ":" in relative
    ):
        return None, None
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
    ):
        return None, None
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None, None
    evidence_dir = receipt_path.parent.resolve()
    resolved = (evidence_dir / candidate).resolve()
    try:
        resolved.relative_to(evidence_dir)
    except ValueError:
        return None, None
    return resolved, digest


def _timestamp_is_fresh(
    value: object,
    *,
    now: datetime,
    max_age_hours: float,
) -> bool:
    if not isinstance(value, str) or max_age_hours <= 0:
        return False
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if observed.tzinfo is None:
        return False
    age = now.astimezone(timezone.utc) - observed.astimezone(timezone.utc)
    return -timedelta(minutes=5) <= age <= timedelta(hours=max_age_hours)


def _artifact_integrity(
    *,
    receipt_path: Path,
    record: object,
    png: bool = False,
) -> tuple[bool, Path | None]:
    path, expected_digest = _safe_artifact_path(
        receipt_path=receipt_path,
        record=record,
    )
    if path is None or expected_digest is None or not path.is_file():
        return False, path
    try:
        if _sha256(path) != expected_digest:
            return False, path
        if png:
            with path.open("rb") as handle:
                if handle.read(len(_PNG_SIGNATURE)) != _PNG_SIGNATURE:
                    return False, path
    except OSError:
        return False, path
    return True, path


def verify_windows_live_acceptance(
    *,
    receipt_path: Path,
    expected_revision: str,
    max_age_hours: float = 24.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify a transferred live receipt and its local artifact bundle.

    This verifier recomputes semantic and integrity checks instead of trusting
    the producer's boolean check map. It deliberately makes no stronger
    hardware-attestation claim than the receipt can support.
    """

    expected = str(expected_revision).strip().lower()
    max_age = float(max_age_hours)
    if not math.isfinite(max_age) or max_age <= 0:
        raise ValueError("max_age_hours must be a positive finite number")
    result = _empty_verification(
        receipt_path=receipt_path,
        expected_revision=expected,
        max_age_hours=max_age,
    )
    checks = result["checks"]
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result["errors"].append(f"receipt_unreadable:{type(exc).__name__}")
        return result
    if not isinstance(payload, Mapping):
        result["errors"].append("receipt_not_object")
        return result

    result["observed_source_revision"] = payload.get("source_revision")
    result["degraded"] = payload.get("degraded")
    receipt_warnings = payload.get("warnings")
    if isinstance(receipt_warnings, list):
        result["warnings"] = [
            item for item in receipt_warnings if isinstance(item, str)
        ]

    artifacts = payload.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, Mapping) else {}
    checks["receipt_schema"] = (
        payload.get("schema_version") == WINDOWS_LIVE_ACCEPTANCE_SCHEMA
        and receipt_path.name == "windows_live_acceptance.json"
        and artifacts.get("receipt") == receipt_path.name
    )
    checks["status_pass"] = payload.get("status") == "pass"
    checks["source_revision_matches"] = (
        len(expected) == 40
        and all(char in "0123456789abcdef" for char in expected)
        and payload.get("source_revision") == expected
    )
    checks["receipt_fresh"] = _timestamp_is_fresh(
        payload.get("timestamp_utc"),
        now=_utc_now(now),
        max_age_hours=max_age,
    )

    platform = payload.get("platform")
    platform = platform if isinstance(platform, Mapping) else {}
    windows_build = platform.get("windows_build")
    checks["windows_11"] = (
        platform.get("sys_platform") == "win32"
        and isinstance(windows_build, int)
        and not isinstance(windows_build, bool)
        and windows_build >= 22000
    )
    powershell = platform.get("powershell")
    powershell = powershell if isinstance(powershell, Mapping) else {}
    powershell_major = powershell.get("major")
    checks["powershell_7"] = (
        powershell.get("command") == "pwsh"
        and isinstance(powershell_major, int)
        and not isinstance(powershell_major, bool)
        and powershell_major >= 7
        and powershell.get("returncode") == 0
    )

    producer_checks = payload.get("checks")
    checks["producer_checks_pass"] = (
        isinstance(producer_checks, Mapping)
        and set(producer_checks) == set(REQUIRED_CHECKS)
        and all(producer_checks.get(name) is True for name in REQUIRED_CHECKS)
    )

    session = payload.get("session")
    session = session if isinstance(session, Mapping) else {}
    checks["session_consistent"] = (
        session.get("window_found") is True
        and session.get("foreground") is True
        and session.get("atm10_probable") is True
        and session.get("capture_intersects_window") is True
    )

    audio = payload.get("audio")
    audio = audio if isinstance(audio, Mapping) else {}
    checks["audio_posture_explicit"] = (
        audio.get("mode") == "degraded_no_audio"
        and audio.get("status") == "degraded"
        and audio.get("push_to_talk_exercised") is False
        and audio.get("reason") == "audio_input_not_exercised"
    )
    screenshot_ok, screenshot_path = _artifact_integrity(
        receipt_path=receipt_path,
        record=artifacts.get("screenshot"),
        png=True,
    )
    capture = payload.get("capture")
    capture = capture if isinstance(capture, Mapping) else {}
    capture_backend = capture.get("capture_backend")
    screenshot_record = artifacts.get("screenshot")
    screenshot_record = (
        screenshot_record if isinstance(screenshot_record, Mapping) else {}
    )
    width = capture.get("width")
    height = capture.get("height")
    checks["capture_consistent"] = (
        isinstance(capture_backend, str)
        and (
            capture_backend.startswith("dxcam_")
            or capture_backend.startswith("pillow_imagegrab_")
        )
        and isinstance(width, int)
        and not isinstance(width, bool)
        and width > 0
        and isinstance(height, int)
        and not isinstance(height, bool)
        and height > 0
        and capture.get("screenshot_path") == screenshot_record.get("path")
        and capture.get("screenshot_sha256") == screenshot_record.get("sha256")
    )
    expected_warnings = {"audio_input_not_exercised"}
    if isinstance(capture_backend, str) and capture_backend.startswith(
        "pillow_imagegrab_"
    ):
        expected_warnings.add("dxcam_failed_pillow_fallback_used")
    checks["degradation_honest"] = (
        payload.get("degraded") is True
        and set(result["warnings"]) == expected_warnings
    )
    checks["screenshot_integrity"] = screenshot_ok and screenshot_path is not None

    turn = payload.get("turn")
    turn = turn if isinstance(turn, Mapping) else {}
    turn_id = turn.get("turn_id")
    action = turn.get("action")
    action = action if isinstance(action, Mapping) else {}
    checks["turn_consistent"] = (
        isinstance(turn_id, str)
        and bool(turn_id)
        and turn.get("status") == "ok"
        and turn.get("perception_source") == "provided_image"
        and isinstance(turn.get("citations_count"), int)
        and not isinstance(turn.get("citations_count"), bool)
        and turn.get("citations_count") > 0
        and action.get("trace_id") == turn_id
        and isinstance(action.get("intent_id"), str)
        and bool(action.get("intent_id"))
    )

    turn_json_ok, turn_json_path = _artifact_integrity(
        receipt_path=receipt_path,
        record=artifacts.get("turn_json"),
    )
    checks["turn_json_integrity"] = (
        turn_json_ok
        and isinstance(turn_id, str)
        and turn_json_path is not None
        and _turn_trace_matches(turn_json_path, turn_id)
    )
    append_ok, append_path = _artifact_integrity(
        receipt_path=receipt_path,
        record=artifacts.get("append_only_trace"),
    )
    checks["append_only_trace_integrity"] = (
        append_ok
        and isinstance(turn_id, str)
        and append_path is not None
        and _append_trace_contains(append_path, turn_id)
    )
    checks["dry_run_fence"] = (
        action.get("dry_run") is True and action.get("executed") is False
    )
    checks["errors_empty"] = payload.get("errors") == []
    checks["mutable_state_separate"] = payload.get("mutable_state_separate") is True

    failed = [name for name in VERIFICATION_CHECKS if checks.get(name) is not True]
    if failed:
        result["errors"] = [
            f"verification_check_failed:{name}" for name in failed
        ]
    else:
        result["status"] = "pass"
    return result
