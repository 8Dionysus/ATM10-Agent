from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from atm10_agent.cli import main
from atm10_agent.evals import run_companion_core_suite


FIXED_NOW = datetime(2026, 7, 25, 13, 0, 0, tzinfo=timezone.utc)


def test_companion_core_eval_is_standalone_and_writes_separate_evidence(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    state_dir = tmp_path / "state"
    reports_dir = tmp_path / "eval-results"
    memory_dir = tmp_path / "memory"
    report = run_companion_core_suite(
        runs_dir=runs_dir,
        state_dir=state_dir,
        reports_dir=reports_dir,
        memory_dir=memory_dir,
        now=FIXED_NOW,
    )

    assert report["schema_version"] == "atm10_eval_report_v2"
    assert report["suite_id"] == "atm10-companion-core"
    assert report["status"] == "pass"
    assert report["verdict"] == "supports_bounded_claim"
    assert report["case_count"] == 8
    assert report["passed_count"] == 8
    assert report["failed_count"] == 0
    assert report["network_required"] is False
    assert report["live_services_required"] is False
    assert report["real_input_emitted"] is False
    assert Path(report["report_path"]).is_file()
    assert Path(report["report_path"]).is_relative_to(reports_dir)
    assert runs_dir.is_dir()
    assert state_dir.is_dir()
    assert reports_dir.is_dir()
    assert memory_dir.is_dir()
    assert (
        len(
            {
                runs_dir.resolve(),
                state_dir.resolve(),
                reports_dir.resolve(),
                memory_dir.resolve(),
            }
        )
        == 4
    )
    assert report["storage"]["memory_root"] == str(memory_dir)
    assert {case["status"] for case in report["cases"]} == {"pass"}
    assert report["claim"]["authority"] == "ATM10-Agent"
    assert report["scope"]["out"]
    assert report["blind_spots"]
    assert report["provenance"]
    assert {
        metric["definition"]["authority_ceiling"] for metric in report["metrics"]
    } == {"measurement_only_not_proof"}


def test_cli_eval_supports_a_fixed_clock_and_nonzero_contract(
    tmp_path: Path,
    capsys: object,
) -> None:
    exit_code = main(
        [
            "eval",
            "--suite",
            "companion-core",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--state-dir",
            str(tmp_path / "state"),
            "--reports-dir",
            str(tmp_path / "reports"),
            "--memory-dir",
            str(tmp_path / "memory"),
            "--now",
            "2026-07-25T13:00:00Z",
        ]
    )
    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "pass"
    assert report["observed_at_utc"] == "2026-07-25T13:00:00+00:00"
    assert Path(report["report_path"]).is_file()
