import json
from datetime import datetime, timezone
from pathlib import Path

import scripts.probe_qwen3_voice_support as probe


def test_classify_probe_error_marks_upstream_blocker() -> None:
    status = probe.classify_probe_error("unsupported architecture qwen3_asr", "qwen3_asr")
    assert status == probe.STATUS_BLOCKED_UPSTREAM


def test_probe_architecture_support_handles_import_error(monkeypatch) -> None:
    def _raise_import_error():
        raise ImportError("cannot import name 'is_offline_mode' from 'huggingface_hub'")

    monkeypatch.setattr(probe, "_resolve_transformers_autoconfig", _raise_import_error)
    result = probe.probe_architecture_support("Qwen/Qwen3-ASR-0.6B", "qwen3_asr")
    assert result["supported"] is False
    assert result["status"] == probe.STATUS_IMPORT_ERROR
    assert "transformers import failed" in (result["error"] or "")


def test_probe_architecture_support_reports_supported(monkeypatch) -> None:
    class _FakeAutoConfig:
        @staticmethod
        def from_pretrained(*_args, **_kwargs):
            return object()

    monkeypatch.setattr(probe, "_resolve_transformers_autoconfig", lambda: _FakeAutoConfig)
    result = probe.probe_architecture_support("Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", "qwen3_tts")
    assert result["supported"] is True
    assert result["status"] == probe.STATUS_SUPPORTED
    assert result["error"] is None


def test_run_probe_qwen3_voice_support_writes_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        probe,
        "probe_default_voice_stack",
        lambda **_kwargs: {
            "qwen3_asr": {"supported": False, "status": "blocked_upstream", "error": "qwen3_asr unsupported"},
            "qwen3_tts": {"supported": True, "status": "supported", "error": None},
            "qwen3_tts_tokenizer_12hz": {"supported": True, "status": "supported", "error": None},
        },
    )
    result = probe.run_probe_qwen3_voice_support(
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 20, 20, 0, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    probe_payload = json.loads((run_dir / "probe_results.json").read_text(encoding="utf-8"))
    assert run_dir.name == "20260220_200000-qwen3-voice-probe"
    assert run_payload["mode"] == "qwen3_voice_support_probe"
    assert run_payload["summary"]["qwen3_asr"]["status"] == "blocked_upstream"
    assert probe_payload["qwen3_tts"]["status"] == "supported"
