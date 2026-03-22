from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Mapping, Sequence


INVENTORY_SCHEMA_VERSION = "dependency_inventory_v1"
FINDINGS_SCHEMA_VERSION = "dependency_findings_v1"
SECURITY_AUDIT_SCHEMA_VERSION = "dependency_security_audit_v1"
DEFAULT_REQUIREMENTS_FILES = (
    "requirements.txt",
    "requirements-voice.txt",
    "requirements-llm.txt",
    "requirements-export.txt",
    "requirements-dev.txt",
)
DEFAULT_SCAN_ROOTS = ("scripts", "src", "tests")
OPTIONAL_RUNTIME_PACKAGES = {"qwen-asr", "qwen-tts"}

IMPORT_TO_PACKAGE = {
    "fastapi": "fastapi",
    "httpx": "httpx",
    "librosa": "librosa",
    "nncf": "nncf",
    "numpy": "numpy",
    "openvino": "openvino",
    "openvino_genai": "openvino-genai",
    "optimum": "optimum",
    "qwen_asr": "qwen-asr",
    "qwen_tts": "qwen-tts",
    "sounddevice": "sounddevice",
    "streamlit": "streamlit",
    "torch": "torch",
    "transformers": "transformers",
    "TTS": "tts",
    "uvicorn": "uvicorn",
}


def _normalize_package_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _create_run_dir(runs_dir: Path, now: datetime) -> Path:
    base_name = now.strftime("%Y%m%d_%H%M%S-dependency-audit")
    run_dir = runs_dir / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    suffix = 1
    while True:
        candidate = runs_dir / f"{base_name}_{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        suffix += 1


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_bool_flag(raw_value: str) -> bool:
    normalized = str(raw_value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("Expected one of: true|false|1|0|yes|no.")


def _requirement_name_from_spec(spec: str) -> str | None:
    stripped = spec.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("-"):
        return None
    match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)", stripped)
    if match is None:
        return None
    return _normalize_package_name(match.group(1))


def _parse_requirements_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "missing": True, "dependencies": [], "includes": []}

    dependencies: list[str] = []
    includes: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            includes.append(line[3:].strip())
            continue
        if line.startswith("--requirement "):
            includes.append(line[len("--requirement ") :].strip())
            continue
        name = _requirement_name_from_spec(line)
        if name is not None:
            dependencies.append(name)
    dependencies = sorted(set(dependencies))
    return {"path": str(path), "missing": False, "dependencies": dependencies, "includes": includes}


def _resolve_requirement_files(repo_root: Path, raw_paths: Sequence[str | Path]) -> list[Path]:
    resolved: list[Path] = []
    for raw in raw_paths:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        resolved.append(candidate)
    return resolved


def _discover_local_module_names(scan_roots: Sequence[Path]) -> set[str]:
    local_modules: set[str] = set()
    for root in scan_roots:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if py_file.name == "__init__.py":
                local_modules.add(py_file.parent.name)
                continue
            local_modules.add(py_file.stem)
    return local_modules


def _iter_import_top_modules(tree: ast.AST) -> list[str]:
    results: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0].strip()
                if top:
                    results.append(top)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module:
                top = node.module.split(".")[0].strip()
                if top:
                    results.append(top)
    return results


def _collect_import_inventory(*, repo_root: Path, scan_roots: Sequence[Path]) -> dict[str, Any]:
    stdlib_names = set(sys.stdlib_module_names)
    local_module_names = _discover_local_module_names(scan_roots)

    observed: dict[str, dict[str, dict[str, Any]]] = {"runtime": {}, "tests": {}}

    for root in scan_roots:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            rel_path = str(py_file.relative_to(repo_root))
            scope = "tests" if py_file.parts and py_file.parts[0] == "tests" else "runtime"

            for top_module in _iter_import_top_modules(tree):
                if top_module in {"scripts", "src", "tests"}:
                    continue
                if top_module in stdlib_names:
                    continue
                if top_module in local_module_names:
                    continue
                package_name = IMPORT_TO_PACKAGE.get(top_module, _normalize_package_name(top_module))
                bucket = observed[scope].setdefault(
                    top_module,
                    {"module": top_module, "package": package_name, "files": set()},
                )
                bucket["files"].add(rel_path)

    serialized: dict[str, list[dict[str, Any]]] = {"runtime": [], "tests": []}
    for scope in ("runtime", "tests"):
        for module_name in sorted(observed[scope]):
            item = observed[scope][module_name]
            serialized[scope].append(
                {
                    "module": item["module"],
                    "package": item["package"],
                    "files": sorted(item["files"]),
                }
            )
    return serialized


def _run_command(
    *,
    command: list[str],
    cwd: Path,
    command_runner: Any | None = None,
) -> subprocess.CompletedProcess[str]:
    if command_runner is not None:
        return command_runner(command, cwd)
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _collect_declared_dependencies(
    requirement_files: Sequence[Path],
) -> tuple[set[str], list[dict[str, Any]], list[dict[str, Any]]]:
    declared: set[str] = set()
    details: list[dict[str, Any]] = []
    missing_file_findings: list[dict[str, Any]] = []

    for req_file in requirement_files:
        parsed = _parse_requirements_file(req_file)
        details.append(parsed)
        for dependency in parsed["dependencies"]:
            declared.add(dependency)
        if parsed["missing"]:
            missing_file_findings.append(
                {
                    "severity": "warn",
                    "code": "requirements_file_missing",
                    "message": f"Requirements file does not exist: {req_file}",
                    "path": str(req_file),
                }
            )
    return declared, details, missing_file_findings


def _collect_installed_dependencies(installed_packages: set[str] | None = None) -> set[str]:
    if installed_packages is not None:
        return {_normalize_package_name(item) for item in installed_packages}

    discovered: set[str] = set()
    for dist in metadata.distributions():
        name = dist.metadata.get("Name") if dist.metadata is not None else None
        if name is None:
            continue
        discovered.add(_normalize_package_name(name))
    return discovered


def _build_findings(
    *,
    inventory_payload: Mapping[str, Any],
    declared_dependencies: set[str],
    installed_dependencies: set[str],
    extra_findings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = [dict(item) for item in extra_findings]

    runtime_packages: set[str] = set()
    test_packages: set[str] = set()
    observed_packages: set[str] = set()

    for item in inventory_payload.get("imports", {}).get("runtime", []):
        package_name = _normalize_package_name(str(item["package"]))
        runtime_packages.add(package_name)
        observed_packages.add(package_name)
        if package_name not in declared_dependencies:
            if package_name in OPTIONAL_RUNTIME_PACKAGES:
                findings.append(
                    {
                        "severity": "warn",
                        "code": "missing_optional_runtime_dependency",
                        "message": (
                            "Optional runtime import is not present in declared requirements files: "
                            f"module={item['module']}, package={package_name}"
                        ),
                        "module": item["module"],
                        "package": package_name,
                        "files": item["files"],
                    }
                )
                continue
            findings.append(
                {
                    "severity": "error",
                    "code": "missing_runtime_dependency",
                    "message": (
                        "Runtime import is not present in declared requirements files: "
                        f"module={item['module']}, package={package_name}"
                    ),
                    "module": item["module"],
                    "package": package_name,
                    "files": item["files"],
                }
            )

    for item in inventory_payload.get("imports", {}).get("tests", []):
        package_name = _normalize_package_name(str(item["package"]))
        test_packages.add(package_name)
        observed_packages.add(package_name)
        if package_name not in declared_dependencies:
            findings.append(
                {
                    "severity": "info",
                    "code": "missing_test_dependency",
                    "message": (
                        "Test-only import is not present in declared requirements files: "
                        f"module={item['module']}, package={package_name}"
                    ),
                    "module": item["module"],
                    "package": package_name,
                    "files": item["files"],
                }
            )

    for package_name in sorted(declared_dependencies):
        if package_name not in installed_dependencies:
            findings.append(
                {
                    "severity": "warn",
                    "code": "declared_dependency_not_installed",
                    "message": f"Declared dependency is not installed in current environment: {package_name}",
                    "package": package_name,
                }
            )
        if package_name not in observed_packages:
            findings.append(
                {
                    "severity": "warn",
                    "code": "declared_dependency_not_observed",
                    "message": (
                        "Declared dependency is not directly observed in current import graph "
                        f"(might still be valid for optional paths): {package_name}"
                    ),
                    "package": package_name,
                }
            )

    summary = {
        "error_count": sum(1 for item in findings if item["severity"] == "error"),
        "warn_count": sum(1 for item in findings if item["severity"] == "warn"),
        "info_count": sum(1 for item in findings if item["severity"] == "info"),
    }
    return {"schema_version": FINDINGS_SCHEMA_VERSION, "summary": summary, "findings": findings}


def _run_pip_check(*, repo_root: Path, command_runner: Any | None) -> dict[str, Any]:
    command = [sys.executable, "-m", "pip", "check"]
    result = _run_command(command=command, cwd=repo_root, command_runner=command_runner)
    status = "ok" if result.returncode == 0 else "error"
    return {
        "command": command,
        "status": status,
        "returncode": int(result.returncode),
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    }


def _normalize_pip_audit_vulnerabilities(parsed_payload: Any) -> list[dict[str, Any]]:
    if isinstance(parsed_payload, list):
        if not all(isinstance(item, Mapping) for item in parsed_payload):
            raise ValueError("pip-audit list payload must contain mapping items.")
        return [dict(item) for item in parsed_payload]

    if isinstance(parsed_payload, Mapping):
        dependencies = parsed_payload.get("dependencies", [])
        if dependencies in (None, ""):
            return []
        if not isinstance(dependencies, list):
            raise ValueError("pip-audit object payload must provide 'dependencies' as a list.")
        if not all(isinstance(item, Mapping) for item in dependencies):
            raise ValueError("pip-audit dependencies payload must contain mapping items.")
        return [dict(item) for item in dependencies]

    raise ValueError("Unsupported pip-audit JSON payload shape.")


def _count_pip_audit_vulnerabilities(vulnerabilities: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for item in vulnerabilities:
        vulns = item.get("vulns", [])
        if isinstance(vulns, list):
            total += len(vulns)
    return total


def _run_security_scan(
    *,
    repo_root: Path,
    with_security_scan: bool,
    command_runner: Any | None,
) -> dict[str, Any]:
    if not with_security_scan:
        return {
            "schema_version": SECURITY_AUDIT_SCHEMA_VERSION,
            "status": "skipped",
            "tool": "pip-audit",
            "vulnerabilities_count": 0,
            "vulnerabilities": [],
            "error": None,
        }

    command = [sys.executable, "-m", "pip_audit", "-f", "json"]
    result = _run_command(command=command, cwd=repo_root, command_runner=command_runner)
    stdout_text = result.stdout or ""
    stderr_text = result.stderr or ""

    payload: dict[str, Any] = {
        "schema_version": SECURITY_AUDIT_SCHEMA_VERSION,
        "tool": "pip-audit",
        "command": command,
        "returncode": int(result.returncode),
        "stdout": stdout_text,
        "stderr": stderr_text,
    }

    if result.returncode == 0:
        try:
            parsed = json.loads(stdout_text or "[]")
            vulnerabilities = _normalize_pip_audit_vulnerabilities(parsed)
            vulnerabilities_count = _count_pip_audit_vulnerabilities(vulnerabilities)
            payload.update(
                {
                    "status": "ok",
                    "vulnerabilities_count": int(vulnerabilities_count),
                    "vulnerabilities": vulnerabilities,
                    "error": None,
                }
            )
            return payload
        except Exception as exc:
            payload.update(
                {
                    "status": "warn",
                    "vulnerabilities_count": 0,
                    "vulnerabilities": [],
                    "error": f"Failed to parse pip-audit JSON output: {exc}",
                }
            )
            return payload

    missing_tool_markers = ("No module named pip_audit", "No module named pip-audit")
    is_missing_tool = any(marker in stderr_text for marker in missing_tool_markers)
    if is_missing_tool:
        error_message = "pip-audit is not installed in current environment."
    else:
        error_message = "pip-audit execution failed (network/tooling issue)."

    payload.update(
        {
            "status": "warn",
            "vulnerabilities_count": 0,
            "vulnerabilities": [],
            "error": error_message,
        }
    )
    return payload


def _compute_exit_code(
    *,
    policy: str,
    findings_payload: Mapping[str, Any],
    security_payload: Mapping[str, Any],
    pip_check_payload: Mapping[str, Any],
) -> int:
    if policy == "report_only":
        return 0

    if int(findings_payload["summary"]["error_count"]) > 0:
        return 2
    if pip_check_payload.get("status") != "ok":
        return 2
    security_status = str(security_payload.get("status", "unknown"))
    if security_status not in {"ok", "skipped"}:
        return 2
    if security_payload.get("status") == "ok" and int(security_payload.get("vulnerabilities_count", 0)) > 0:
        return 2
    return 0


def _render_summary_markdown(
    *,
    run_payload: Mapping[str, Any],
    inventory_payload: Mapping[str, Any],
    findings_payload: Mapping[str, Any],
    security_payload: Mapping[str, Any],
    pip_check_payload: Mapping[str, Any],
) -> str:
    summary = findings_payload["summary"]
    runtime_imports = inventory_payload["imports"]["runtime"]
    test_imports = inventory_payload["imports"]["tests"]
    lines = [
        "# Dependency Audit Summary",
        "",
        f"- status: `{run_payload['status']}`",
        f"- policy: `{run_payload['policy']}`",
        f"- with_security_scan: `{run_payload['with_security_scan']}`",
        "",
        "## Findings",
        "",
        f"- errors: `{summary['error_count']}`",
        f"- warnings: `{summary['warn_count']}`",
        f"- info: `{summary['info_count']}`",
        "",
        "## Import Inventory",
        "",
        f"- runtime third-party modules: `{len(runtime_imports)}`",
        f"- test third-party modules: `{len(test_imports)}`",
        "",
        "## pip check",
        "",
        f"- status: `{pip_check_payload['status']}`",
        f"- returncode: `{pip_check_payload['returncode']}`",
        "",
        "## Security Scan",
        "",
        f"- status: `{security_payload.get('status', 'unknown')}`",
        f"- vulnerabilities_count: `{security_payload.get('vulnerabilities_count', 0)}`",
    ]
    if security_payload.get("error"):
        lines.append(f"- error: `{security_payload['error']}`")
    return "\n".join(lines) + "\n"


def run_dependency_audit(
    *,
    runs_dir: Path = Path("runs"),
    policy: str = "report_only",
    with_security_scan: bool = True,
    requirements_files: Sequence[str | Path] | None = None,
    now: datetime | None = None,
    command_runner: Any | None = None,
    repo_root: Path | None = None,
    scan_roots: Sequence[Path] | None = None,
    installed_packages: set[str] | None = None,
) -> dict[str, Any]:
    effective_now = now or datetime.now(timezone.utc)
    effective_repo_root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    requirement_specs = list(requirements_files or DEFAULT_REQUIREMENTS_FILES)
    requirement_paths = _resolve_requirement_files(effective_repo_root, requirement_specs)

    effective_scan_roots = [
        root.resolve() if root.is_absolute() else (effective_repo_root / root).resolve()
        for root in (scan_roots or [Path(item) for item in DEFAULT_SCAN_ROOTS])
    ]

    run_dir = _create_run_dir(runs_dir, now=effective_now)
    run_json_path = run_dir / "run.json"
    inventory_path = run_dir / "dependency_inventory.json"
    findings_path = run_dir / "dependency_findings.json"
    security_path = run_dir / "security_audit.json"
    summary_path = run_dir / "summary.md"

    run_payload: dict[str, Any] = {
        "timestamp_utc": effective_now.astimezone(timezone.utc).isoformat(),
        "mode": "dependency_audit",
        "status": "started",
        "policy": policy,
        "with_security_scan": with_security_scan,
        "paths": {
            "run_dir": str(run_dir),
            "run_json": str(run_json_path),
            "inventory_json": str(inventory_path),
            "findings_json": str(findings_path),
            "security_json": str(security_path),
            "summary_md": str(summary_path),
        },
    }
    _write_json(run_json_path, run_payload)

    declared_dependencies, requirements_details, pre_findings = _collect_declared_dependencies(requirement_paths)
    inventory_payload: dict[str, Any] = {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "timestamp_utc": effective_now.astimezone(timezone.utc).isoformat(),
        "scan_roots": [str(path) for path in effective_scan_roots],
        "requirements_files": [str(path) for path in requirement_paths],
        "requirements_details": requirements_details,
        "imports": _collect_import_inventory(repo_root=effective_repo_root, scan_roots=effective_scan_roots),
        "declared_dependencies": sorted(declared_dependencies),
    }
    _write_json(inventory_path, inventory_payload)

    installed_dependencies = _collect_installed_dependencies(installed_packages)
    inventory_payload["installed_dependencies"] = sorted(installed_dependencies)
    _write_json(inventory_path, inventory_payload)

    findings_payload = _build_findings(
        inventory_payload=inventory_payload,
        declared_dependencies=declared_dependencies,
        installed_dependencies=installed_dependencies,
        extra_findings=pre_findings,
    )

    pip_check_payload = _run_pip_check(repo_root=effective_repo_root, command_runner=command_runner)
    if pip_check_payload["status"] != "ok":
        findings_payload["findings"].append(
            {
                "severity": "error",
                "code": "pip_check_failed",
                "message": "pip check reported broken environment dependencies.",
                "returncode": pip_check_payload["returncode"],
            }
        )
        findings_payload["summary"]["error_count"] += 1

    security_payload = _run_security_scan(
        repo_root=effective_repo_root,
        with_security_scan=with_security_scan,
        command_runner=command_runner,
    )
    if security_payload.get("status") == "warn":
        findings_payload["findings"].append(
            {
                "severity": "warn",
                "code": "security_scan_warn",
                "message": str(security_payload.get("error") or "security scan warning"),
            }
        )
        findings_payload["summary"]["warn_count"] += 1

    _write_json(findings_path, findings_payload)
    _write_json(security_path, security_payload)

    run_status = "ok"
    if int(findings_payload["summary"]["error_count"]) > 0:
        run_status = "error"
    elif int(findings_payload["summary"]["warn_count"]) > 0:
        run_status = "warn"
    run_payload["status"] = run_status

    exit_code = _compute_exit_code(
        policy=policy,
        findings_payload=findings_payload,
        security_payload=security_payload,
        pip_check_payload=pip_check_payload,
    )
    run_payload["exit_code"] = int(exit_code)
    _write_json(run_json_path, run_payload)

    summary_text = _render_summary_markdown(
        run_payload=run_payload,
        inventory_payload=inventory_payload,
        findings_payload=findings_payload,
        security_payload=security_payload,
        pip_check_payload=pip_check_payload,
    )
    summary_path.write_text(summary_text, encoding="utf-8")

    return {
        "run_dir": run_dir,
        "run_payload": run_payload,
        "inventory_payload": inventory_payload,
        "findings_payload": findings_payload,
        "security_payload": security_payload,
        "pip_check_payload": pip_check_payload,
        "exit_code": int(exit_code),
        "ok": exit_code == 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build dependency inventory and security report artifacts in "
            "runs/<timestamp>-dependency-audit."
        )
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Base directory for run artifacts (default: runs).",
    )
    parser.add_argument(
        "--policy",
        choices=("report_only", "fail_on_critical"),
        default="report_only",
        help="Audit policy (default: report_only).",
    )
    parser.add_argument(
        "--with-security-scan",
        type=_parse_bool_flag,
        default=True,
        help="Enable pip-audit scan (true/false, default: true).",
    )
    parser.add_argument(
        "--requirements-files",
        nargs="+",
        default=list(DEFAULT_REQUIREMENTS_FILES),
        help=(
            "Requirements files to analyze (default: "
            "requirements.txt requirements-voice.txt requirements-llm.txt "
            "requirements-export.txt requirements-dev.txt)."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_dependency_audit(
        runs_dir=args.runs_dir,
        policy=args.policy,
        with_security_scan=args.with_security_scan,
        requirements_files=args.requirements_files,
    )
    run_dir = result["run_dir"]
    run_payload = result["run_payload"]

    print(f"[dependency_audit] run_dir: {run_dir}")
    print(f"[dependency_audit] status: {run_payload['status']}")
    print(f"[dependency_audit] exit_code: {run_payload['exit_code']}")
    print(f"[dependency_audit] run_json: {run_payload['paths']['run_json']}")
    print(f"[dependency_audit] findings_json: {run_payload['paths']['findings_json']}")
    print(f"[dependency_audit] security_json: {run_payload['paths']['security_json']}")
    print(f"[dependency_audit] summary_md: {run_payload['paths']['summary_md']}")
    return int(run_payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
