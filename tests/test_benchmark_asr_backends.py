from __future__ import annotations

import json
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

import scripts.benchmark_asr_backends as bench


def _write_test_wav(path: Path, *, sample_rate: int = 16000) -> None:
    t = np.linspace(0, 0.05, int(sample_rate * 0.05), endpoint=False)
    waveform = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    pcm16 = np.clip(waveform, -1.0, 1.0)
    pcm16 = (pcm16 * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())


def test_asr_backend_benchmark_writes_summary_and_records(tmp_path: Path) -> None:
    audio_1 = tmp_path / "a.wav"
    audio_2 = tmp_path / "b.wav"
    _write_test_wav(audio_1)
    _write_test_wav(audio_2)

    class _FakeQwenClient:
        def transcribe_path(self, *, audio_path: Path, context: str, language: str | None) -> dict[str, str]:
            assert context == ""
            assert language is None
            return {"text": f"qwen::{audio_path.stem}", "language": "en"}

    class _FakeWhisperClient:
        def transcribe_path(self, *, audio_path: Path, context: str, language: str | None) -> dict[str, str]:
            return {"text": f"whisper::{audio_path.stem}", "language": "en"}

    result = bench.run_asr_backend_benchmark(
        inputs=[audio_1, audio_2],
        manifest=None,
        backends=["qwen_asr", "whisper_genai"],
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 16, 0, 0, tzinfo=timezone.utc),
        backend_factories={
            "qwen_asr": lambda: _FakeQwenClient(),
            "whisper_genai": lambda: _FakeWhisperClient(),
        },
    )

    run_dir = result["run_dir"]
    assert run_dir.name == "20260222_160000-asr-backend-bench"
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "summary.md").exists()
    assert (run_dir / "per_sample_results.jsonl").exists()
    assert (run_dir / "service_sla_summary.json").exists()

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    service_sla = json.loads((run_dir / "service_sla_summary.json").read_text(encoding="utf-8"))
    assert summary["schema_version"] == "asr_backend_benchmark_summary_v1"
    assert summary["num_samples"] == 2
    assert summary["primary_backend"] == "whisper_genai"
    assert summary["per_backend"]["qwen_asr"]["num_ok"] == 2
    assert summary["per_backend"]["whisper_genai"]["num_ok"] == 2
    assert service_sla["schema_version"] == "service_sla_summary_v1"
    assert service_sla["service_name"] == "voice_asr"
    assert service_sla["backend"] == "whisper_genai"

    rows = [
        json.loads(line)
        for line in (run_dir / "per_sample_results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 4
    assert {row["backend"] for row in rows} == {"qwen_asr", "whisper_genai"}
    assert all(row["status"] == "ok" for row in rows)


def test_asr_backend_benchmark_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["benchmark_asr_backends.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        bench.parse_args()
    assert exc.value.code == 0


def test_benchmark_main_can_include_archived_qwen_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def _fake_run_asr_backend_benchmark(**kwargs):
        captured["backends"] = kwargs["backends"]
        return {"run_dir": tmp_path / "runs" / "fake", "ok": True}

    monkeypatch.setattr(bench, "run_asr_backend_benchmark", _fake_run_asr_backend_benchmark)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark_asr_backends.py",
            "--inputs",
            str(tmp_path / "sample.wav"),
            "--include-archived-qwen-asr",
        ],
    )

    exit_code = bench.main()
    assert exit_code == 0
    assert captured["backends"] == ["whisper_genai", "qwen_asr"]
