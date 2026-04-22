from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.start_operator_fedora_dev import build_start_command_payload
from scripts.write_fedora_companion_receipt import build_receipt_payload, write_receipt
from src.agent_core.atm10_session_probe import probe_atm10_session
from src.agent_core.fedora_companion_milestone import evaluate_fedora_companion_milestone
from src.agent_core.host_profiles import FEDORA_LOCAL_DEV_PROFILE_ID
from src.agent_core.readiness_scopes import evaluate_host_profile_session_readiness


def _startup_payload(**overrides):
    payload = build_start_command_payload(
        python_executable="python",
        runs_dir="runs/fedora",
        capture_region="0,0,1920,1080",
    )
    payload.update(overrides)
    return payload


def _session_probe():
    return probe_atm10_session(
        capture_target_kind="region",
        capture_bbox=[0, 0, 1920, 1080],
        now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        platform_name="linux",
    )


def _readiness(probe):
    return evaluate_host_profile_session_readiness(
        host_profile=FEDORA_LOCAL_DEV_PROFILE_ID,
        session_probe=probe,
    )


def _instance_report(atm10_dir: str | None = "/games/ATM10"):
    return {
        "paths": {"atm10_dir": atm10_dir},
        "exists": {"atm10_dir": bool(atm10_dir)},
    }


def test_fedora_companion_milestone_receipt_accepts_dev_companion_evidence() -> None:
    probe = _session_probe()
    receipt = evaluate_fedora_companion_milestone(
        startup_payload=_startup_payload(),
        session_probe=probe,
        readiness_evaluation=_readiness(probe),
        instance_discovery_report=_instance_report(),
    )

    assert receipt["schema_version"] == "fedora_companion_milestone_receipt_v1"
    assert receipt["status"] == "ok"
    assert receipt["blocking_reason_codes"] == []
    assert set(receipt["required_checks"]) <= set(receipt["satisfied_checks"])
    assert "window_identity_unavailable" in receipt["warning_reason_codes"]


def test_fedora_companion_milestone_blocks_when_instance_path_is_required() -> None:
    probe = _session_probe()
    receipt = evaluate_fedora_companion_milestone(
        startup_payload=_startup_payload(),
        session_probe=probe,
        readiness_evaluation=_readiness(probe),
        instance_discovery_report=_instance_report(None),
    )

    assert receipt["status"] == "attention"
    assert "atm10_instance_path_missing" in receipt["blocking_reason_codes"]
    assert "set_ATM10_DIR_or_place_ATM10_under_a_scanned_launcher_root" in receipt["recommended_actions"]


def test_fedora_companion_milestone_can_skip_instance_path_for_ci_mechanics() -> None:
    probe = _session_probe()
    receipt = evaluate_fedora_companion_milestone(
        startup_payload=_startup_payload(),
        session_probe=probe,
        readiness_evaluation=_readiness(probe),
        instance_discovery_report=_instance_report(None),
        require_instance_path=False,
    )

    assert receipt["status"] == "ok"
    assert "atm10_instance_path_known" in receipt["skipped_checks"]


def test_fedora_companion_milestone_preserves_dry_run_boundary() -> None:
    startup = _startup_payload()
    startup["command"] = [*startup["command"], "--execute"]
    probe = _session_probe()

    receipt = evaluate_fedora_companion_milestone(
        startup_payload=startup,
        session_probe=probe,
        readiness_evaluation=_readiness(probe),
        instance_discovery_report=_instance_report(),
    )

    assert receipt["status"] == "attention"
    assert "unsafe_automation_flag_present" in receipt["blocking_reason_codes"]


def test_write_receipt_builds_json_payload_without_launching_runtimes(tmp_path: Path) -> None:
    atm10_dir = tmp_path / "ATM10"
    atm10_dir.mkdir()
    payload = build_receipt_payload(
        env={"HOME": str(tmp_path), "ATM10_DIR": str(atm10_dir)},
        runs_dir=tmp_path / "runs",
        capture_region="0,0,1280,720",
        now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
    )

    assert payload["milestone_evaluation"]["status"] == "ok"
    assert payload["startup_payload"]["host_profile"] == FEDORA_LOCAL_DEV_PROFILE_ID
    json.dumps(payload)


def test_write_receipt_writes_artifact(tmp_path: Path, monkeypatch) -> None:
    atm10_dir = tmp_path / "ATM10"
    atm10_dir.mkdir()
    monkeypatch.setenv("ATM10_DIR", str(atm10_dir))
    payload, path = write_receipt(
        runs_dir=tmp_path / "runs",
        capture_region="0,0,1280,720",
        allow_missing_atm10_dir=False,
        require_atm10_dir_exists=False,
        now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
    )

    assert path.name == "fedora_companion_milestone_receipt.json"
    assert path.is_file()
    assert payload["milestone_evaluation"]["status"] == "ok"
