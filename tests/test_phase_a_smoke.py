import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.phase_a_smoke as phase_a_smoke
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


def test_phase_a_smoke_strict_vlm_failure_writes_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FailingVLM:
        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, object]:
            del image_path, prompt
            raise RuntimeError("forced_vlm_failure")

    def _fake_build_vlm_client(**kwargs) -> _FailingVLM:
        del kwargs
        return _FailingVLM()

    monkeypatch.setattr(phase_a_smoke, "_build_vlm_client", _fake_build_vlm_client)

    runs_dir = tmp_path / "runs"
    now = datetime(2026, 3, 2, 0, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(RuntimeError, match="forced_vlm_failure"):
        phase_a_smoke.run_phase_a_smoke(
            runs_dir=runs_dir,
            now=now,
            vlm_provider="openai",
            allow_vlm_fallback=False,
            openai_api_key="test",
            openai_api_base="http://127.0.0.1:9",
        )

    run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    run_json_path = run_dir / "run.json"
    response_json_path = run_dir / "response.json"

    assert run_json_path.exists()
    assert response_json_path.exists()

    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    response_payload = json.loads(response_json_path.read_text(encoding="utf-8"))
    assert run_payload["vlm"]["provider_failed"] == "openai"
    assert "forced_vlm_failure" in str(run_payload["vlm"]["fallback_reason"])
    assert response_payload["error_code"] == "vlm_provider_failed"
    assert "forced_vlm_failure" in str(response_payload["error"])
