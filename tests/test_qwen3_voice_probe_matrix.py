import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import scripts.qwen3_voice_probe_matrix as matrix_probe


def test_qwen3_voice_probe_matrix_dry_run_writes_plan(tmp_path: Path) -> None:
    result = matrix_probe.run_qwen3_voice_probe_matrix(
        execute=False,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 20, 20, 1, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    plan_payload = json.loads((run_dir / "matrix_plan.json").read_text(encoding="utf-8"))
    results_payload = json.loads((run_dir / "matrix_results.json").read_text(encoding="utf-8"))

    assert run_dir.name == "20260220_200100-qwen3-voice-matrix"
    assert run_payload["status"] == "dry_run"
    assert plan_payload["execute"] is False
    assert len(plan_payload["presets"]) >= 1
    assert results_payload["note"] == "dry-run only"


def test_qwen3_voice_probe_matrix_execute_derives_unlock_gate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        matrix_probe,
        "PRESETS",
        {
            "combo-ready": {
                "python": "python-ready",
                "setup_commands": [],
                "description": "ready combo",
            },
            "combo-blocked": {
                "python": "python-blocked",
                "setup_commands": [],
                "description": "blocked combo",
            },
        },
    )

    def _fake_run(command):
        if command[0] == "python-ready":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "qwen3_asr": {"status": "supported"},
                        "qwen3_tts": {"status": "supported"},
                        "qwen3_tts_tokenizer_12hz": {"status": "supported"},
                    }
                ),
                stderr="",
            )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "qwen3_asr": {"status": "blocked_upstream"},
                    "qwen3_tts": {"status": "blocked_upstream"},
                    "qwen3_tts_tokenizer_12hz": {"status": "supported"},
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(matrix_probe, "_run_command", _fake_run)

    result = matrix_probe.run_qwen3_voice_probe_matrix(
        execute=True,
        with_setup=False,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 20, 20, 2, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    combos = {item["name"]: item for item in result["results_payload"]["combos"]}
    assert combos["combo-ready"]["unlock_ready"] is True
    assert combos["combo-ready"]["gate_status"] == "ready"
    assert combos["combo-blocked"]["unlock_ready"] is False
    assert combos["combo-blocked"]["gate_status"] == "blocked_upstream"
    assert result["results_payload"]["summary"]["unlock_ready"] == 1
