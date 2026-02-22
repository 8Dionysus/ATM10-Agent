from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.hud_ocr_baseline as hud_ocr


def test_hud_ocr_baseline_writes_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    def _fake_which(binary_name: str) -> str:
        assert binary_name == "tesseract"
        return "C:\\Tools\\tesseract.exe"

    def _fake_run(cmd: list[str], **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="Quest Updated\nCollect 16 wood\n",
            stderr="",
        )

    monkeypatch.setattr(hud_ocr.shutil, "which", _fake_which)
    monkeypatch.setattr(hud_ocr.subprocess, "run", _fake_run)

    image_in = tmp_path / "hud.png"
    image_in.write_bytes(b"fake")

    result = hud_ocr.run_hud_ocr_baseline(
        image_in=image_in,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 19, 30, 0, tzinfo=timezone.utc),
    )

    run_dir = result["run_dir"]
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    ocr_payload = json.loads((run_dir / "ocr.json").read_text(encoding="utf-8"))
    ocr_text = (run_dir / "ocr.txt").read_text(encoding="utf-8")

    assert result["ok"] is True
    assert run_dir.name == "20260222_193000-hud-ocr"
    assert run_payload["status"] == "ok"
    assert ocr_payload["line_count"] == 2
    assert ocr_payload["lines"] == ["Quest Updated", "Collect 16 wood"]
    assert "Collect 16 wood" in ocr_text
    assert calls["cmd"] == [
        "C:\\Tools\\tesseract.exe",
        str(image_in),
        "stdout",
        "--psm",
        "6",
        "--oem",
        "1",
        "-l",
        "eng",
    ]


def test_hud_ocr_baseline_missing_tesseract_reports_dependency_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(hud_ocr.shutil, "which", lambda _: None)

    image_in = tmp_path / "hud.png"
    image_in.write_bytes(b"fake")
    result = hud_ocr.run_hud_ocr_baseline(
        image_in=image_in,
        runs_dir=tmp_path / "runs",
        now=datetime(2026, 2, 22, 19, 31, 0, tzinfo=timezone.utc),
    )

    assert result["ok"] is False
    assert result["run_payload"]["error_code"] == "runtime_missing_dependency"


def test_hud_ocr_baseline_cli_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["hud_ocr_baseline.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        hud_ocr.parse_args()
    assert exc.value.code == 0
