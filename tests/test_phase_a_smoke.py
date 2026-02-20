import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.phase_a_smoke import run_phase_a_smoke


def test_phase_a_smoke_creates_expected_artifacts(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    now = datetime(2026, 2, 19, 12, 30, 0, tzinfo=timezone.utc)

    result = run_phase_a_smoke(runs_dir=runs_dir, now=now)
    run_dir = result["run_dir"]

    screenshot_path = run_dir / "screenshot.png"
    run_json_path = run_dir / "run.json"
    response_json_path = run_dir / "response.json"

    assert run_dir.exists()
    assert screenshot_path.exists()
    assert run_json_path.exists()
    assert response_json_path.exists()

    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    response_payload = json.loads(response_json_path.read_text(encoding="utf-8"))

    assert run_payload["mode"] == "phase_a_smoke"
    assert run_payload["screen_source"] == "placeholder_png"
    assert run_payload["vlm"]["requested"] == "auto"
    assert run_payload["vlm"]["resolved"] == "stub"
    assert run_payload["vlm"]["fallback_used"] is False
    assert "timestamp_utc" in run_payload
    assert run_payload["paths"]["run_dir"] == str(run_dir)
    assert run_payload["paths"]["screenshot"] == str(screenshot_path)
    assert run_payload["paths"]["response_json"] == str(response_json_path)

    assert response_payload["provider"] == "deterministic_stub_v1"
    assert "summary" in response_payload
    assert isinstance(response_payload["next_steps"], list)
