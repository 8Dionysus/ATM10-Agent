from __future__ import annotations

import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _dependency_names(specs: list[str]) -> set[str]:
    names: set[str] = set()
    for spec in specs:
        name = spec.split("[", 1)[0]
        for separator in ("<", ">", "=", "!", "~", ";"):
            name = name.split(separator, 1)[0]
        names.add(name.strip().lower().replace("_", "-"))
    return names


def test_pyproject_is_the_only_dependency_authority() -> None:
    payload = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = payload["project"]

    assert project["dependencies"] == []
    assert not list(REPO_ROOT.glob("requirements*.txt"))


def test_core_lock_resolves_only_the_local_dependency_free_package() -> None:
    lock = tomllib.loads((REPO_ROOT / "pylock.toml").read_text(encoding="utf-8"))

    assert lock["lock-version"] == "1.0"
    assert lock["packages"] == [
        {"name": "atm10-agent", "directory": {"path": "."}},
    ]


def test_optional_dependency_groups_match_replaceable_provider_boundaries() -> None:
    payload = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    groups = payload["project"]["optional-dependencies"]

    assert set(groups) == {"windows", "openvino", "voice", "rerank", "export", "audit", "dev"}
    assert _dependency_names(groups["windows"]) == {"dxcam", "numpy", "pillow"}
    assert {"openvino", "openvino-genai", "numpy", "pillow"} <= _dependency_names(groups["openvino"])
    assert {"librosa", "numpy", "openvino-genai", "sounddevice", "torch"} <= _dependency_names(groups["voice"])
    assert {"openvino", "torch", "transformers"} <= _dependency_names(groups["rerank"])
    assert {"nncf", "optimum", "optimum-intel", "torch", "transformers"} <= _dependency_names(groups["export"])
    assert _dependency_names(groups["audit"]) == {"pip-audit"}
    assert {"build", "jsonschema", "pytest", "wheel"} <= _dependency_names(groups["dev"])


def test_dxcam_is_confined_to_the_windows_extra() -> None:
    payload = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    groups = payload["project"]["optional-dependencies"]

    owners = [name for name, specs in groups.items() if "dxcam" in _dependency_names(specs)]
    assert owners == ["windows"]
