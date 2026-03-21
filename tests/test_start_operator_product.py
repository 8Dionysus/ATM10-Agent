from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.start_operator_product as start_operator_product


def test_build_startup_plan_uses_primary_operator_profile_defaults() -> None:
    args = start_operator_product.parse_args(["--print-plan-json"])
    plan = start_operator_product.build_startup_plan(args)

    assert plan["schema_version"] == "operator_product_startup_v1"
    assert plan["profile"] == "operator_product_core"
    assert plan["gateway"]["url"] == "http://127.0.0.1:8770"
    assert plan["streamlit"]["url"] == "http://127.0.0.1:8501"
    assert "scripts/gateway_v1_http_service.py" in plan["gateway"]["command"]
    assert "scripts/streamlit_operator_panel.py" in plan["streamlit"]["command"]


def test_build_startup_plan_passes_optional_runtime_urls() -> None:
    args = start_operator_product.parse_args(
        [
            "--voice-runtime-url",
            "http://127.0.0.1:8765",
            "--tts-runtime-url",
            "http://127.0.0.1:8780",
        ]
    )
    plan = start_operator_product.build_startup_plan(args)
    assert "--voice-service-url" in plan["gateway"]["command"]
    assert "http://127.0.0.1:8765" in plan["gateway"]["command"]
    assert "--tts-service-url" in plan["gateway"]["command"]
    assert "http://127.0.0.1:8780" in plan["gateway"]["command"]


def test_build_startup_plan_manages_opt_in_runtimes() -> None:
    args = start_operator_product.parse_args(
        [
            "--start-voice-runtime",
            "--start-tts-runtime",
        ]
    )
    plan = start_operator_product.build_startup_plan(args)
    managed = plan["managed_processes"]
    assert managed["voice_runtime_service"]["managed"] is True
    assert managed["tts_runtime_service"]["managed"] is True
    assert managed["voice_runtime_service"]["url"] == "http://127.0.0.1:8765"
    assert managed["tts_runtime_service"]["url"] == "http://127.0.0.1:8780"
    assert "--voice-service-url" in plan["gateway"]["command"]
    assert "--tts-service-url" in plan["gateway"]["command"]


def test_parse_args_rejects_conflicting_voice_runtime_options() -> None:
    with pytest.raises(SystemExit):
        start_operator_product.parse_args(
            [
                "--start-voice-runtime",
                "--voice-runtime-url",
                "http://127.0.0.1:8765",
            ]
        )


def test_start_operator_product_smoke_managed_runtime_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launched_commands: list[list[str]] = []

    class _FakeProcess:
        _next_pid = 5000

        def __init__(self) -> None:
            type(self)._next_pid += 1
            self.pid = type(self)._next_pid

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout: float | None = None):
            return 0

        def kill(self):
            return None

    def _fake_launch_process(command: list[str], log_path: Path):
        launched_commands.append(list(command))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")
        return _FakeProcess()

    monkeypatch.setattr(start_operator_product, "_launch_process", _fake_launch_process)
    monkeypatch.setattr(
        start_operator_product,
        "_wait_for_runtime_health",
        lambda service_url, timeout_sec: ({"status": "ok"}, None),
    )
    monkeypatch.setattr(
        start_operator_product,
        "_wait_for_gateway_operator_snapshot",
        lambda gateway_url, timeout_sec: ({"status": "ok", "checked_at_utc": "2026-03-21T12:00:00+00:00"}, None),
    )
    monkeypatch.setattr(
        start_operator_product.time,
        "sleep",
        lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    exit_code = start_operator_product.main(
        [
            "--runs-dir",
            str(tmp_path / "runs"),
            "--gateway-runs-dir",
            str(tmp_path / "gateway"),
            "--panel-runs-dir",
            str(tmp_path / "panel"),
            "--start-voice-runtime",
            "--start-tts-runtime",
        ]
    )

    assert exit_code == 0
    assert any("scripts/voice_runtime_service.py" in command for command in launched_commands)
    assert any("scripts/tts_runtime_service.py" in command for command in launched_commands)
    assert any("scripts/gateway_v1_http_service.py" in command for command in launched_commands)
    assert any("scripts/streamlit_operator_panel.py" in command for command in launched_commands)
    run_dirs = sorted((tmp_path / "runs").glob("*-start-operator-product*"))
    assert run_dirs
    run_payload = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "stopped"
    assert run_payload["managed_processes"]["voice_runtime_service"]["managed"] is True


def test_start_operator_product_print_plan_json(capsys) -> None:
    exit_code = start_operator_product.main(["--print-plan-json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["schema_version"] == "operator_product_startup_v1"
    assert payload["profile"] == "operator_product_core"
