from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import scripts.benchmark_pilot_openvino_devices as benchmark


def test_parse_args_uses_active_stack_defaults() -> None:
    args = benchmark.parse_args([])

    assert args.vision_model_dir == Path("models") / "qwen2.5-vl-7b-instruct-int4-ov"
    assert args.text_model_dir == Path("models") / "qwen3-8b-int4-cw-ov"
    assert args.vision_devices == "GPU,CPU,NPU"
    assert args.text_devices == "NPU,CPU,GPU"
    assert args.image_path is None
    assert args.runs_dir == Path("runs")


def test_run_benchmark_writes_artifacts_and_tolerates_unsupported_devices(
    tmp_path: Path, monkeypatch
) -> None:
    class _FakeVLMClient:
        def __init__(self, device: str) -> None:
            self.device = device

        def analyze_image(self, *, image_path: Path, prompt: str) -> dict[str, object]:
            assert image_path.is_file()
            assert prompt
            return {
                "summary": f"vision on {self.device}",
                "next_steps": [],
            }

    class _FakeReplyClient:
        def __init__(self, device: str) -> None:
            self.device = device

        def generate_reply(
            self,
            *,
            transcript: str,
            visual_summary: str | None,
            citations: list[object],
            hybrid_summary: dict[str, object] | None,
            degraded_flags: list[str],
            preferred_language: str | None,
        ) -> dict[str, object]:
            assert transcript
            assert preferred_language == "ru"
            _ = citations, hybrid_summary, degraded_flags
            return {
                "answer_text": f"reply on {self.device}: {visual_summary}",
            }

    def _fake_vlm_factory(*, model_dir: Path, device: str, max_new_tokens: int, temperature: float):
        assert model_dir == Path("models") / "vision"
        assert max_new_tokens == 64
        assert temperature == 0.0
        if device == "NPU":
            raise RuntimeError("unsupported device for benchmark")
        return _FakeVLMClient(device)

    def _fake_reply_factory(*, model_dir: Path, device: str, max_new_tokens: int, temperature: float):
        assert model_dir == Path("models") / "text"
        assert max_new_tokens == 96
        assert temperature == 0.1
        return _FakeReplyClient(device)

    perf_values = iter([0.0, 0.01, 0.02, 0.05, 0.06, 0.12])
    monkeypatch.setattr(benchmark, "perf_counter", lambda: next(perf_values))

    summary = benchmark.run_pilot_openvino_device_benchmark(
        vision_model_dir=Path("models") / "vision",
        text_model_dir=Path("models") / "text",
        vision_devices=["GPU", "NPU"],
        text_devices=["CPU"],
        runs_dir=tmp_path,
        now=datetime(2026, 3, 24, 22, 0, 0, tzinfo=timezone.utc),
        vlm_client_factory=_fake_vlm_factory,
        grounded_reply_client_factory=_fake_reply_factory,
    )

    assert summary["status"] == "ok"
    assert summary["recommendations"]["vision"]["recommended_device"] == "GPU"
    assert summary["recommendations"]["grounded_reply"]["recommended_device"] == "CPU"

    run_dir = Path(summary["paths"]["run_dir"])
    assert (run_dir / "run.json").is_file()
    assert (run_dir / "benchmark_plan.json").is_file()
    assert (run_dir / "per_case_results.jsonl").is_file()
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "summary.md").is_file()
    assert (run_dir / "fixtures" / "generated_benchmark_screen.png").is_file()

    rows = summary["rows"]
    assert any(row["stage"] == "vision" and row["device"] == "GPU" and row["ok"] is True for row in rows)
    assert any(
        row["stage"] == "vision" and row["device"] == "NPU" and row["ok"] is False and row["error_code"] == "unsupported_device"
        for row in rows
    )
    assert any(row["stage"] == "grounded_reply" and row["device"] == "CPU" and row["ok"] is True for row in rows)
    assert any(
        row["stage"] == "combined" and row["device"] == "vision=GPU;text=CPU" and row["ok"] is True
        for row in rows
    )

    per_case_rows = [
        json.loads(line)
        for line in (run_dir / "per_case_results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(per_case_rows) == 4
