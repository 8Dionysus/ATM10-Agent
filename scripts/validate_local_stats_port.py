#!/usr/bin/env python3
"""Validate the owner-local ATM10 measurement contract without donor checkouts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PORT_PATH = REPO_ROOT / "stats" / "port.manifest.json"
PACKET_PATH = REPO_ROOT / "stats" / "packets" / "cross-service-sla-pass-ratio.reference.json"


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.relative_to(REPO_ROOT)} must contain a JSON object")
    return payload


def validate_local_stats() -> list[str]:
    issues: list[str] = []
    try:
        manifest = _load_object(PORT_PATH)
        packet = _load_object(PACKET_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]

    if manifest.get("schema_version") != "atm10_stats_port_v1":
        issues.append("stats/port.manifest.json: unsupported schema_version")
    if manifest.get("owner_repo") != "ATM10-Agent":
        issues.append("stats/port.manifest.json: owner_repo must be ATM10-Agent")
    if manifest.get("status") != "active":
        issues.append("stats/port.manifest.json: status must be active")

    measurements = manifest.get("measurements")
    if not isinstance(measurements, list) or len(measurements) != 1:
        issues.append("stats/port.manifest.json: exactly one measurement is required")
        return issues

    measurement = measurements[0]
    if not isinstance(measurement, dict):
        issues.append("stats/port.manifest.json: measurement must be an object")
        return issues

    measurement_id = "ATM10-Agent/cross-service-sla-pass-ratio"
    if measurement.get("schema_version") != "atm10_measurement_contract_v1":
        issues.append("stats/port.manifest.json: unsupported measurement schema")
    if measurement.get("measurement_id") != measurement_id:
        issues.append("stats/port.manifest.json: unexpected measurement_id")
    if measurement.get("owner_repo") != "ATM10-Agent":
        issues.append("stats/port.manifest.json: measurement owner must be ATM10-Agent")

    if packet.get("schema_version") != "atm10_measurement_packet_v1":
        issues.append("stats packet: unsupported schema_version")
    if packet.get("measurement_id") != measurement_id:
        issues.append("stats packet: measurement_id does not match manifest")
    if packet.get("writer_repo") != "ATM10-Agent":
        issues.append("stats packet: writer_repo must be ATM10-Agent")
    if packet.get("contract_ref") != "stats/port.manifest.json#/measurements/0":
        issues.append("stats packet: contract_ref must target the local manifest")

    posture = packet.get("posture")
    if not isinstance(posture, dict) or posture.get("privacy") != "public":
        issues.append("stats packet: posture.privacy must be public")
    if isinstance(posture, dict) and posture.get("raw_content_included") is not False:
        issues.append("stats packet: raw_content_included must be false")

    value = packet.get("value")
    if not isinstance(value, dict):
        issues.append("stats packet: value must be an object")
    else:
        numerator = value.get("numerator")
        denominator = value.get("denominator")
        number = value.get("number")
        if not isinstance(numerator, int) or not isinstance(denominator, int) or denominator <= 0:
            issues.append("stats packet: numerator/denominator must be a positive census")
        elif not isinstance(number, (int, float)) or number != numerator / denominator:
            issues.append("stats packet: number must equal numerator / denominator")

    return issues


def main() -> int:
    issues = validate_local_stats()
    if issues:
        for issue in issues:
            print(f"[error] {issue}")
        return 1
    print("[ok] ATM10 local measurement contract validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
