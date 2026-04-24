#!/usr/bin/env python3
"""Validate nested AGENTS.md guidance for ATM10-Agent.

This validator-first spine protects local AGENTS.md surfaces that already exist.
It also reports high-risk directories that are likely to need future local
guidance, without making those future files blocking before they land.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_NAME = 'ATM10-Agent'

REQUIRED_AGENTS_DOCS: dict[str, tuple[str, ...]] = {
    'scripts/AGENTS.md': (
        'runnable entrypoints and operator tooling',
        'dry-run or report-only behavior as the default',
        'ATM10_SERVICE_TOKEN',
        'python scripts/phase_a_smoke.py',
    ),
    'src/AGENTS.md': (
        'Nearest-file precedence',
        'src/agent_core/AGENTS.md',
        'Keep module imports cheap',
        'python -m pytest',
    ),
    'src/agent_core/AGENTS.md': (
        'shared runtime and policy surface',
        'Never silently turn a dry-run or safe-action path into real input behavior',
        'combo_a` stays additive',
        'python -m pytest tests/test_service_sla.py',
    ),
    'src/rag/AGENTS.md': (
        'document and evaluation schema',
        'Do not bake maintainer-local filesystem assumptions',
        'tests/test_rag_doc_contract.py',
    ),
    'src/kag/AGENTS.md': (
        'file baseline as the easiest local default',
        'Neo4j remains additive',
        'NEO4J_PASSWORD',
        'tests/test_kag_neo4j_backend.py',
    ),
    'src/hybrid/AGENTS.md': (
        '`baseline_first`',
        '`combo_a` additive',
        'explicit fallback behavior on KAG degradation',
        'tests/test_hybrid_query_demo.py',
    ),
    'docs/AGENTS.md': (
        'operator-facing public docs',
        'docs/SOURCE_OF_TRUTH.md',
        'dry-run by default',
        'tests/test_public_repo_hardening.py',
    ),
    'schemas/AGENTS.md': (
        'operator and antifragility contracts',
        'schema changes are contract changes',
        'gateway_operator_return_event.schema.json',
        'stressor_receipt_v1.json',
    ),
    'examples/AGENTS.md': (
        'sanitized contract examples',
        'match the schemas',
        'no secrets',
        'python -m pytest',
    ),
    'tests/AGENTS.md': (
        'regression and public-surface checks',
        'fixture-first',
        'python -m pytest',
        'tests/test_public_repo_hardening.py',
    ),
}
ADVISORY_AGENT_DIRS: tuple[str, ...] = ()
HEADING_PREFIXES = ("# AGENTS.md", "# AGENTS")
IGNORED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}


@dataclass(frozen=True)
class ValidationResult:
    issues: tuple[str, ...]
    warnings: tuple[str, ...]


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _has_agents_heading(text: str) -> bool:
    stripped = text.lstrip()
    return any(stripped.startswith(prefix) for prefix in HEADING_PREFIXES)


def _relative(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_ignored(path: Path, repo_root: Path) -> bool:
    try:
        parts = path.relative_to(repo_root).parts
    except ValueError:
        return False
    return any(part in IGNORED_DIRS for part in parts)


def discover_nested_agents(repo_root: Path) -> set[str]:
    found: set[str] = set()
    for path in repo_root.rglob("AGENTS.md"):
        if _is_ignored(path, repo_root):
            continue
        rel = _relative(path, repo_root)
        if rel != "AGENTS.md":
            found.add(rel)
    return found


def validate(
    repo_root: Path = REPO_ROOT,
    *,
    strict_advisory: bool = False,
    fail_on_untracked: bool = False,
) -> ValidationResult:
    repo_root = repo_root.resolve()
    issues: list[str] = []
    warnings: list[str] = []

    root_agents = repo_root / "AGENTS.md"
    if not root_agents.is_file():
        issues.append("AGENTS.md: root guidance file is missing")
    else:
        root_text = root_agents.read_text(encoding="utf-8")
        if not _has_agents_heading(root_text):
            issues.append("AGENTS.md: missing AGENTS heading")

    for rel_path, snippets in REQUIRED_AGENTS_DOCS.items():
        path = repo_root / rel_path
        if not path.is_file():
            issues.append(f"{rel_path}: required nested AGENTS.md is missing")
            continue
        text = path.read_text(encoding="utf-8")
        if not _has_agents_heading(text):
            issues.append(f"{rel_path}: missing AGENTS heading")
        normalized = _normalize(text)
        for snippet in snippets:
            if _normalize(snippet) not in normalized:
                issues.append(f"{rel_path}: missing required snippet {snippet!r}")

    required = set(REQUIRED_AGENTS_DOCS)
    actual = discover_nested_agents(repo_root)
    untracked = sorted(actual - required)
    if untracked:
        message = "untracked nested AGENTS.md not yet in validator map: " + ", ".join(untracked)
        warnings.append(message)
        if fail_on_untracked:
            issues.append(message)

    for rel_dir in ADVISORY_AGENT_DIRS:
        dir_path = repo_root / rel_dir
        agent_path = f"{rel_dir.rstrip('/')}/AGENTS.md"
        if not dir_path.is_dir():
            continue
        if agent_path in required or agent_path in actual:
            continue
        warnings.append(f"{rel_dir}: high-risk directory has no local AGENTS.md yet")

    if strict_advisory:
        issues.extend(warnings)

    return ValidationResult(tuple(issues), tuple(warnings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--strict-advisory", action="store_true")
    parser.add_argument("--fail-on-untracked", action="store_true")
    args = parser.parse_args(argv)

    result = validate(
        args.repo_root,
        strict_advisory=args.strict_advisory,
        fail_on_untracked=args.fail_on_untracked,
    )
    if result.issues:
        print(f"Nested AGENTS validation failed for {REPOSITORY_NAME}.")
        for issue in result.issues:
            print(f"- {issue}")
        return 1
    print(
        f"Nested AGENTS validation passed for {REPOSITORY_NAME}: "
        f"{len(REQUIRED_AGENTS_DOCS)} required nested document(s)."
    )
    for warning in result.warnings:
        print(f"[advisory] {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
