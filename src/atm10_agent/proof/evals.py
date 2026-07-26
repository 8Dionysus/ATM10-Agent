"""Bounded ATM10 eval specifications, case results, and reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from atm10_agent.proof.measurements import MetricDefinition, MetricObservation
from atm10_agent.proof.provenance import ProvenanceRef


EVAL_REPORT_SCHEMA_VERSION = "atm10_eval_report_v2"
CASE_STATUSES = {"pass", "fail", "error"}
VERDICT_SUPPORTS = "supports_bounded_claim"
VERDICT_MIXED = "mixed_support"
VERDICT_DOES_NOT_SUPPORT = "does_not_support_bounded_claim"


def _validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at_utc must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("observed_at_utc must include a timezone")


@dataclass(frozen=True)
class EvalSpec:
    """The invariant meaning of an eval, separate from its runner details."""

    suite_id: str
    bounded_claim: str
    in_scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    case_ids: tuple[str, ...]
    portability_invariants: tuple[str, ...]
    replaceable_surfaces: tuple[str, ...]
    claim_limit: str

    def __post_init__(self) -> None:
        for name, value in (
            ("suite_id", self.suite_id),
            ("bounded_claim", self.bounded_claim),
            ("claim_limit", self.claim_limit),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        for name, values in (
            ("in_scope", self.in_scope),
            ("out_of_scope", self.out_of_scope),
            ("case_ids", self.case_ids),
            ("portability_invariants", self.portability_invariants),
            ("replaceable_surfaces", self.replaceable_surfaces),
        ):
            if not values or any(not item.strip() for item in values):
                raise ValueError(f"{name} must contain non-empty values")
            if len(set(values)) != len(values):
                raise ValueError(f"{name} values must be unique")
        if set(self.in_scope) & set(self.out_of_scope):
            raise ValueError("in_scope and out_of_scope must not overlap")

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "bounded_claim": self.bounded_claim,
            "in_scope": list(self.in_scope),
            "out_of_scope": list(self.out_of_scope),
            "case_ids": list(self.case_ids),
            "portability": {
                "invariants": list(self.portability_invariants),
                "replaceable_surfaces": list(self.replaceable_surfaces),
            },
            "claim_limit": self.claim_limit,
        }


@dataclass(frozen=True)
class EvalCaseResult:
    """One deterministic case result with local evidence and limitations."""

    case_id: str
    status: str
    protects: tuple[str, ...]
    observed: Mapping[str, Any]
    evidence: tuple[ProvenanceRef, ...]
    limitation: str
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be empty")
        if self.status not in CASE_STATUSES:
            raise ValueError(f"unsupported eval case status: {self.status!r}")
        if not self.protects or any(not item.strip() for item in self.protects):
            raise ValueError("protects must contain non-empty contract refs")
        if not self.evidence:
            raise ValueError("eval case evidence must not be empty")
        if not self.limitation.strip():
            raise ValueError("eval case limitation must not be empty")
        if self.status == "error" and not (self.error or "").strip():
            raise ValueError("error cases must carry an error")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.case_id,
            "status": self.status,
            "protects": list(self.protects),
            "observed": dict(self.observed),
            "evidence": [item.to_dict() for item in self.evidence],
            "limitation": self.limitation,
        }
        if self.error is not None:
            payload["error"] = self.error
        return payload


def _verdict(cases: tuple[EvalCaseResult, ...]) -> str:
    passed = sum(case.status == "pass" for case in cases)
    if passed == len(cases):
        return VERDICT_SUPPORTS
    if passed:
        return VERDICT_MIXED
    return VERDICT_DOES_NOT_SUPPORT


def build_eval_report(
    *,
    spec: EvalSpec,
    cases: tuple[EvalCaseResult, ...],
    observed_at_utc: str,
    provenance: tuple[ProvenanceRef, ...],
    blind_spots: tuple[str, ...],
    storage: Mapping[str, str],
    report_path: str,
    network_required: bool,
    live_services_required: bool,
    real_input_emitted: bool,
) -> dict[str, Any]:
    """Build a report whose verdict never exceeds its named bounded claim."""

    _validate_timestamp(observed_at_utc)
    if not cases:
        raise ValueError("eval report requires at least one case")
    if tuple(case.case_id for case in cases) != spec.case_ids:
        raise ValueError("eval report cases must match spec case_ids in order")
    if not provenance:
        raise ValueError("eval report provenance must not be empty")
    if not blind_spots or any(not item.strip() for item in blind_spots):
        raise ValueError("eval report must disclose non-empty blind spots")
    if not report_path.strip():
        raise ValueError("report_path must not be empty")

    passed_count = sum(case.status == "pass" for case in cases)
    failed_count = len(cases) - passed_count
    error_count = sum(case.status == "error" for case in cases)
    verdict = _verdict(cases)
    metric_evidence = (
        *provenance,
        ProvenanceRef(kind="artifact", ref=report_path, role="derived"),
    )
    metrics = (
        MetricObservation(
            definition=MetricDefinition(
                metric_id="eval.case_count",
                description="Number of deterministic cases executed in this suite.",
                unit="case",
                window="one suite run",
                zero_is_observation=False,
            ),
            status="observed",
            observed_at_utc=observed_at_utc,
            value=len(cases),
            evidence=metric_evidence,
        ),
        MetricObservation(
            definition=MetricDefinition(
                metric_id="eval.passed_count",
                description="Number of executed cases whose bounded checks passed.",
                unit="case",
                window="one suite run",
                zero_is_observation=True,
            ),
            status="observed",
            observed_at_utc=observed_at_utc,
            value=passed_count,
            evidence=metric_evidence,
        ),
        MetricObservation(
            definition=MetricDefinition(
                metric_id="eval.failed_or_error_count",
                description="Number of executed cases that failed or errored.",
                unit="case",
                window="one suite run",
                zero_is_observation=True,
            ),
            status="observed",
            observed_at_utc=observed_at_utc,
            value=failed_count,
            evidence=metric_evidence,
        ),
    )

    return {
        "schema_version": EVAL_REPORT_SCHEMA_VERSION,
        "suite_id": spec.suite_id,
        "status": "pass" if verdict == VERDICT_SUPPORTS else "fail",
        "verdict": verdict,
        "claim": {
            "bounded": spec.bounded_claim,
            "authority": "ATM10-Agent",
            "claim_limit": spec.claim_limit,
        },
        "scope": {
            "in": list(spec.in_scope),
            "out": list(spec.out_of_scope),
        },
        "portability": {
            "invariants": list(spec.portability_invariants),
            "replaceable_surfaces": list(spec.replaceable_surfaces),
        },
        "observed_at_utc": observed_at_utc,
        "case_count": len(cases),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "error_count": error_count,
        "network_required": network_required,
        "live_services_required": live_services_required,
        "real_input_emitted": real_input_emitted,
        "metrics": [item.to_dict() for item in metrics],
        "blind_spots": list(blind_spots),
        "provenance": [item.to_dict() for item in provenance],
        "storage": dict(storage),
        "cases": [case.to_dict() for case in cases],
        "report_path": report_path,
    }
