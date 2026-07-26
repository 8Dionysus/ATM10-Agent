#!/usr/bin/env python3
"""Validate the source-owned ATM10 eval manifest and deterministic suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "evals" / "manifest.json"


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.relative_to(REPO_ROOT)} must contain a JSON object")
    return payload


def validate_local_evals() -> list[str]:
    issues: list[str] = []
    try:
        manifest = _load_object(MANIFEST_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]

    if manifest.get("schema_version") != "atm10_eval_manifest_v1":
        issues.append("evals/manifest.json: unsupported schema_version")
    if manifest.get("owner_repo") != "ATM10-Agent":
        issues.append("evals/manifest.json: owner_repo must be ATM10-Agent")
    if manifest.get("verdict_authority") != "ATM10-Agent":
        issues.append("evals/manifest.json: verdict authority must remain local")

    suite_refs = manifest.get("suite_refs")
    if not isinstance(suite_refs, list) or not suite_refs:
        issues.append("evals/manifest.json: at least one suite_ref is required")
        return issues

    case_ids: set[str] = set()
    protected_ids: set[str] = set()
    for raw_ref in suite_refs:
        suite_path = REPO_ROOT / str(raw_ref)
        try:
            suite = _load_object(suite_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            issues.append(str(exc))
            continue
        if suite.get("schema_version") != "atm10_eval_suite_v1":
            issues.append(f"{raw_ref}: unsupported schema_version")
        cases = suite.get("cases")
        if not isinstance(cases, list) or not cases:
            issues.append(f"{raw_ref}: at least one case is required")
            continue
        for case in cases:
            if not isinstance(case, dict):
                issues.append(f"{raw_ref}: every case must be an object")
                continue
            case_id = str(case.get("id", "")).strip()
            test_ref = str(case.get("test_ref", "")).strip()
            raw_protects = case.get("protects")
            protects = (
                [str(item).strip() for item in raw_protects]
                if isinstance(raw_protects, list)
                else [str(raw_protects or "").strip()]
            )
            if not case_id or case_id in case_ids:
                issues.append(f"{raw_ref}: missing or duplicate case id {case_id!r}")
            case_ids.add(case_id)
            if not test_ref or not (REPO_ROOT / test_ref).is_file():
                issues.append(f"{raw_ref}: missing test_ref {test_ref!r}")
            if not protects:
                issues.append(f"{raw_ref}: case {case_id!r} has no protected behavior refs")
            for protects_ref in protects:
                if not protects_ref.startswith("PB-"):
                    issues.append(
                        f"{raw_ref}: invalid protected behavior ref {protects_ref!r}"
                    )
                protected_ids.add(protects_ref)

    if len(protected_ids) < 5:
        issues.append("local eval suite must protect at least five behavior contracts")
    return issues


def main() -> int:
    issues = validate_local_evals()
    if issues:
        for issue in issues:
            print(f"[error] {issue}")
        return 1
    print("[ok] ATM10 local eval suites validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
