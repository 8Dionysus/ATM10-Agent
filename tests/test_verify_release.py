from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.verify_release import (
    ReleaseVerificationError,
    inspect_sdist,
    inspect_wheel,
)


def _write_wheel(path: Path, *, requires_dist: list[str] | None = None, extra_root: str | None = None) -> None:
    metadata = [
        "Metadata-Version: 2.4",
        "Name: atm10-agent",
        "Version: 0.1.0",
        *(f"Requires-Dist: {spec}" for spec in (requires_dist or [])),
        "",
    ]
    with zipfile.ZipFile(path, "w") as archive:
        for package_path in (
            "atm10_agent/__init__.py",
            "atm10_agent/app.py",
            "atm10_agent/cli.py",
            "atm10_agent/data/default_world.jsonl",
            "atm10_agent/memory/consolidation.py",
            "atm10_agent/memory/model.py",
            "atm10_agent/memory/store.py",
            "atm10_agent/proof/evals.py",
            "atm10_agent/proof/measurements.py",
            "atm10_agent/proof/provenance.py",
            "atm10_agent/world/knowledge.py",
            "atm10_agent/windows_acceptance.py",
        ):
            archive.writestr(package_path, "")
        archive.writestr("atm10_agent-0.1.0.dist-info/METADATA", "\n".join(metadata))
        archive.writestr(
            "atm10_agent-0.1.0.dist-info/entry_points.txt",
            "[console_scripts]\natm10 = atm10_agent.cli:main\n",
        )
        if extra_root is not None:
            archive.writestr(f"{extra_root}/leak.py", "")


def _write_sdist(path: Path, *, omit: str | None = None) -> None:
    required = {
        "docs/intake/donor-ledger.json",
        "evals/manifest.json",
        "evals/suites/companion-core.json",
        "pylock.toml",
        "pyproject.toml",
        "schemas/donor_intake_ledger_v1.json",
        "schemas/windows_live_acceptance_v2.json",
        "schemas/windows_live_acceptance_verification_v1.json",
        "src/atm10_agent/app.py",
        "src/atm10_agent/cli.py",
        "src/atm10_agent/memory/consolidation.py",
        "src/atm10_agent/memory/model.py",
        "src/atm10_agent/memory/store.py",
        "src/atm10_agent/proof/evals.py",
        "src/atm10_agent/proof/measurements.py",
        "src/atm10_agent/proof/provenance.py",
        "src/atm10_agent/world/knowledge.py",
    }
    with tarfile.open(path, "w:gz") as archive:
        for relative in sorted(required - {omit}):
            content = b"{}\n" if relative.endswith(".json") else b"\n"
            member = tarfile.TarInfo(f"atm10-agent-0.1.0/{relative}")
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))


def test_inspect_wheel_accepts_dependency_free_core_with_optional_extras(tmp_path: Path) -> None:
    wheel = tmp_path / "atm10_agent-0.1.0-py3-none-any.whl"
    _write_wheel(
        wheel,
        requires_dist=['dxcam<1.0.0,>=0.3.0; extra == "windows"'],
    )

    result = inspect_wheel(wheel)

    assert result["name"] == "atm10-agent"
    assert result["core_requires_dist"] == []
    assert result["sha256"]


@pytest.mark.parametrize(
    ("requires_dist", "extra_root", "message"),
    [
        (["numpy>=2"], None, "unconditional dependencies"),
        ([], "scripts", "forbidden wheel roots"),
        ([], "tests", "forbidden wheel roots"),
    ],
)
def test_inspect_wheel_rejects_nonstandalone_boundaries(
    tmp_path: Path,
    requires_dist: list[str],
    extra_root: str | None,
    message: str,
) -> None:
    wheel = tmp_path / "atm10_agent-0.1.0-py3-none-any.whl"
    _write_wheel(wheel, requires_dist=requires_dist, extra_root=extra_root)

    with pytest.raises(ReleaseVerificationError, match=message):
        inspect_wheel(wheel)


def test_inspect_sdist_requires_public_contracts(tmp_path: Path) -> None:
    complete = tmp_path / "complete.tar.gz"
    _write_sdist(complete)

    result = inspect_sdist(complete)

    assert "schemas/windows_live_acceptance_v2.json" in result["required_source_paths"]
    assert (
        "schemas/windows_live_acceptance_verification_v1.json"
        in result["required_source_paths"]
    )
    assert "schemas/donor_intake_ledger_v1.json" in result["required_source_paths"]
    assert "docs/intake/donor-ledger.json" in result["required_source_paths"]

    incomplete = tmp_path / "incomplete.tar.gz"
    _write_sdist(
        incomplete,
        omit="schemas/windows_live_acceptance_verification_v1.json",
    )
    with pytest.raises(ReleaseVerificationError, match="sdist boundary failed"):
        inspect_sdist(incomplete)
