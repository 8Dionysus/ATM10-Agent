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
        "requirements-core.txt",
        "requirements-win-edge.txt",
        "requirements-linux-dev.txt",
        "requirements-dev.txt",
        "requirements-voice.txt",
        "requirements-llm.txt",
        "requirements-export.txt",
        "requirements-audit.txt",
    ):
        assert (REPO_ROOT / name).exists(), f"Missing requirements file: {name}"


def test_requirements_profile_include_chain() -> None:
    default_lines = _normalized_lines(REPO_ROOT / "requirements.txt")
    win_edge_lines = _normalized_lines(REPO_ROOT / "requirements-win-edge.txt")
    linux_dev_lines = _normalized_lines(REPO_ROOT / "requirements-linux-dev.txt")
    dev_lines = _normalized_lines(REPO_ROOT / "requirements-dev.txt")
    voice_lines = _normalized_lines(REPO_ROOT / "requirements-voice.txt")
    llm_lines = _normalized_lines(REPO_ROOT / "requirements-llm.txt")
    export_lines = _normalized_lines(REPO_ROOT / "requirements-export.txt")

    assert default_lines[0] == "-r requirements-win-edge.txt"
    assert win_edge_lines[0] == "-r requirements-core.txt"
    assert linux_dev_lines[0] == "-r requirements-core.txt"
    assert dev_lines[0] == "-r requirements.txt"
    assert voice_lines[0] == "-r requirements-core.txt"
    assert llm_lines[0] == "-r requirements-core.txt"
    assert export_lines[0] == "-r requirements.txt"
    assert "-r requirements-llm.txt" not in export_lines


def test_requirements_profile_expected_packages_present() -> None:
    core_lines = _normalized_lines(REPO_ROOT / "requirements-core.txt")
    win_edge_lines = _normalized_lines(REPO_ROOT / "requirements-win-edge.txt")
    linux_dev_lines = _normalized_lines(REPO_ROOT / "requirements-linux-dev.txt")
    voice_lines = _normalized_lines(REPO_ROOT / "requirements-voice.txt")
    llm_lines = _normalized_lines(REPO_ROOT / "requirements-llm.txt")
    export_lines = _normalized_lines(REPO_ROOT / "requirements-export.txt")
    audit_lines = _normalized_lines(REPO_ROOT / "requirements-audit.txt")

    assert any(line.startswith("numpy") for line in core_lines)
    assert any(line.startswith("dxcam") for line in win_edge_lines)
    assert not any(line.startswith("dxcam") for line in core_lines)
    assert any(line.startswith("mss") for line in linux_dev_lines)
    assert any(line.startswith("openvino-genai") for line in voice_lines)
    assert any(line.startswith("torch") for line in voice_lines)
    assert any(line.startswith("TTS") for line in voice_lines)
    assert any(line.startswith("transformers") for line in llm_lines)
    assert any(line.startswith("torch") for line in export_lines)
    assert any(line.startswith("transformers") for line in export_lines)
    assert any(line.startswith("optimum") for line in export_lines)
    assert any(line.startswith("optimum-intel") for line in export_lines)
    assert any(line.startswith("nncf") for line in export_lines)
    assert any(line.startswith("pip-audit") for line in audit_lines)
