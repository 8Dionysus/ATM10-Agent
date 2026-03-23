from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.start_operator_product as start_operator_product


def test_build_startup_plan_uses_primary_operator_profile_defaults() -> None:
    args = start_operator_product.parse_args(["--print-plan-json"])
    plan = start_operator_product.build_startup_plan(args)

    assert plan["schema_version"] == "operator_product_startup_v1"
    assert plan["profile"] == "operator_product_core"
    assert plan["artifact_roots"]["operator_runs_dir"] == str(Path("runs"))
    assert plan["gateway"]["url"] == "http://127.0.0.1:8770"
    assert plan["streamlit"]["url"] == "http://127.0.0.1:8501"
    assert plan["gateway"]["runs_dir"] == str(Path("runs") / "gateway-http")
    assert plan["streamlit"]["runs_dir"] == str(Path("runs"))
    assert "scripts/gateway_v1_http_service.py" in plan["gateway"]["command"]
    assert "--operator-runs-dir" in plan["gateway"]["command"]
    assert "scripts/streamlit_operator_panel.py" in plan["streamlit"]["command"]
    assert "--operator-runs-dir" in plan["streamlit"]["command"]


def test_parse_args_derives_child_run_dirs_from_base_runs_dir(tmp_path: Path) -> None:
    args = start_operator_product.parse_args(["--runs-dir", str(tmp_path / "audit-root")])

    assert args.runs_dir == tmp_path / "audit-root"
    assert args.gateway_runs_dir == tmp_path / "audit-root" / "gateway-http"
    assert args.panel_runs_dir == tmp_path / "audit-root"
    assert args.voice_runtime_runs_dir == tmp_path / "audit-root" / "voice-runtime"
    assert args.tts_runtime_runs_dir == tmp_path / "audit-root" / "tts-runtime"
    assert args.pilot_runtime_runs_dir == tmp_path / "audit-root" / "pilot-runtime"


def test_parse_args_uses_qwen2_5_vl_7b_default_model_dir() -> None:
    args = start_operator_product.parse_args([])
    assert args.pilot_vlm_model_dir == Path("models") / "qwen2.5-vl-7b-instruct-int4-ov"
    assert args.pilot_vlm_device == "GPU"
    assert args.pilot_text_device == "NPU"


def test_parse_args_keeps_explicit_child_run_dir_overrides(tmp_path: Path) -> None:
    args = start_operator_product.parse_args(
        [
            "--runs-dir",
            str(tmp_path / "audit-root"),
            "--gateway-runs-dir",
            str(tmp_path / "explicit-gateway"),
            "--panel-runs-dir",
            str(tmp_path / "explicit-panel"),
            "--voice-runtime-runs-dir",
            str(tmp_path / "explicit-voice"),
            "--tts-runtime-runs-dir",
            str(tmp_path / "explicit-tts"),
        ]
    )

    assert args.gateway_runs_dir == tmp_path / "explicit-gateway"
    assert args.panel_runs_dir == tmp_path / "explicit-panel"
    assert args.voice_runtime_runs_dir == tmp_path / "explicit-voice"
    assert args.tts_runtime_runs_dir == tmp_path / "explicit-tts"


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


def test_build_startup_plan_tracks_combo_a_external_services() -> None:
    args = start_operator_product.parse_args(
        [
            "--qdrant-url",
            "http://127.0.0.1:6333",
            "--neo4j-url",
            "http://127.0.0.1:7474",
            "--neo4j-database",
            "neo4j",
            "--neo4j-user",
            "neo4j",
        ]
    )

    plan = start_operator_product.build_startup_plan(args)
    session_state = start_operator_product._build_initial_session_state(plan, Path("runs") / "startup")

    assert plan["external_services"]["qdrant"]["managed"] is False
    assert plan["external_services"]["qdrant"]["url"] == "http://127.0.0.1:6333"
    assert plan["external_services"]["neo4j"]["managed"] is False
    assert plan["external_services"]["neo4j"]["url"] == "http://127.0.0.1:7474"
    assert plan["external_services"]["neo4j"]["database"] == "neo4j"
    assert plan["external_services"]["neo4j"]["user"] == "neo4j"
    assert "--qdrant-url" in plan["gateway"]["command"]
    assert "--neo4j-url" in plan["gateway"]["command"]
    assert session_state["qdrant"]["status"] == "external"
    assert session_state["neo4j"]["status"] == "external"


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


def test_build_startup_plan_manages_opt_in_pilot_runtime() -> None:
    args = start_operator_product.parse_args(
        [
            "--start-voice-runtime",
            "--start-tts-runtime",
            "--start-pilot-runtime",
            "--pilot-hotkey",
            "F9",
            "--capture-monitor",
            "1",
            "--capture-region",
            "10,20,300,400",
        ]
    )
    plan = start_operator_product.build_startup_plan(args)
    pilot_plan = plan["managed_processes"]["pilot_runtime"]

    assert pilot_plan["managed"] is True
    assert pilot_plan["configured"] is True
    assert "scripts/pilot_runtime_loop.py" in pilot_plan["command"]
    assert "--pilot-hotkey" in pilot_plan["command"]
    assert "F9" in pilot_plan["command"]
    assert "--capture-monitor" in pilot_plan["command"]
    assert "1" in pilot_plan["command"]
    assert "--capture-region" in pilot_plan["command"]
    assert "10,20,300,400" in pilot_plan["command"]
    assert "--pilot-vlm-device" in pilot_plan["command"]
    assert "GPU" in pilot_plan["command"]
    assert "--pilot-text-device" in pilot_plan["command"]
    assert "NPU" in pilot_plan["command"]
    assert plan["artifact_roots"]["pilot_runtime_runs_dir"] == str(Path("runs") / "pilot-runtime")


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
        start_operator_product,
        "_wait_for_streamlit_ready",
        lambda streamlit_url, timeout_sec, process=None: ({"status": "ok", "url": streamlit_url.rstrip('/') + "/"}, None),
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
    assert Path(run_payload["paths"]["startup_plan_json"]).is_file()
    assert run_payload["managed_processes"]["voice_runtime_service"]["managed"] is True
    assert run_payload["session_state"]["gateway"]["status"] == "stopped"
    assert run_payload["session_state"]["voice_runtime_service"]["last_probe"]["status"] == "ok"
    assert run_payload["session_state"]["streamlit"]["status"] == "stopped"
    assert run_payload["session_state"]["streamlit"]["last_probe"]["status"] == "ok"
    assert run_payload["startup_checkpoints"]


def test_start_operator_product_smoke_managed_pilot_runtime_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launched_commands: list[list[str]] = []

    class _FakeProcess:
        _next_pid = 8000

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
        start_operator_product,
        "_wait_for_pilot_runtime_ready",
        lambda pilot_runs_dir, timeout_sec: ({"schema_version": "pilot_runtime_status_v1", "status": "running", "state": "idle"}, None),
    )
    monkeypatch.setattr(
        start_operator_product,
        "_wait_for_streamlit_ready",
        lambda streamlit_url, timeout_sec, process=None: ({"status": "ok", "url": streamlit_url.rstrip('/') + "/"}, None),
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
            "--start-pilot-runtime",
            "--pilot-hotkey",
            "F8",
        ]
    )

    assert exit_code == 0
    assert any("scripts/pilot_runtime_loop.py" in command for command in launched_commands)
    run_dirs = sorted((tmp_path / "runs").glob("*-start-operator-product*"))
    assert run_dirs
    run_payload = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_payload["managed_processes"]["pilot_runtime"]["managed"] is True
    assert run_payload["session_state"]["pilot_runtime"]["last_probe"]["status"] == "ok"


def test_start_operator_product_marks_never_launched_streamlit_not_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeProcess:
        _next_pid = 6000

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
        _ = command
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")
        return _FakeProcess()

    monkeypatch.setattr(start_operator_product, "_launch_process", _fake_launch_process)
    monkeypatch.setattr(
        start_operator_product,
        "_wait_for_gateway_operator_snapshot",
        lambda gateway_url, timeout_sec: (None, "gateway snapshot unavailable"),
    )

    exit_code = start_operator_product.main(
        [
            "--runs-dir",
            str(tmp_path / "runs"),
            "--gateway-runs-dir",
            str(tmp_path / "gateway"),
            "--panel-runs-dir",
            str(tmp_path / "panel"),
        ]
    )

    assert exit_code == 2
    run_dirs = sorted((tmp_path / "runs").glob("*-start-operator-product*"))
    assert run_dirs
    run_payload = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "error"
    assert run_payload["session_state"]["gateway"]["status"] == "error"
    assert run_payload["session_state"]["streamlit"]["status"] == "not_started"


def test_start_operator_product_marks_streamlit_probe_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeProcess:
        _next_pid = 7000

        def __init__(self) -> None:
            type(self)._next_pid += 1
            self.pid = type(self)._next_pid
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            return None

        def wait(self, timeout: float | None = None):
            self.returncode = 0
            return 0

        def kill(self):
            self.returncode = 1
            return None

    def _fake_launch_process(command: list[str], log_path: Path):
        _ = command
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")
        return _FakeProcess()

    monkeypatch.setattr(start_operator_product, "_launch_process", _fake_launch_process)
    monkeypatch.setattr(
        start_operator_product,
        "_wait_for_gateway_operator_snapshot",
        lambda gateway_url, timeout_sec: ({"status": "ok", "checked_at_utc": "2026-03-21T12:00:00+00:00"}, None),
    )
    monkeypatch.setattr(
        start_operator_product,
        "_wait_for_streamlit_ready",
        lambda streamlit_url, timeout_sec, process=None: (None, "streamlit startup timeout after 20.0s"),
    )

    exit_code = start_operator_product.main(
        [
            "--runs-dir",
            str(tmp_path / "runs"),
            "--gateway-runs-dir",
            str(tmp_path / "gateway"),
            "--panel-runs-dir",
            str(tmp_path / "panel"),
        ]
    )

    assert exit_code == 2
    run_dirs = sorted((tmp_path / "runs").glob("*-start-operator-product*"))
    assert run_dirs
    run_payload = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "error"
    assert run_payload["session_state"]["gateway"]["status"] == "stopped"
    assert run_payload["session_state"]["streamlit"]["status"] == "error"
    assert run_payload["session_state"]["streamlit"]["last_probe"]["status"] == "error"
    assert run_payload["session_state"]["streamlit"]["last_event"] == "probe_error"
    assert "streamlit startup timeout" in run_payload["session_state"]["streamlit"]["error"]


def test_start_operator_product_print_plan_json(capsys) -> None:
    exit_code = start_operator_product.main(["--print-plan-json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["schema_version"] == "operator_product_startup_v1"
    assert payload["profile"] == "operator_product_core"


def test_start_operator_product_script_entrypoint_print_plan_json() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/start_operator_product.py", "--print-plan-json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "operator_product_startup_v1"
    assert payload["profile"] == "operator_product_core"
