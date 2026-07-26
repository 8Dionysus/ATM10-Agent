"""Typed ATM10 measurements with explicit missingness and authority ceiling."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import math
import re
from typing import Any

from atm10_agent.proof.provenance import ProvenanceRef


MEASUREMENT_SCHEMA_VERSION = "atm10_measurement_observation_v1"
MEASUREMENT_STATUSES = {"observed", "missing", "unknown", "stale"}
MEASUREMENT_AUTHORITY_CEILING = "measurement_only_not_proof"
_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")


def _validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at_utc must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("observed_at_utc must include a timezone")


@dataclass(frozen=True)
class MetricDefinition:
    """The calculation and interpretation contract for one local metric."""

    metric_id: str
    description: str
    unit: str
    window: str
    zero_is_observation: bool
    authority_ceiling: str = MEASUREMENT_AUTHORITY_CEILING

    def __post_init__(self) -> None:
        for name, value in (
            ("metric_id", self.metric_id),
            ("description", self.description),
            ("unit", self.unit),
            ("window", self.window),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.authority_ceiling != MEASUREMENT_AUTHORITY_CEILING:
            raise ValueError(
                f"authority_ceiling must be {MEASUREMENT_AUTHORITY_CEILING!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetricObservation:
    """One observed or explicitly unavailable value with evidence handles."""

    definition: MetricDefinition
    status: str
    observed_at_utc: str
    evidence: tuple[ProvenanceRef, ...]
    value: int | float | None = None
    source_revision: str | None = None
    notes: str | None = None
    schema_version: str = MEASUREMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in MEASUREMENT_STATUSES:
            raise ValueError(f"unsupported measurement status: {self.status!r}")
        _validate_timestamp(self.observed_at_utc)
        if not self.evidence:
            raise ValueError("measurement evidence must not be empty")
        if self.source_revision is not None and not _GIT_REVISION.fullmatch(
            self.source_revision
        ):
            raise ValueError("source_revision must be a 40-character git SHA")

        if self.status == "observed":
            if (
                isinstance(self.value, bool)
                or not isinstance(self.value, (int, float))
                or not math.isfinite(float(self.value))
            ):
                raise ValueError("observed measurement requires a finite numeric value")
            if self.value == 0 and not self.definition.zero_is_observation:
                raise ValueError("zero is not an observation for this metric")
        elif self.value is not None:
            raise ValueError(f"{self.status} measurement must not carry a value")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "definition": self.definition.to_dict(),
            "status": self.status,
            "observed_at_utc": self.observed_at_utc,
            "value": self.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "source_revision": self.source_revision,
            "notes": self.notes,
        }
