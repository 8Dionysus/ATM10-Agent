from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in _read_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def test_requirements_profile_files_exist() -> None:
    for name in (
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-voice.txt",
        "requirements-llm.txt",
        "requirements-export.txt",
        "requirements-audit.txt",
    ):
        assert (REPO_ROOT / name).exists(), f"Missing requirements file: {name}"


def test_requirements_profile_include_chain() -> None:
    voice_lines = _normalized_lines(REPO_ROOT / "requirements-voice.txt")
    llm_lines = _normalized_lines(REPO_ROOT / "requirements-llm.txt")
    export_lines = _normalized_lines(REPO_ROOT / "requirements-export.txt")

    assert voice_lines[0] == "-r requirements.txt"
    assert llm_lines[0] == "-r requirements.txt"
    assert export_lines[0] == "-r requirements-llm.txt"


def test_requirements_profile_expected_packages_present() -> None:
    base_lines = _normalized_lines(REPO_ROOT / "requirements.txt")
    voice_lines = _normalized_lines(REPO_ROOT / "requirements-voice.txt")
    llm_lines = _normalized_lines(REPO_ROOT / "requirements-llm.txt")
    export_lines = _normalized_lines(REPO_ROOT / "requirements-export.txt")
    audit_lines = _normalized_lines(REPO_ROOT / "requirements-audit.txt")

    assert any(line.startswith("numpy") for line in base_lines)
    assert any(line.startswith("openvino-genai") for line in voice_lines)
    assert any(line.startswith("torch") for line in voice_lines)
    assert any(line.startswith("TTS") for line in voice_lines)
    assert any(line.startswith("transformers") for line in llm_lines)
    assert any(line.startswith("optimum") for line in export_lines)
    assert any(line.startswith("optimum-intel") for line in export_lines)
    assert any(line.startswith("nncf") for line in export_lines)
    assert any(line.startswith("pip-audit") for line in audit_lines)
