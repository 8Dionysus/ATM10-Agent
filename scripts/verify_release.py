"""Verify ATM10 release artifacts and smoke the dependency-free wheel.

The verifier deliberately runs the installed CLI from a temporary environment
whose working directory is outside the repository. This makes repository-path
imports and undeclared core dependencies visible before release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path
from typing import Any, Mapping, Sequence


RELEASE_VERIFICATION_SCHEMA = "atm10_release_verification_v1"
REQUIRED_WHEEL_PATHS = {
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
    "atm10_agent/providers/promotion.py",
    "atm10_agent/providers/routing.py",
    "atm10_agent/world/knowledge.py",
    "atm10_agent/windows_acceptance.py",
}
FORBIDDEN_WHEEL_ROOTS = {"scripts", "tests", ".aoa"}


class ReleaseVerificationError(RuntimeError):
    """Raised when a release artifact violates the standalone contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _only_artifact(dist_dir: Path, pattern: str, label: str) -> Path:
    matches = sorted(dist_dir.glob(pattern))
    if len(matches) != 1:
        raise ReleaseVerificationError(
            f"expected exactly one {label} in {dist_dir}, found {len(matches)}"
        )
    return matches[0]


def _wheel_metadata(archive: zipfile.ZipFile) -> tuple[str, bytes]:
    candidates = [
        name
        for name in archive.namelist()
        if name.endswith(".dist-info/METADATA") and name.count("/") == 1
    ]
    if len(candidates) != 1:
        raise ReleaseVerificationError(
            f"wheel must contain exactly one dist-info/METADATA, found {len(candidates)}"
        )
    metadata_path = candidates[0]
    return metadata_path, archive.read(metadata_path)


def inspect_wheel(wheel_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(wheel_path) as archive:
        names = sorted(name.rstrip("/") for name in archive.namelist() if name.rstrip("/"))
        top_roots = {name.split("/", 1)[0] for name in names}
        forbidden_roots = sorted(top_roots & FORBIDDEN_WHEEL_ROOTS)
        forbidden_generated = sorted(
            name for name in names if name.endswith(".pyc") or "/__pycache__/" in f"/{name}/"
        )
        missing_paths = sorted(REQUIRED_WHEEL_PATHS - set(names))
        entry_points = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        metadata_path, metadata_bytes = _wheel_metadata(archive)
        metadata = BytesParser(policy=email_policy).parsebytes(metadata_bytes)
        requires_dist = metadata.get_all("Requires-Dist", [])
        unconditional = sorted(spec for spec in requires_dist if "extra ==" not in spec)

        issues: list[str] = []
        if forbidden_roots:
            issues.append(f"forbidden wheel roots: {forbidden_roots}")
        if forbidden_generated:
            issues.append(f"generated Python files in wheel: {forbidden_generated}")
        if missing_paths:
            issues.append(f"required package files missing from wheel: {missing_paths}")
        if len(entry_points) != 1:
            issues.append(f"expected one entry_points.txt, found {len(entry_points)}")
        elif "atm10 = atm10_agent.cli:main" not in archive.read(entry_points[0]).decode("utf-8"):
            issues.append("atm10 console entry point is missing")
        if unconditional:
            issues.append(f"core wheel has unconditional dependencies: {unconditional}")
        if issues:
            raise ReleaseVerificationError("; ".join(issues))

        return {
            "path": str(wheel_path),
            "sha256": _sha256(wheel_path),
            "file_count": len(names),
            "metadata_path": metadata_path,
            "name": metadata.get("Name"),
            "version": metadata.get("Version"),
            "core_requires_dist": [],
            "optional_requires_dist": sorted(requires_dist),
            "required_package_paths": sorted(REQUIRED_WHEEL_PATHS),
        }


def inspect_sdist(sdist_path: Path) -> dict[str, Any]:
    with tarfile.open(sdist_path, "r:*") as archive:
        names = sorted(member.name.rstrip("/") for member in archive.getmembers() if member.name.rstrip("/"))
    relative_names = {
        name.split("/", 1)[1]
        for name in names
        if "/" in name
    }
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
        "src/atm10_agent/providers/promotion.py",
        "src/atm10_agent/providers/routing.py",
        "src/atm10_agent/world/knowledge.py",
    }
    missing = sorted(required - relative_names)
    forbidden = sorted(
        name
        for name in relative_names
        if name == ".aoa"
        or name.startswith(".aoa/")
        or Path(name).name.startswith("requirements") and name.endswith(".txt")
    )
    if missing or forbidden:
        raise ReleaseVerificationError(
            f"sdist boundary failed: missing={missing}, forbidden={forbidden}"
        )
    return {
        "path": str(sdist_path),
        "sha256": _sha256(sdist_path),
        "file_count": len(names),
        "required_source_paths": sorted(required),
    }


def _run_checked(command: Sequence[str], *, cwd: Path, env: Mapping[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        list(command),
        cwd=str(cwd),
        env=dict(env),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseVerificationError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return {
        "command": [str(part) for part in command],
        "returncode": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr.encode("utf-8")).hexdigest(),
    }


def smoke_installed_wheel(wheel_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="atm10-release-") as raw_temp:
        temp_root = Path(raw_temp).resolve()
        env_dir = temp_root / "venv"
        work_dir = temp_root / "work"
        work_dir.mkdir()
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
        python_path = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        atm10_path = env_dir / ("Scripts/atm10.exe" if os.name == "nt" else "bin/atm10")
        env = {
            **os.environ,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        commands: list[dict[str, Any]] = []
        commands.append(
            _run_checked(
                [
                    str(python_path),
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "--disable-pip-version-check",
                    str(wheel_path.resolve()),
                ],
                cwd=work_dir,
                env=env,
            )
        )
        commands.append(_run_checked([str(atm10_path), "doctor"], cwd=work_dir, env=env))
        commands.append(
            _run_checked(
                [
                    str(atm10_path),
                    "verify-windows-acceptance",
                    "--help",
                ],
                cwd=work_dir,
                env=env,
            )
        )
        commands.append(
            _run_checked(
                [
                    str(atm10_path),
                    "run",
                    "--prompt",
                    "Describe ATM10 context.",
                    "--query",
                    "steel tools",
                    "--action-intent",
                    "open_quest_book",
                    "--runs-dir",
                    "runs",
                    "--state-dir",
                    "state",
                ],
                cwd=work_dir,
                env=env,
            )
        )
        turn_paths = sorted((work_dir / "runs").rglob("turn.json"))
        if len(turn_paths) != 1:
            raise ReleaseVerificationError(
                f"installed run must produce exactly one turn.json, found {len(turn_paths)}"
            )
        commands.append(
            _run_checked(
                [
                    str(atm10_path),
                    "replay",
                    str(turn_paths[0]),
                    "--runs-dir",
                    "replay-runs",
                    "--state-dir",
                    "state",
                ],
                cwd=work_dir,
                env=env,
            )
        )
        commands.append(
            _run_checked(
                [
                    str(atm10_path),
                    "eval",
                    "--suite",
                    "companion-core",
                    "--runs-dir",
                    "eval-runs",
                    "--state-dir",
                    "eval-state",
                    "--reports-dir",
                    "eval-reports",
                ],
                cwd=work_dir,
                env=env,
            )
        )
        commands.append(
            _run_checked(
                [
                    str(atm10_path),
                    "consolidate-memory",
                    "--memory-dir",
                    ".atm10-memory",
                    "--now",
                    "2026-07-25T13:00:00Z",
                ],
                cwd=work_dir,
                env=env,
            )
        )
        module_probe = _run_checked(
            [
                str(python_path),
                "-c",
                (
                    "import atm10_agent, pathlib; "
                    "from atm10_agent.providers import ProviderEvidence, select_provider; "
                    "print(pathlib.Path(atm10_agent.__file__).resolve(), "
                    "ProviderEvidence.__name__, select_provider.__name__)"
                ),
            ],
            cwd=work_dir,
            env=env,
        )
        commands.append(module_probe)
        return {
            "status": "pass",
            "working_directory_outside_repository": True,
            "python_no_user_site": True,
            "install_mode": "wheel_no_deps",
            "commands": commands,
        }


def verify_release(*, dist_dir: Path, report_path: Path | None = None, smoke: bool = True) -> dict[str, Any]:
    resolved_dist = dist_dir.resolve()
    wheel_path = _only_artifact(resolved_dist, "*.whl", "wheel")
    sdist_path = _only_artifact(resolved_dist, "*.tar.gz", "sdist")
    payload: dict[str, Any] = {
        "schema_version": RELEASE_VERIFICATION_SCHEMA,
        "status": "pass",
        "wheel": inspect_wheel(wheel_path),
        "sdist": inspect_sdist(sdist_path),
        "standalone_smoke": smoke_installed_wheel(wheel_path) if smoke else {"status": "skipped"},
        "claim_limit": (
            "Proves dependency-free core artifact structure and deterministic installed-wheel behavior; "
            "does not prove optional providers or live Windows capture."
        ),
    }
    destination = (report_path or (resolved_dist / "release_verification.json")).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify ATM10 wheel/sdist and standalone installed-wheel behavior.")
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--no-smoke", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = verify_release(
            dist_dir=args.dist_dir,
            report_path=args.report,
            smoke=not args.no_smoke,
        )
    except ReleaseVerificationError as exc:
        print(f"[verify_release] failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
