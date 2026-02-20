import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.export_qwen3_openvino as export_qwen3_openvino
from scripts.export_qwen3_openvino import PRESETS, run_export_qwen3_openvino


class _FakeCompletedProcess:
    def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_export_qwen3_openvino_dry_run_writes_plan(tmp_path: Path) -> None:
    now = datetime(2026, 2, 20, 16, 0, 0, tzinfo=timezone.utc)
    result = run_export_qwen3_openvino(
        preset_name="qwen3-vl-4b",
        execute=False,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=now,
    )

    run_dir = result["run_dir"]
    run_json = run_dir / "run.json"
    plan_json = run_dir / "export_plan.json"

    assert result["ok"] is True
    assert run_dir.name == "20260220_160000-qwen3-export"
    assert run_json.exists()
    assert plan_json.exists()

    run_payload = json.loads(run_json.read_text(encoding="utf-8"))
    plan_payload = json.loads(plan_json.read_text(encoding="utf-8"))

    assert run_payload["status"] == "dry_run"
    assert run_payload["preset"] == "qwen3-vl-4b"
    assert plan_payload["model_id"] == PRESETS["qwen3-vl-4b"]["model_id"]
    assert plan_payload["task"] == "image-text-to-text"
    assert plan_payload["weight_format"] == "int4"
    assert Path(plan_payload["command"][0]).name.lower() in {"optimum-cli", "optimum-cli.exe"}


def test_export_qwen3_openvino_execute_success_writes_logs(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(command: list[str], cwd: Path) -> _FakeCompletedProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        return _FakeCompletedProcess(returncode=0, stdout="ok stdout", stderr="")

    result = run_export_qwen3_openvino(
        preset_name="qwen3-asr-0.6b",
        execute=True,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=datetime(2026, 2, 20, 16, 1, 0, tzinfo=timezone.utc),
        runner=fake_runner,
    )

    run_dir = result["run_dir"]
    run_payload = result["run_payload"]

    assert result["ok"] is True
    assert run_payload["status"] == "ok"
    assert run_payload["returncode"] == 0
    assert (run_dir / "export_stdout.log").read_text(encoding="utf-8") == "ok stdout"
    assert (run_dir / "export_stderr.log").read_text(encoding="utf-8") == ""
    assert captured["command"] is not None


def test_export_qwen3_openvino_execute_handles_runner_exception(tmp_path: Path) -> None:
    def failing_runner(command: list[str], cwd: Path) -> _FakeCompletedProcess:
        raise FileNotFoundError("No such file or directory: optimum-cli")

    result = run_export_qwen3_openvino(
        preset_name="qwen3-vl-4b",
        execute=True,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=datetime(2026, 2, 20, 16, 2, 0, tzinfo=timezone.utc),
        runner=failing_runner,
    )

    run_payload = result["run_payload"]
    run_dir = result["run_dir"]
    assert result["ok"] is False
    assert run_payload["status"] == "error"
    assert run_payload["returncode"] is None
    assert "optimum-cli" in run_payload["error"]
    assert (run_dir / "export_stderr.log").read_text(encoding="utf-8").startswith("No such file")


def test_resolve_executable_falls_back_to_venv_scripts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_python = tmp_path / "python.exe"
    fake_python.write_text("", encoding="utf-8")
    fake_cli = tmp_path / "optimum-cli.exe"
    fake_cli.write_text("", encoding="utf-8")

    monkeypatch.setattr(export_qwen3_openvino.shutil, "which", lambda _: None)
    monkeypatch.setattr(sys, "executable", str(fake_python))

    resolved = export_qwen3_openvino._resolve_executable("optimum-cli")
    assert resolved == str(fake_cli)
