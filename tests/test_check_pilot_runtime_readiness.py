from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import scripts.check_pilot_runtime_readiness as readiness


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_operator_startup_run(
    operator_runs_dir: Path,
    pilot_runs_dir: Path,
    *,
    timestamp: datetime,
    status: str = "running",
    pilot_configured: bool = True,
) -> Path:
    run_dir = operator_runs_dir / timestamp.strftime("%Y%m%d_%H%M%S-start-operator-product")
    run_dir.mkdir(parents=True, exist_ok=True)
    run_json_path = run_dir / "run.json"
    startup_plan_json = run_dir / "startup_plan.json"
    startup_plan_json.write_text("{}", encoding="utf-8")
    _write_json(
        run_json_path,
        {
            "schema_version": "operator_product_startup_v1",
            "mode": "start_operator_product",
            "status": status,
            "profile": "operator_product_core",
            "timestamp_utc": timestamp.isoformat(),
            "artifact_roots": {
                "operator_runs_dir": str(operator_runs_dir),
                "pilot_runtime_runs_dir": str(pilot_runs_dir),
            },
            "managed_processes": {
                "pilot_runtime": {
                    "managed": True,
                    "configured": pilot_configured,
                }
            },
            "session_state": {
                "pilot_runtime": {
                    "service_name": "pilot_runtime",
                    "managed": True,
                    "configured": pilot_configured,
                    "runs_dir": str(pilot_runs_dir),
                    "status": status,
                    "last_probe": {"status": "ok"},
                }
            },
            "paths": {
                "run_json": str(run_json_path),
                "startup_plan_json": str(startup_plan_json),
            },
            "child_processes": {},
            "startup_checkpoints": [],
        },
    )
    return run_json_path


def _write_pilot_turn(
    turn_json_path: Path,
    *,
    timestamp: datetime,
    status: str = "ok",
    audio_mode: str = readiness.LIVE_AUDIO_MODE,
    hybrid_profile: str = "combo_a",
    hybrid_degraded: bool = False,
    planner_status: str = "hybrid_merged",
    schema_version: str = "pilot_turn_v1",
) -> None:
    _write_json(
        turn_json_path,
        {
            "schema_version": schema_version,
            "turn_id": turn_json_path.parent.name,
            "timestamp_utc": timestamp.isoformat(),
            "completed_at_utc": timestamp.isoformat(),
            "status": status,
            "audio": {"mode": audio_mode},
            "hybrid": {
                "profile": hybrid_profile,
                "planner_status": planner_status,
                "degraded": hybrid_degraded,
            },
            "answer_text": "Quest book is the next step.",
            "paths": {
                "turn_json": str(turn_json_path),
            },
        },
    )


def _write_pilot_runtime_status(
    pilot_runs_dir: Path,
    turn_json_path: Path | None,
    *,
    timestamp: datetime,
    status: str = "running",
    capture_monitor: int | None = 0,
    capture_region: list[int] | None = None,
    schema_version: str = "pilot_runtime_status_v1",
) -> Path:
    status_path = pilot_runs_dir / "pilot_runtime_status_latest.json"
    _write_json(
        status_path,
        {
            "schema_version": schema_version,
            "timestamp_utc": timestamp.isoformat(),
            "status": status,
            "state": "idle",
            "hotkey": "F8",
            "effective_config": {
                "gateway_url": "http://127.0.0.1:8770",
                "voice_runtime_url": "http://127.0.0.1:8765",
                "tts_runtime_url": "http://127.0.0.1:8780",
                "capture_monitor": capture_monitor,
                "capture_region": capture_region,
                "vlm_model_dir": "models/qwen2.5-vl-7b-instruct-int4-ov",
                "text_model_dir": "models/qwen3-8b-int4-cw-ov",
            },
            "degraded_services": [],
            "last_error": None,
            "last_turn_id": None if turn_json_path is None else turn_json_path.parent.name,
            "last_turn_started_at_utc": None if turn_json_path is None else timestamp.isoformat(),
            "last_turn_completed_at_utc": None if turn_json_path is None else timestamp.isoformat(),
            "latency_summary": {"total_sec": 1.23},
            "paths": {
                "run_dir": str(pilot_runs_dir / "20260323_120000-pilot-runtime"),
                "status_json": str(pilot_runs_dir / "20260323_120000-pilot-runtime" / "pilot_runtime_status.json"),
                "latest_status_json": str(status_path),
                "last_turn_json": None if turn_json_path is None else str(turn_json_path),
            },
        },
    )
    return status_path


def test_check_pilot_runtime_readiness_green_live_path(tmp_path: Path) -> None:
    now = datetime(2026, 3, 23, 18, 0, 0, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    operator_runs_dir = runs_dir
    pilot_runs_dir = runs_dir / "pilot-runtime"
    turn_json_path = pilot_runs_dir / "20260323_175500-pilot-runtime" / "turns" / "20260323_175600-pilot-turn" / "pilot_turn.json"
    _write_operator_startup_run(operator_runs_dir, pilot_runs_dir, timestamp=now - timedelta(minutes=10))
    _write_pilot_turn(turn_json_path, timestamp=now - timedelta(minutes=4))
    _write_pilot_runtime_status(pilot_runs_dir, turn_json_path, timestamp=now - timedelta(minutes=3))

    result = readiness.run_check_pilot_runtime_readiness(runs_dir=runs_dir, now=now)

    summary = result["summary_payload"]
    assert result["exit_code"] == 0
    assert summary["status"] == "ok"
    assert summary["readiness_status"] == "ready"
    assert summary["blocking_reason_codes"] == []
    assert summary["next_step_code"] == "none"
    assert summary["evidence"]["live_turn_evidence"] is True
    assert summary["evidence"]["hybrid_profile"] == "combo_a"
    assert Path(summary["paths"]["summary_json"]).is_file()
    assert Path(summary["paths"]["history_summary_json"]).is_file()
    assert Path(summary["paths"]["summary_md"]).is_file()


def test_check_pilot_runtime_readiness_blocks_when_startup_artifact_missing(tmp_path: Path) -> None:
    now = datetime(2026, 3, 23, 18, 0, 0, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    pilot_runs_dir = runs_dir / "pilot-runtime"
    turn_json_path = pilot_runs_dir / "20260323_175500-pilot-runtime" / "turns" / "20260323_175600-pilot-turn" / "pilot_turn.json"
    _write_pilot_turn(turn_json_path, timestamp=now - timedelta(minutes=4))
    _write_pilot_runtime_status(pilot_runs_dir, turn_json_path, timestamp=now - timedelta(minutes=3))

    result = readiness.run_check_pilot_runtime_readiness(runs_dir=runs_dir, now=now)

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "blocked"
    assert "startup_artifact_missing" in summary["blocking_reason_codes"]


def test_check_pilot_runtime_readiness_blocks_when_pilot_status_missing(tmp_path: Path) -> None:
    now = datetime(2026, 3, 23, 18, 0, 0, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    pilot_runs_dir = runs_dir / "pilot-runtime"
    _write_operator_startup_run(runs_dir, pilot_runs_dir, timestamp=now - timedelta(minutes=10))

    result = readiness.run_check_pilot_runtime_readiness(runs_dir=runs_dir, now=now)

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "blocked"
    assert "pilot_status_missing" in summary["blocking_reason_codes"]


def test_check_pilot_runtime_readiness_blocks_when_capture_not_configured(tmp_path: Path) -> None:
    now = datetime(2026, 3, 23, 18, 0, 0, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    pilot_runs_dir = runs_dir / "pilot-runtime"
    turn_json_path = pilot_runs_dir / "20260323_175500-pilot-runtime" / "turns" / "20260323_175600-pilot-turn" / "pilot_turn.json"
    _write_operator_startup_run(runs_dir, pilot_runs_dir, timestamp=now - timedelta(minutes=10))
    _write_pilot_turn(turn_json_path, timestamp=now - timedelta(minutes=4))
    _write_pilot_runtime_status(
        pilot_runs_dir,
        turn_json_path,
        timestamp=now - timedelta(minutes=3),
        capture_monitor=None,
        capture_region=None,
    )

    result = readiness.run_check_pilot_runtime_readiness(runs_dir=runs_dir, now=now)

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "blocked"
    assert "capture_not_configured" in summary["blocking_reason_codes"]


def test_check_pilot_runtime_readiness_blocks_when_last_turn_schema_is_invalid(tmp_path: Path) -> None:
    now = datetime(2026, 3, 23, 18, 0, 0, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    pilot_runs_dir = runs_dir / "pilot-runtime"
    turn_json_path = pilot_runs_dir / "20260323_175500-pilot-runtime" / "turns" / "20260323_175600-pilot-turn" / "pilot_turn.json"
    _write_operator_startup_run(runs_dir, pilot_runs_dir, timestamp=now - timedelta(minutes=10))
    _write_pilot_turn(
        turn_json_path,
        timestamp=now - timedelta(minutes=4),
        schema_version="wrong_pilot_turn_schema_v1",
    )
    _write_pilot_runtime_status(pilot_runs_dir, turn_json_path, timestamp=now - timedelta(minutes=3))

    result = readiness.run_check_pilot_runtime_readiness(runs_dir=runs_dir, now=now)

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "blocked"
    assert "pilot_turn_invalid" in summary["blocking_reason_codes"]
    assert summary["warnings"]


def test_check_pilot_runtime_readiness_marks_stale_turn_as_attention(tmp_path: Path) -> None:
    now = datetime(2026, 3, 23, 18, 0, 0, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    pilot_runs_dir = runs_dir / "pilot-runtime"
    turn_json_path = pilot_runs_dir / "20260323_145500-pilot-runtime" / "turns" / "20260323_145600-pilot-turn" / "pilot_turn.json"
    _write_operator_startup_run(runs_dir, pilot_runs_dir, timestamp=now - timedelta(minutes=20))
    _write_pilot_turn(turn_json_path, timestamp=now - timedelta(hours=3))
    _write_pilot_runtime_status(pilot_runs_dir, turn_json_path, timestamp=now - timedelta(minutes=3))

    result = readiness.run_check_pilot_runtime_readiness(runs_dir=runs_dir, now=now)

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "attention"
    assert "pilot_turn_stale" in summary["blocking_reason_codes"]


def test_check_pilot_runtime_readiness_marks_degraded_turn_as_attention(tmp_path: Path) -> None:
    now = datetime(2026, 3, 23, 18, 0, 0, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    pilot_runs_dir = runs_dir / "pilot-runtime"
    turn_json_path = pilot_runs_dir / "20260323_175500-pilot-runtime" / "turns" / "20260323_175600-pilot-turn" / "pilot_turn.json"
    _write_operator_startup_run(runs_dir, pilot_runs_dir, timestamp=now - timedelta(minutes=10))
    _write_pilot_turn(turn_json_path, timestamp=now - timedelta(minutes=4), status="degraded")
    _write_pilot_runtime_status(pilot_runs_dir, turn_json_path, timestamp=now - timedelta(minutes=3))

    result = readiness.run_check_pilot_runtime_readiness(runs_dir=runs_dir, now=now)

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "attention"
    assert "pilot_turn_degraded" in summary["blocking_reason_codes"]


def test_check_pilot_runtime_readiness_blocks_on_error_turn(tmp_path: Path) -> None:
    now = datetime(2026, 3, 23, 18, 0, 0, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    pilot_runs_dir = runs_dir / "pilot-runtime"
    turn_json_path = pilot_runs_dir / "20260323_175500-pilot-runtime" / "turns" / "20260323_175600-pilot-turn" / "pilot_turn.json"
    _write_operator_startup_run(runs_dir, pilot_runs_dir, timestamp=now - timedelta(minutes=10))
    _write_pilot_turn(turn_json_path, timestamp=now - timedelta(minutes=4), status="error")
    _write_pilot_runtime_status(pilot_runs_dir, turn_json_path, timestamp=now - timedelta(minutes=3))

    result = readiness.run_check_pilot_runtime_readiness(runs_dir=runs_dir, now=now)

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "blocked"
    assert "pilot_turn_error" in summary["blocking_reason_codes"]


def test_check_pilot_runtime_readiness_blocks_when_turn_is_not_completed(tmp_path: Path) -> None:
    now = datetime(2026, 3, 23, 18, 0, 0, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    pilot_runs_dir = runs_dir / "pilot-runtime"
    turn_json_path = pilot_runs_dir / "20260323_175500-pilot-runtime" / "turns" / "20260323_175600-pilot-turn" / "pilot_turn.json"
    _write_operator_startup_run(runs_dir, pilot_runs_dir, timestamp=now - timedelta(minutes=10))
    _write_pilot_turn(turn_json_path, timestamp=now - timedelta(minutes=4), status="started")
    _write_pilot_runtime_status(pilot_runs_dir, turn_json_path, timestamp=now - timedelta(minutes=3))

    result = readiness.run_check_pilot_runtime_readiness(runs_dir=runs_dir, now=now)

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "blocked"
    assert "pilot_turn_not_completed" in summary["blocking_reason_codes"]


def test_check_pilot_runtime_readiness_blocks_when_combo_a_evidence_is_missing(tmp_path: Path) -> None:
    now = datetime(2026, 3, 23, 18, 0, 0, tzinfo=timezone.utc)
    runs_dir = tmp_path / "runs"
    pilot_runs_dir = runs_dir / "pilot-runtime"
    turn_json_path = pilot_runs_dir / "20260323_175500-pilot-runtime" / "turns" / "20260323_175600-pilot-turn" / "pilot_turn.json"
    _write_operator_startup_run(runs_dir, pilot_runs_dir, timestamp=now - timedelta(minutes=10))
    _write_pilot_turn(turn_json_path, timestamp=now - timedelta(minutes=4), hybrid_profile="baseline_first")
    _write_pilot_runtime_status(pilot_runs_dir, turn_json_path, timestamp=now - timedelta(minutes=3))

    result = readiness.run_check_pilot_runtime_readiness(runs_dir=runs_dir, now=now)

    summary = result["summary_payload"]
    assert summary["readiness_status"] == "blocked"
    assert "hybrid_profile_not_combo_a" in summary["blocking_reason_codes"]
