from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ops_contract_profiles import PROFILE_SOURCE_SPECS, resolve_profile_sources

_POLICIES: tuple[str, ...] = ("report_only", "fail_on_error")
_STATUS_VALUES = {"ok", "error"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_status_semantics(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    status = payload.get("status")
    status_text = str(status).strip() if isinstance(status, str) else ""
    if status_text not in _STATUS_VALUES:
        errors.append("status must be one of: ok|error")
        return errors

    ok_value = payload.get("ok")
    if isinstance(ok_value, bool):
        if status_text == "ok" and not ok_value:
            errors.append("status=ok conflicts with ok=false")
        if status_text == "error" and ok_value:
            errors.append("status=error conflicts with ok=true")

    exit_code = payload.get("exit_code")
    if isinstance(exit_code, int):
        if status_text == "ok" and exit_code != 0:
            errors.append("status=ok conflicts with non-zero exit_code")
        if status_text == "error" and exit_code == 0:
            errors.append("status=error conflicts with exit_code=0")

    return errors


def _validate_source(spec: Mapping[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    source_key = str(spec["source_key"])
    path = Path(str(spec["path"]))
    expected_schema = spec.get("expected_schema_version")
    required_fields = [str(item) for item in spec.get("required_fields", ())]

    entry: dict[str, Any] = {
        "source_key": source_key,
        "path": str(path),
        "expected_schema_version": expected_schema,
        "schema_version": None,
        "source_status": None,
        "exists": path.is_file(),
        "json_parse_ok": False,
        "missing_required_fields": [],
        "semantics_errors": [],
        "errors": [],
        "warnings": [],
        "contract_status": "error",
    }

    if not path.is_file():
        entry["errors"].append("missing file")
        return entry, [f"{source_key}: missing file {path}"], []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry["errors"].append(f"json parse failed: {exc}")
        return entry, [f"{source_key}: json parse failed for {path}: {exc}"], []

    if not isinstance(payload, Mapping):
        entry["errors"].append("json root must be object")
        return entry, [f"{source_key}: json root must be object"], []

    entry["json_parse_ok"] = True
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, str) and schema_version.strip():
        entry["schema_version"] = schema_version.strip()
    if expected_schema is not None and entry["schema_version"] != expected_schema:
        entry["errors"].append(
            f"schema_version mismatch (observed={entry['schema_version']!r}, expected={expected_schema!r})"
        )

    missing_fields = [field for field in required_fields if field not in payload]
    if missing_fields:
        entry["missing_required_fields"] = missing_fields
        entry["errors"].append(f"missing required fields: {', '.join(missing_fields)}")

    source_status = payload.get("status")
    if isinstance(source_status, str):
        entry["source_status"] = source_status.strip()
    semantics_errors = _parse_status_semantics(payload)
    if semantics_errors:
        entry["semantics_errors"] = semantics_errors
        entry["errors"].extend(semantics_errors)

    if not entry["errors"]:
        entry["contract_status"] = "ok"
    return (
        entry,
        [f"{source_key}: {error}" for error in entry["errors"]],
        [f"{source_key}: {warning}" for warning in entry["warnings"]],
    )


def run_validate_ops_contracts(
    *,
    profile: str,
    runs_dir: Path = Path("runs"),
    policy: str = "report_only",
    summary_json: Path | None = None,
) -> dict[str, Any]:
    if policy not in _POLICIES:
        raise ValueError(f"policy must be one of: {', '.join(_POLICIES)}")
    if profile not in PROFILE_SOURCE_SPECS:
        raise ValueError(f"profile must be one of: {', '.join(sorted(PROFILE_SOURCE_SPECS.keys()))}")

    output_path = (
        summary_json
        if summary_json is not None
        else (Path(runs_dir) / "ops-validation" / f"{profile}_validation_summary.json")
    )

    try:
        source_specs = resolve_profile_sources(profile, Path(runs_dir))
        checked_sources: list[dict[str, Any]] = []
        errors: list[str] = []
        warnings: list[str] = []
        for spec in source_specs:
            entry, source_errors, source_warnings = _validate_source(spec)
            checked_sources.append(entry)
            errors.extend(source_errors)
            warnings.extend(source_warnings)

        status = "ok" if not errors else "error"
        exit_code = 0
        if policy == "fail_on_error" and status == "error":
            exit_code = 2

        summary_payload: dict[str, Any] = {
            "schema_version": "validation_summary_v1",
            "profile": profile,
            "status": status,
            "generated_at_utc": _utc_now(),
            "policy": policy,
            "checked_sources": checked_sources,
            "errors": errors,
            "warnings": warnings,
            "totals": {
                "checked_count": len(checked_sources),
                "error_count": len(errors),
                "warning_count": len(warnings),
                "ok_sources_count": sum(1 for item in checked_sources if item["contract_status"] == "ok"),
            },
            "exit_code": exit_code,
            "paths": {
                "runs_dir": str(Path(runs_dir)),
                "summary_json": str(output_path),
            },
        }
        _write_json(output_path, summary_payload)
        return {"ok": exit_code == 0, "exit_code": exit_code, "summary_payload": summary_payload}
    except Exception as exc:
        summary_payload = {
            "schema_version": "validation_summary_v1",
            "profile": profile,
            "status": "error",
            "generated_at_utc": _utc_now(),
            "policy": policy,
            "checked_sources": [],
            "errors": [str(exc)],
            "warnings": [],
            "totals": {
                "checked_count": 0,
                "error_count": 1,
                "warning_count": 0,
                "ok_sources_count": 0,
            },
            "exit_code": 2,
            "paths": {
                "runs_dir": str(Path(runs_dir)),
                "summary_json": str(output_path),
            },
        }
        _write_json(output_path, summary_payload)
        return {"ok": False, "exit_code": 2, "summary_payload": summary_payload}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate machine-readable ops summary contracts.")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_SOURCE_SPECS.keys()),
        required=True,
        help="Validation profile.",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Base runs directory.")
    parser.add_argument(
        "--policy",
        choices=_POLICIES,
        default="report_only",
        help="Exit policy: report_only (default) or fail_on_error.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Output path for validation_summary_v1.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_validate_ops_contracts(
        profile=args.profile,
        runs_dir=args.runs_dir,
        policy=args.policy,
        summary_json=args.summary_json,
    )
    summary = result["summary_payload"]
    print(f"[validate_ops_contracts] profile: {args.profile}")
    print(f"[validate_ops_contracts] status: {summary['status']}")
    print(f"[validate_ops_contracts] summary_json: {summary['paths']['summary_json']}")
    print(f"[validate_ops_contracts] error_count: {summary['totals']['error_count']}")
    print(f"[validate_ops_contracts] warning_count: {summary['totals']['warning_count']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
