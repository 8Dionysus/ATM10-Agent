from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

import atm10_agent.windows_acceptance as acceptance
from atm10_agent.cli import main


FIXED_NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
REVISION = "a" * 40


def _schema() -> dict[str, object]:
    return json.loads(
        Path("schemas/windows_live_acceptance_v1.json").read_text(encoding="utf-8")
    )


def test_non_windows_run_is_explicitly_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(acceptance.sys, "platform", "linux")

    payload, receipt_path = acceptance.run_windows_live_acceptance(
        evidence_root=tmp_path / "evidence",
        state_dir=tmp_path / "state",
        settle_seconds=0,
        now=FIXED_NOW,
    )

    assert payload["status"] == "blocked"
    assert payload["errors"] == ["platform_not_windows"]
    assert not any(payload["checks"].values())
    assert receipt_path.is_file()
    Draft202012Validator(_schema()).validate(payload)


def test_cli_non_windows_run_returns_nonzero_with_receipt(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(acceptance.sys, "platform", "linux")

    exit_code = main(
        [
            "windows-acceptance",
            "--evidence-dir",
            str(tmp_path / "evidence"),
            "--state-dir",
            str(tmp_path / "state"),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["status"] == "blocked"
    assert Path(output["receipt"]).is_file()


def test_live_receipt_correlates_capture_turn_trace_and_dry_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(acceptance.sys, "platform", "win32")
    monkeypatch.setattr(acceptance, "_windows_build", lambda: 26100)
    monkeypatch.setattr(
        acceptance,
        "_powershell_version",
        lambda: {"command": "pwsh", "version": "7.5.2", "major": 7, "returncode": 0},
    )
    monkeypatch.setattr(
        acceptance,
        "_resolve_source_revision",
        lambda repo_root, explicit: REVISION,
    )
    monkeypatch.setattr(
        acceptance,
        "find_best_atm10_window",
        lambda **kwargs: {
            "window_title": "Minecraft - All the Mods 10",
            "process_name": "javaw.exe",
            "foreground": True,
            "window_bounds": [10, 20, 1290, 740],
        },
    )
    monkeypatch.setattr(
        acceptance,
        "probe_atm10_session",
        lambda **kwargs: {
            "schema_version": "atm10_session_probe_v1",
            "status": "ok",
            "window_found": True,
            "foreground": True,
            "atm10_probable": True,
            "capture_intersects_window": True,
            "reason_codes": [],
        },
    )

    def _capture(*, output_path: Path, **kwargs):
        output_path.write_bytes(b"fake-png")
        return {
            "capture_mode": "region",
            "capture_backend": "dxcam_dxgi",
            "width": 1280,
            "height": 720,
            "screenshot_path": str(output_path),
        }

    monkeypatch.setattr(acceptance, "capture_screen_image", _capture)

    def _turn(*, evidence_dir: Path, **kwargs):
        turn_dir = evidence_dir / "turn-runs" / "fixture"
        turn_dir.mkdir(parents=True)
        turn_json = turn_dir / "turn.json"
        trace_jsonl = evidence_dir / "turn-runs" / "turn-trace.jsonl"
        turn_json.write_text('{"turn_id":"turn:fixture"}\n', encoding="utf-8")
        trace_jsonl.write_text('{"turn_id":"turn:fixture"}\n', encoding="utf-8")
        return {
            "turn_id": "turn:fixture",
            "status": "ok",
            "degraded": False,
            "stages": {"perception": {"source": "provided_image"}},
            "citations": [{"id": "doc:steel_tools"}],
            "action": {
                "intent": "open_quest_book",
                "intent_id": "intent:fixture",
                "trace_id": "turn:fixture",
                "dry_run": True,
                "executed": False,
            },
            "trace": {
                "turn_json": str(turn_json),
                "append_only_trace": str(trace_jsonl),
            },
        }

    monkeypatch.setattr(acceptance, "_run_companion_turn", _turn)

    payload, receipt_path = acceptance.run_windows_live_acceptance(
        evidence_root=tmp_path / "evidence",
        state_dir=tmp_path / "state",
        settle_seconds=0,
        now=FIXED_NOW,
    )

    assert payload["status"] == "pass"
    assert payload["degraded"] is False
    assert all(payload["checks"].values())
    assert payload["source_revision"] == REVISION
    assert payload["capture"]["capture_backend"] == "dxcam_dxgi"
    assert payload["capture"]["screenshot_sha256"]
    assert payload["turn"]["action"]["executed"] is False
    assert receipt_path.is_file()
    Draft202012Validator(_schema()).validate(payload)


def test_pillow_fallback_is_pass_with_explicit_degradation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(acceptance.sys, "platform", "win32")
    monkeypatch.setattr(acceptance, "_windows_build", lambda: 26100)
    monkeypatch.setattr(
        acceptance,
        "_powershell_version",
        lambda: {"command": "pwsh", "version": "7.5.2", "major": 7, "returncode": 0},
    )
    monkeypatch.setattr(acceptance, "_resolve_source_revision", lambda *args: REVISION)
    monkeypatch.setattr(
        acceptance,
        "find_best_atm10_window",
        lambda **kwargs: {
            "window_title": "All the Mods 10",
            "foreground": True,
            "window_bounds": [0, 0, 800, 600],
        },
    )
    monkeypatch.setattr(
        acceptance,
        "probe_atm10_session",
        lambda **kwargs: {
            "foreground": True,
            "atm10_probable": True,
            "capture_intersects_window": True,
        },
    )

    def _capture(*, output_path: Path, **kwargs):
        output_path.write_bytes(b"fallback")
        return {
            "capture_backend": "pillow_imagegrab_desktop",
            "width": 800,
            "height": 600,
            "backend_errors": [{"backend": "dxcam_dxgi", "error": "device unavailable"}],
        }

    monkeypatch.setattr(acceptance, "capture_screen_image", _capture)

    def _turn(*, evidence_dir: Path, **kwargs):
        turn_dir = evidence_dir / "turn-runs"
        turn_dir.mkdir()
        turn_json = turn_dir / "turn.json"
        trace = turn_dir / "trace.jsonl"
        turn_json.write_text('{"turn_id":"turn:fallback"}\n', encoding="utf-8")
        trace.write_text('{"turn_id":"turn:fallback"}\n', encoding="utf-8")
        return {
            "turn_id": "turn:fallback",
            "status": "ok",
            "degraded": False,
            "stages": {"perception": {"source": "provided_image"}},
            "citations": [{"id": "doc:steel_tools"}],
            "action": {
                "intent": "open_quest_book",
                "intent_id": "intent:fallback",
                "trace_id": "turn:fallback",
                "dry_run": True,
                "executed": False,
            },
            "trace": {
                "turn_json": str(turn_json),
                "append_only_trace": str(trace),
            },
        }

    monkeypatch.setattr(acceptance, "_run_companion_turn", _turn)

    payload, _ = acceptance.run_windows_live_acceptance(
        evidence_root=tmp_path / "evidence",
        state_dir=tmp_path / "state",
        settle_seconds=0,
        now=FIXED_NOW,
    )

    assert payload["status"] == "pass"
    assert payload["degraded"] is True
    assert payload["warnings"] == ["dxcam_failed_pillow_fallback_used"]
    Draft202012Validator(_schema()).validate(payload)
