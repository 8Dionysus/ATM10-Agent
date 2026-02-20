import json
from datetime import datetime, timezone
from pathlib import Path

import scripts.export_qwen3_tts_openvino as tts_export


def test_tts_export_dry_run_writes_plan(tmp_path: Path) -> None:
    result = tts_export.run_export_qwen3_tts_openvino(
        execute=False,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=datetime(2026, 2, 20, 16, 5, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    plan_payload = json.loads((run_dir / "export_plan.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert run_dir.name == "20260220_160500-qwen3-tts-export"
    assert run_payload["status"] == "dry_run"
    assert plan_payload["preset"] == "qwen3-tts-12hz-0.6b"
    assert plan_payload["model_source"] == "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
    assert plan_payload["tokenizer_source"] == "Qwen/Qwen3-TTS-Tokenizer-12Hz"


def test_tts_export_source_override_is_persisted(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        tts_export,
        "probe_architecture_support",
        lambda _model_source, _tag: {"supported": True, "status": "supported", "error": None},
    )

    result = tts_export.run_export_qwen3_tts_openvino(
        execute=False,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        model_source="models/hf_raw/qwen3-tts-12hz-0.6b",
        tokenizer_source="models/hf_raw/qwen3-tts-tokenizer-12hz",
        now=datetime(2026, 2, 20, 16, 6, 0, tzinfo=timezone.utc),
    )

    plan_payload = json.loads((result["run_dir"] / "export_plan.json").read_text(encoding="utf-8"))
    assert plan_payload["model_source"] == "models/hf_raw/qwen3-tts-12hz-0.6b"
    assert plan_payload["tokenizer_source"] == "models/hf_raw/qwen3-tts-tokenizer-12hz"


def test_tts_export_execute_writes_diagnostic(monkeypatch, tmp_path: Path) -> None:
    def _probe(_model_source, tag):
        if tag == "qwen3_tts_tokenizer_12hz":
            return {"supported": True, "status": "supported", "error": None}
        return {"supported": False, "status": "blocked_upstream", "error": "unsupported architecture qwen3_tts"}

    monkeypatch.setattr(
        tts_export,
        "probe_architecture_support",
        _probe,
    )

    result = tts_export.run_export_qwen3_tts_openvino(
        execute=True,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=datetime(2026, 2, 20, 16, 7, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = result["run_payload"]
    stderr_log = (run_dir / "export_stderr.log").read_text(encoding="utf-8")

    assert result["ok"] is False
    assert run_payload["status"] == "blocked"
    assert run_payload["error_code"] == "unlock_gate_blocked"
    assert "unlock gate blocked" in run_payload["error"]
    assert "qwen3_tts" in run_payload["diagnostic"]
    assert "unsupported architecture qwen3_tts" in stderr_log


def test_tts_export_plan_contains_probe_statuses(monkeypatch, tmp_path: Path) -> None:
    def _probe(_model_source, tag):
        if tag == "qwen3_tts_tokenizer_12hz":
            return {"supported": False, "status": "import_error", "error": "transformers import failed"}
        return {"supported": False, "status": "blocked_upstream", "error": "unsupported architecture qwen3_tts"}

    monkeypatch.setattr(tts_export, "probe_architecture_support", _probe)

    result = tts_export.run_export_qwen3_tts_openvino(
        execute=False,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=datetime(2026, 2, 20, 16, 8, 0, tzinfo=timezone.utc),
    )

    plan_payload = json.loads((result["run_dir"] / "export_plan.json").read_text(encoding="utf-8"))
    assert plan_payload["model_probe"]["status"] == "blocked_upstream"
    assert plan_payload["tokenizer_probe"]["status"] == "import_error"
    assert plan_payload["unlock_gate"]["status"] == "import_error"
    assert plan_payload["unlock_gate"]["ready"] is False


def test_tts_export_execute_after_unlock_gate_reports_not_implemented(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        tts_export,
        "probe_architecture_support",
        lambda _model_source, _tag: {"supported": True, "status": "supported", "error": None},
    )

    result = tts_export.run_export_qwen3_tts_openvino(
        execute=True,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        now=datetime(2026, 2, 20, 16, 9, 0, tzinfo=timezone.utc),
    )

    run_payload = result["run_payload"]
    assert result["ok"] is False
    assert run_payload["status"] == "error"
    assert run_payload["error_code"] == "export_not_implemented"
    assert run_payload["unlock_gate"]["ready"] is True


def test_tts_export_notebook_helper_execute_success(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str, str]] = []

    class _FakeHelper:
        @staticmethod
        def convert_speech_tokenizer(source: str, output_dir: Path, use_local_dir: bool = False) -> None:
            calls.append(("tokenizer", source, str(output_dir)))

        @staticmethod
        def convert_qwen3_tts_model(
            source: str,
            output_dir: Path,
            quantization_config=None,
            use_local_dir: bool = False,
        ) -> None:
            calls.append(("model", source, str(output_dir)))

    monkeypatch.setattr(
        tts_export,
        "probe_architecture_support",
        lambda _model_source, _tag: {"supported": False, "status": "blocked_upstream", "error": "blocked"},
    )
    monkeypatch.setattr(tts_export.importlib, "import_module", lambda _name: _FakeHelper)

    result = tts_export.run_export_qwen3_tts_openvino(
        execute=True,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        backend=tts_export.BACKEND_NOTEBOOK_HELPER,
        helper_module_name="fake_helper",
        now=datetime(2026, 2, 20, 16, 10, 0, tzinfo=timezone.utc),
    )

    run_payload = result["run_payload"]
    plan_payload = result["plan_payload"]

    assert result["ok"] is True
    assert run_payload["status"] == "completed"
    assert len(run_payload["helper_steps"]) == 2
    assert run_payload["helper_steps"][0]["name"] == "convert_speech_tokenizer"
    assert run_payload["helper_steps"][1]["name"] == "convert_qwen3_tts_model"
    assert plan_payload["path"] == "notebook_helper_experimental"
    assert plan_payload["unlock_gate"]["ready"] is False
    assert calls[0][0] == "tokenizer"
    assert calls[1][0] == "model"


def test_tts_export_notebook_helper_execute_import_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        tts_export,
        "probe_architecture_support",
        lambda _model_source, _tag: {"supported": True, "status": "supported", "error": None},
    )

    def _raise_import_error(_name: str):
        raise ModuleNotFoundError("No module named 'qwen_3_tts_helper'")

    monkeypatch.setattr(tts_export.importlib, "import_module", _raise_import_error)

    result = tts_export.run_export_qwen3_tts_openvino(
        execute=True,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        backend=tts_export.BACKEND_NOTEBOOK_HELPER,
        helper_module_name="qwen_3_tts_helper",
        now=datetime(2026, 2, 20, 16, 11, 0, tzinfo=timezone.utc),
    )

    run_payload = result["run_payload"]

    assert result["ok"] is False
    assert run_payload["status"] == "error"
    assert run_payload["error_code"] == "notebook_helper_failed"
    assert "not importable" in run_payload["diagnostic"]


def test_tts_export_notebook_helper_execute_passes_quantization_config(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _FakeHelper:
        @staticmethod
        def convert_speech_tokenizer(source: str, output_dir: Path, use_local_dir: bool = False) -> None:
            captured["tokenizer_source"] = source

        @staticmethod
        def convert_qwen3_tts_model(
            source: str,
            output_dir: Path,
            quantization_config=None,
            use_local_dir: bool = False,
        ) -> None:
            captured["model_source"] = source
            captured["quantization_config"] = quantization_config

    monkeypatch.setattr(
        tts_export,
        "probe_architecture_support",
        lambda _model_source, _tag: {"supported": False, "status": "blocked_upstream", "error": "blocked"},
    )
    monkeypatch.setattr(tts_export.importlib, "import_module", lambda _name: _FakeHelper)
    monkeypatch.setattr(
        tts_export,
        "_resolve_helper_quantization_config",
        lambda mode: {"mode": f"resolved::{mode}"},
    )

    result = tts_export.run_export_qwen3_tts_openvino(
        execute=True,
        runs_dir=tmp_path / "runs",
        output_root=tmp_path / "models",
        backend=tts_export.BACKEND_NOTEBOOK_HELPER,
        weights_quantization=tts_export.WEIGHTS_QUANT_INT4_ASYM,
        now=datetime(2026, 2, 20, 16, 12, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    assert result["run_payload"]["status"] == "completed"
    assert result["plan_payload"]["weights_quantization"] == "int4_asym"
    assert captured["quantization_config"] == {"mode": "resolved::int4_asym"}
