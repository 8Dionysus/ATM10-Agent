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
from src.agent_core.ops_policy import SOURCE_STALE_AFTER_HOURS

_TIMESTAMP_FIELDS: tuple[str, ...] = (
    "checked_at_utc",
    "finished_at_utc",
    "timestamp_utc",
    "started_at_utc",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_timestamp_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _extract_payload_timestamp(payload: Mapping[str, Any]) -> datetime | None:
    for field in _TIMESTAMP_FIELDS:
        parsed = _parse_timestamp_utc(payload.get(field))
        if parsed is not None:
            return parsed
    return None


def _index_source(
    *,
    spec: Mapping[str, Any],
    now: datetime,
    stale_after_hours: float,
) -> tuple[dict[str, Any], list[str]]:
    source_key = str(spec["source_key"])
    path = Path(str(spec["path"]))
    expected_schema = spec.get("expected_schema_version")
    warnings: list[str] = []

    entry: dict[str, Any] = {
        "source_key": source_key,
        "path": str(path),
        "expected_schema_version": expected_schema,
        "schema_version": None,
        "status": "missing",
        "freshness": "missing",
        "age_hours": None,
        "timestamp_utc": None,
        "contract_state": "missing",
    }

    if not path.is_file():
        return entry, warnings

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        entry["status"] = "invalid"
        entry["freshness"] = "invalid"
        entry["contract_state"] = "json_parse_error"
        warnings.append(f"{source_key}: failed to parse JSON {path}: {exc}")
        return entry, warnings

    if not isinstance(payload, Mapping):
        entry["status"] = "invalid"
        entry["freshness"] = "invalid"
        entry["contract_state"] = "invalid_root"
        warnings.append(f"{source_key}: json root must be object: {path}")
        return entry, warnings

    observed_schema = payload.get("schema_version")
    if isinstance(observed_schema, str) and observed_schema.strip():
        entry["schema_version"] = observed_schema.strip()
    if expected_schema is not None and entry["schema_version"] != expected_schema:
        entry["contract_state"] = "schema_mismatch"
        warnings.append(
            f"{source_key}: schema mismatch (observed={entry['schema_version']!r}, expected={expected_schema!r})"
        )
    else:
        entry["contract_state"] = "ok"

    observed_status = payload.get("status")
    if isinstance(observed_status, str) and observed_status.strip():
        entry["status"] = observed_status.strip()
    else:
        entry["status"] = "unknown"

    timestamp = _extract_payload_timestamp(payload)
    if timestamp is None:
        entry["freshness"] = "unknown"
        return entry, warnings

    age_hours = max(0.0, (now - timestamp).total_seconds() / 3600.0)
    entry["timestamp_utc"] = timestamp.isoformat()
    entry["age_hours"] = round(age_hours, 3)
    entry["freshness"] = "fresh" if age_hours <= stale_after_hours else "stale"
    return entry, warnings


def run_build_ops_contract_index(
    *,
    profile: str,
    runs_dir: Path = Path("runs"),
    summary_json: Path | None = None,
    stale_after_hours: float = float(SOURCE_STALE_AFTER_HOURS),
    now: datetime | None = None,
) -> dict[str, Any]:
    if profile not in PROFILE_SOURCE_SPECS:
        raise ValueError(f"profile must be one of: {', '.join(sorted(PROFILE_SOURCE_SPECS.keys()))}")
    if stale_after_hours <= 0:
        raise ValueError("stale_after_hours must be > 0.")
    if now is None:
        now = datetime.now(timezone.utc)

    output_path = (
        summary_json
        if summary_json is not None
        else (Path(runs_dir) / "ops-index" / f"{profile}_ops_contract_index.json")
    )

    try:
        source_specs = resolve_profile_sources(profile, Path(runs_dir))
        entries: list[dict[str, Any]] = []
        warnings: list[str] = []
        for spec in source_specs:
            entry, source_warnings = _index_source(spec=spec, now=now, stale_after_hours=stale_after_hours)
            entries.append(entry)
            warnings.extend(source_warnings)

        freshness_totals = {
            "fresh": sum(1 for item in entries if item["freshness"] == "fresh"),
            "stale": sum(1 for item in entries if item["freshness"] == "stale"),
            "missing": sum(1 for item in entries if item["freshness"] == "missing"),
            "unknown": sum(1 for item in entries if item["freshness"] == "unknown"),
            "invalid": sum(1 for item in entries if item["freshness"] == "invalid"),
        }
        status_totals: dict[str, int] = {}
        for item in entries:
            key = str(item.get("status", "unknown"))
            status_totals[key] = status_totals.get(key, 0) + 1

        summary_payload: dict[str, Any] = {
            "schema_version": "ops_contract_index_v1",
            "profile": profile,
            "status": "ok",
            "generated_at_utc": _utc_now(),
            "stale_after_hours": stale_after_hours,
            "sources": entries,
            "warnings": warnings,
            "totals": {
                "source_count": len(entries),
                "freshness": freshness_totals,
                "status": status_totals,
            },
            "paths": {
                "runs_dir": str(Path(runs_dir)),
                "summary_json": str(output_path),
            },
        }
        _write_json(output_path, summary_payload)
        return {"ok": True, "exit_code": 0, "summary_payload": summary_payload}
    except Exception as exc:
        summary_payload = {
            "schema_version": "ops_contract_index_v1",
            "profile": profile,
            "status": "error",
            "generated_at_utc": _utc_now(),
            "stale_after_hours": stale_after_hours,
            "sources": [],
            "warnings": [],
            "error": str(exc),
            "totals": {
                "source_count": 0,
                "freshness": {"fresh": 0, "stale": 0, "missing": 0, "unknown": 0, "invalid": 0},
                "status": {},
            },
            "paths": {
                "runs_dir": str(Path(runs_dir)),
                "summary_json": str(output_path),
            },
        }
        _write_json(output_path, summary_payload)
        return {"ok": False, "exit_code": 2, "summary_payload": summary_payload}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build indexed view of ops summary contracts.")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_SOURCE_SPECS.keys()),
        required=True,
        help="Index profile.",
    )
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Base runs directory.")
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Output path for ops_contract_index_v1.",
    )
    parser.add_argument(
        "--stale-after-hours",
        type=float,
        default=float(SOURCE_STALE_AFTER_HOURS),
        help=f"Freshness threshold in hours (default: {SOURCE_STALE_AFTER_HOURS}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_build_ops_contract_index(
        profile=args.profile,
        runs_dir=args.runs_dir,
        summary_json=args.summary_json,
        stale_after_hours=args.stale_after_hours,
    )
    summary = result["summary_payload"]
    print(f"[build_ops_contract_index] profile: {args.profile}")
    print(f"[build_ops_contract_index] status: {summary['status']}")
    print(f"[build_ops_contract_index] summary_json: {summary['paths']['summary_json']}")
    print(f"[build_ops_contract_index] source_count: {summary['totals']['source_count']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
