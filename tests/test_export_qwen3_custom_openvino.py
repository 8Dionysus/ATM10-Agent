import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import scripts.export_qwen3_custom_openvino as custom_export


def test_custom_export_vl_dry_run_writes_plan(tmp_path: Path) -> None:
    result = custom_export.run_export_qwen3_custom_openvino(
        preset_name="qwen3-vl-4b",
        execute=False,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=datetime(2026, 2, 20, 17, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    assert run_dir.name == "20260220_170000-qwen3-custom-export"
    assert (run_dir / "run.json").exists()
    assert (run_dir / "export_plan.json").exists()
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    plan_payload = json.loads((run_dir / "export_plan.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "dry_run"
    assert plan_payload["preset"] == "qwen3-vl-4b"
    assert plan_payload["task"] == "image-text-to-text"
    assert plan_payload["model_source"] == "Qwen/Qwen3-VL-4B-Instruct"


def test_custom_export_asr_execute_reports_probe_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        custom_export,
        "probe_architecture_support",
        lambda _model_id, _tag: {
            "supported": False,
            "status": "blocked_upstream",
            "error": "qwen3_asr unsupported in transformers",
        },
    )
    result = custom_export.run_export_qwen3_custom_openvino(
        preset_name="qwen3-asr-0.6b",
        execute=True,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=datetime(2026, 2, 20, 17, 1, 0, tzinfo=timezone.utc),
    )

    run_payload = result["run_payload"]
    plan_payload = result["plan_payload"]
    run_dir = result["run_dir"]
    assert result["ok"] is False
    assert run_payload["status"] == "blocked"
    assert run_payload["error_code"] == "unlock_gate_blocked"
    assert "qwen3_asr" in run_payload["error"]
    assert (run_dir / "export_stderr.log").read_text(encoding="utf-8") == "qwen3_asr unsupported in transformers"
    assert "qwen3_asr" in run_payload["diagnostic"]
    assert plan_payload["support_probe"]["status"] == "blocked_upstream"
    assert plan_payload["unlock_gate"]["ready"] is False
    assert run_payload["unlock_gate"]["observed_status"] == "blocked_upstream"


def test_custom_export_model_source_override_is_persisted(tmp_path: Path) -> None:
    result = custom_export.run_export_qwen3_custom_openvino(
        preset_name="qwen3-vl-4b",
        model_source="models/hf_raw/qwen3-vl-4b",
        execute=False,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=datetime(2026, 2, 20, 17, 2, 0, tzinfo=timezone.utc),
    )

    plan_payload = json.loads((result["run_dir"] / "export_plan.json").read_text(encoding="utf-8"))
    assert plan_payload["model_source"] == "models/hf_raw/qwen3-vl-4b"


def test_custom_export_asr_execute_success_uses_main_export(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        custom_export,
        "probe_architecture_support",
        lambda _model_id, _tag: {"supported": True, "status": "supported", "error": None},
    )

    def fake_main_export(**kwargs):
        calls.update(kwargs)

    monkeypatch.setattr(custom_export, "main_export", fake_main_export)

    result = custom_export.run_export_qwen3_custom_openvino(
        preset_name="qwen3-asr-0.6b",
        execute=True,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=datetime(2026, 2, 20, 17, 3, 0, tzinfo=timezone.utc),
    )

    run_payload = result["run_payload"]
    plan_payload = result["plan_payload"]
    run_dir = result["run_dir"]

    assert result["ok"] is True
    assert run_payload["status"] == "ok"
    assert run_payload["output_dir"].endswith("qwen3-asr-0.6b-ov-custom")
    assert plan_payload["path"] == "main_export"
    assert calls["model_name_or_path"] == "Qwen/Qwen3-ASR-0.6B"
    assert calls["task"] == "automatic-speech-recognition"
    assert (run_dir / "export_stdout.log").read_text(encoding="utf-8") == "Export completed successfully."
    assert (run_dir / "export_stderr.log").read_text(encoding="utf-8") == ""


def test_custom_export_asr_execute_failure_writes_diagnostic(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        custom_export,
        "probe_architecture_support",
        lambda _model_id, _tag: {"supported": True, "status": "supported", "error": None},
    )

    def failing_main_export(**kwargs):
        raise RuntimeError("unsupported architecture qwen3_asr")

    monkeypatch.setattr(custom_export, "main_export", failing_main_export)

    result = custom_export.run_export_qwen3_custom_openvino(
        preset_name="qwen3-asr-0.6b",
        execute=True,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=datetime(2026, 2, 20, 17, 4, 0, tzinfo=timezone.utc),
    )

    run_payload = result["run_payload"]
    run_dir = result["run_dir"]
    stderr_log = (run_dir / "export_stderr.log").read_text(encoding="utf-8")

    assert result["ok"] is False
    assert run_payload["status"] == "error"
    assert "qwen3_asr" in run_payload["error"]
    assert "qwen3_asr" in run_payload["diagnostic"]
    assert "RuntimeError" in stderr_log


def test_resolve_qwen_vl_export_types_prefers_modern_api(monkeypatch) -> None:
    fake_module = SimpleNamespace(
        Qwen3VLOpenVINOConfig=object(),
        Qwen2VLOpenVINOConfig=object(),
        QwenVLConfigBehavior=object(),
        Qwen2VLConfigBehavior=object(),
    )
    monkeypatch.setattr(custom_export.importlib, "import_module", lambda _name: fake_module)

    config_cls, behavior_cls = custom_export._resolve_qwen_vl_export_types()
    assert config_cls is fake_module.Qwen3VLOpenVINOConfig
    assert behavior_cls is fake_module.QwenVLConfigBehavior


def test_resolve_qwen_vl_export_types_falls_back_to_legacy_api(monkeypatch) -> None:
    fake_module = SimpleNamespace(
        Qwen2VLOpenVINOConfig=object(),
        Qwen2VLConfigBehavior=object(),
    )
    monkeypatch.setattr(custom_export.importlib, "import_module", lambda _name: fake_module)

    config_cls, behavior_cls = custom_export._resolve_qwen_vl_export_types()
    assert config_cls is fake_module.Qwen2VLOpenVINOConfig
    assert behavior_cls is fake_module.Qwen2VLConfigBehavior


def test_resolve_qwen_vl_export_types_supports_generic_qwenvl_names(monkeypatch) -> None:
    fake_module = SimpleNamespace(
        QwenVLOpenVINOConfig=object(),
        QwenVLConfigBehavior=object(),
    )
    monkeypatch.setattr(custom_export.importlib, "import_module", lambda _name: fake_module)

    config_cls, behavior_cls = custom_export._resolve_qwen_vl_export_types()
    assert config_cls is fake_module.QwenVLOpenVINOConfig
    assert behavior_cls is fake_module.QwenVLConfigBehavior


def test_custom_export_cli_help_works_when_run_as_script() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "export_qwen3_custom_openvino.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        text=True,
        cwd=repo_root,
        check=False,
    )

    assert result.returncode == 0
    assert "Custom OpenVINO export path" in result.stdout
