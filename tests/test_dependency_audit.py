from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.dependency_audit import run_dependency_audit


class _FakeCompletedProcess:
    def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_dependency_audit_report_only_creates_artifacts_and_keeps_zero_exit(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runs_dir = tmp_path / "runs"
    requirements_path = repo_root / "requirements.txt"
    _write_text(repo_root / "scripts" / "app.py", "import fastapi\nimport numpy\n")
    _write_text(requirements_path, "numpy>=2.0.0,<3.0.0\n")

    def _runner(command: list[str], _cwd: Path) -> _FakeCompletedProcess:
        if command[:4] == [command[0], "-m", "pip", "check"]:
            return _FakeCompletedProcess(returncode=0, stdout="No broken requirements found.\n")
        if command[:3] == [command[0], "-m", "pip_audit"]:
            return _FakeCompletedProcess(returncode=0, stdout="[]")
        raise AssertionError(f"Unexpected command: {command}")

    result = run_dependency_audit(
        runs_dir=runs_dir,
        policy="report_only",
        with_security_scan=True,
        requirements_files=[requirements_path],
        now=datetime(2026, 3, 2, 15, 0, 0, tzinfo=timezone.utc),
        command_runner=_runner,
        repo_root=repo_root,
        scan_roots=[repo_root / "scripts", repo_root / "src", repo_root / "tests"],
        installed_packages={"numpy"},
    )

    run_dir = result["run_dir"]
    assert run_dir.name == "20260302_150000-dependency-audit"
    assert result["run_payload"]["exit_code"] == 0
    assert result["ok"] is True
    assert (run_dir / "run.json").exists()
    assert (run_dir / "dependency_inventory.json").exists()
    assert (run_dir / "dependency_findings.json").exists()
    assert (run_dir / "security_audit.json").exists()
    assert (run_dir / "summary.md").exists()

    findings_payload = json.loads((run_dir / "dependency_findings.json").read_text(encoding="utf-8"))
    assert findings_payload["summary"]["error_count"] >= 1
    assert any(item["code"] == "missing_runtime_dependency" for item in findings_payload["findings"])

    security_payload = json.loads((run_dir / "security_audit.json").read_text(encoding="utf-8"))
    assert security_payload["status"] == "ok"
    assert security_payload["vulnerabilities_count"] == 0


def test_dependency_audit_accepts_object_shaped_pip_audit_payload(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runs_dir = tmp_path / "runs"
    requirements_path = repo_root / "requirements.txt"
    _write_text(repo_root / "scripts" / "app.py", "import numpy\n")
    _write_text(requirements_path, "numpy>=2.0.0,<3.0.0\n")

    def _runner(command: list[str], _cwd: Path) -> _FakeCompletedProcess:
        if command[:4] == [command[0], "-m", "pip", "check"]:
            return _FakeCompletedProcess(returncode=0, stdout="No broken requirements found.\n")
        if command[:3] == [command[0], "-m", "pip_audit"]:
            return _FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps({"dependencies": [{"name": "numpy", "vulns": []}]}),
            )
        raise AssertionError(f"Unexpected command: {command}")

    result = run_dependency_audit(
        runs_dir=runs_dir,
        policy="report_only",
        with_security_scan=True,
        requirements_files=[requirements_path],
        now=datetime(2026, 3, 2, 15, 0, 30, tzinfo=timezone.utc),
        command_runner=_runner,
        repo_root=repo_root,
        scan_roots=[repo_root / "scripts", repo_root / "src", repo_root / "tests"],
        installed_packages={"numpy"},
    )

    assert result["ok"] is True
    assert result["security_payload"]["status"] == "ok"
    assert result["security_payload"]["vulnerabilities_count"] == 0
    assert result["security_payload"]["vulnerabilities"] == [{"name": "numpy", "vulns": []}]
    assert not any(item["code"] == "security_scan_warn" for item in result["findings_payload"]["findings"])

    run_dir = result["run_dir"]
    security_payload = json.loads((run_dir / "security_audit.json").read_text(encoding="utf-8"))
    assert security_payload["vulnerabilities"] == [{"name": "numpy", "vulns": []}]


def test_dependency_audit_warns_on_object_payload_missing_dependencies_key(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runs_dir = tmp_path / "runs"
    requirements_path = repo_root / "requirements.txt"
    _write_text(repo_root / "scripts" / "app.py", "import numpy\n")
    _write_text(requirements_path, "numpy>=2.0.0,<3.0.0\n")

    def _runner(command: list[str], _cwd: Path) -> _FakeCompletedProcess:
        if command[:4] == [command[0], "-m", "pip", "check"]:
            return _FakeCompletedProcess(returncode=0, stdout="No broken requirements found.\n")
        if command[:3] == [command[0], "-m", "pip_audit"]:
            return _FakeCompletedProcess(returncode=0, stdout=json.dumps({"schema_version": "unknown"}))
        raise AssertionError(f"Unexpected command: {command}")

    result = run_dependency_audit(
        runs_dir=runs_dir,
        policy="report_only",
        with_security_scan=True,
        requirements_files=[requirements_path],
        now=datetime(2026, 3, 2, 15, 0, 45, tzinfo=timezone.utc),
        command_runner=_runner,
        repo_root=repo_root,
        scan_roots=[repo_root / "scripts", repo_root / "src", repo_root / "tests"],
        installed_packages={"numpy"},
    )

    assert result["ok"] is True
    assert result["security_payload"]["status"] == "warn"
    assert "dependencies" in str(result["security_payload"]["error"])
    assert any(item["code"] == "security_scan_warn" for item in result["findings_payload"]["findings"])


def test_dependency_audit_fail_on_critical_treats_missing_dependencies_key_as_error(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runs_dir = tmp_path / "runs"
    requirements_path = repo_root / "requirements.txt"
    _write_text(repo_root / "scripts" / "app.py", "import numpy\n")
    _write_text(requirements_path, "numpy>=2.0.0,<3.0.0\n")

    def _runner(command: list[str], _cwd: Path) -> _FakeCompletedProcess:
        if command[:4] == [command[0], "-m", "pip", "check"]:
            return _FakeCompletedProcess(returncode=0, stdout="No broken requirements found.\n")
        if command[:3] == [command[0], "-m", "pip_audit"]:
            return _FakeCompletedProcess(returncode=0, stdout=json.dumps({"schema_version": "unknown"}))
        raise AssertionError(f"Unexpected command: {command}")

    result = run_dependency_audit(
        runs_dir=runs_dir,
        policy="fail_on_critical",
        with_security_scan=True,
        requirements_files=[requirements_path],
        now=datetime(2026, 3, 2, 15, 0, 50, tzinfo=timezone.utc),
        command_runner=_runner,
        repo_root=repo_root,
        scan_roots=[repo_root / "scripts", repo_root / "src", repo_root / "tests"],
        installed_packages={"numpy"},
    )

    assert result["security_payload"]["status"] == "warn"
    assert result["run_payload"]["exit_code"] == 2
    assert result["ok"] is False


def test_dependency_audit_warns_when_pip_audit_is_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runs_dir = tmp_path / "runs"
    requirements_path = repo_root / "requirements.txt"
    _write_text(repo_root / "scripts" / "app.py", "import numpy\n")
    _write_text(requirements_path, "numpy>=2.0.0,<3.0.0\n")

    def _runner(command: list[str], _cwd: Path) -> _FakeCompletedProcess:
        if command[:4] == [command[0], "-m", "pip", "check"]:
            return _FakeCompletedProcess(returncode=0, stdout="No broken requirements found.\n")
        if command[:3] == [command[0], "-m", "pip_audit"]:
            return _FakeCompletedProcess(returncode=1, stderr="No module named pip_audit")
        raise AssertionError(f"Unexpected command: {command}")

    result = run_dependency_audit(
        runs_dir=runs_dir,
        policy="report_only",
        with_security_scan=True,
        requirements_files=[requirements_path],
        now=datetime(2026, 3, 2, 15, 1, 0, tzinfo=timezone.utc),
        command_runner=_runner,
        repo_root=repo_root,
        scan_roots=[repo_root / "scripts", repo_root / "src", repo_root / "tests"],
        installed_packages={"numpy"},
    )

    assert result["run_payload"]["exit_code"] == 0
    assert result["ok"] is True
    assert result["security_payload"]["status"] == "warn"
    assert "pip-audit" in str(result["security_payload"]["error"])
    assert any(item["code"] == "security_scan_warn" for item in result["findings_payload"]["findings"])


def test_dependency_audit_fail_on_critical_returns_nonzero(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runs_dir = tmp_path / "runs"
    requirements_path = repo_root / "requirements.txt"
    _write_text(repo_root / "scripts" / "app.py", "import fastapi\n")
    _write_text(requirements_path, "numpy>=2.0.0,<3.0.0\n")

    def _runner(command: list[str], _cwd: Path) -> _FakeCompletedProcess:
        if command[:4] == [command[0], "-m", "pip", "check"]:
            return _FakeCompletedProcess(returncode=0, stdout="No broken requirements found.\n")
        raise AssertionError(f"Unexpected command: {command}")

    result = run_dependency_audit(
        runs_dir=runs_dir,
        policy="fail_on_critical",
        with_security_scan=False,
        requirements_files=[requirements_path],
        now=datetime(2026, 3, 2, 15, 2, 0, tzinfo=timezone.utc),
        command_runner=_runner,
        repo_root=repo_root,
        scan_roots=[repo_root / "scripts", repo_root / "src", repo_root / "tests"],
        installed_packages={"numpy"},
    )

    assert result["ok"] is False
    assert result["run_payload"]["exit_code"] == 2
    assert result["findings_payload"]["summary"]["error_count"] >= 1


def test_dependency_audit_fail_on_critical_requires_pip_audit_tool(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runs_dir = tmp_path / "runs"
    requirements_path = repo_root / "requirements.txt"
    _write_text(repo_root / "scripts" / "app.py", "import numpy\n")
    _write_text(requirements_path, "numpy>=2.0.0,<3.0.0\n")

    def _runner(command: list[str], _cwd: Path) -> _FakeCompletedProcess:
        if command[:4] == [command[0], "-m", "pip", "check"]:
            return _FakeCompletedProcess(returncode=0, stdout="No broken requirements found.\n")
        if command[:3] == [command[0], "-m", "pip_audit"]:
            return _FakeCompletedProcess(returncode=1, stderr="No module named pip_audit")
        raise AssertionError(f"Unexpected command: {command}")

    result = run_dependency_audit(
        runs_dir=runs_dir,
        policy="fail_on_critical",
        with_security_scan=True,
        requirements_files=[requirements_path],
        now=datetime(2026, 3, 2, 15, 3, 0, tzinfo=timezone.utc),
        command_runner=_runner,
        repo_root=repo_root,
        scan_roots=[repo_root / "scripts", repo_root / "src", repo_root / "tests"],
        installed_packages={"numpy"},
    )

    assert result["security_payload"]["status"] == "warn"
    assert result["run_payload"]["exit_code"] == 2
    assert result["ok"] is False


def test_dependency_audit_fail_on_critical_handles_object_payload_vulnerabilities(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runs_dir = tmp_path / "runs"
    requirements_path = repo_root / "requirements.txt"
    _write_text(repo_root / "scripts" / "app.py", "import numpy\n")
    _write_text(requirements_path, "numpy>=2.0.0,<3.0.0\n")

    def _runner(command: list[str], _cwd: Path) -> _FakeCompletedProcess:
        if command[:4] == [command[0], "-m", "pip", "check"]:
            return _FakeCompletedProcess(returncode=0, stdout="No broken requirements found.\n")
        if command[:3] == [command[0], "-m", "pip_audit"]:
            return _FakeCompletedProcess(
                returncode=0,
                stdout=json.dumps(
                    {
                        "dependencies": [
                            {
                                "name": "numpy",
                                "version": "2.0.0",
                                "vulns": [{"id": "PYSEC-TEST-1", "fix_versions": []}],
                            }
                        ]
                    }
                ),
            )
        raise AssertionError(f"Unexpected command: {command}")

    result = run_dependency_audit(
        runs_dir=runs_dir,
        policy="fail_on_critical",
        with_security_scan=True,
        requirements_files=[requirements_path],
        now=datetime(2026, 3, 2, 15, 4, 0, tzinfo=timezone.utc),
        command_runner=_runner,
        repo_root=repo_root,
        scan_roots=[repo_root / "scripts", repo_root / "src", repo_root / "tests"],
        installed_packages={"numpy"},
    )

    assert result["security_payload"]["status"] == "ok"
    assert result["security_payload"]["vulnerabilities_count"] == 1
    assert result["run_payload"]["exit_code"] == 2
    assert result["ok"] is False
