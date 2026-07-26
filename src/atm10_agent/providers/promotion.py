"""Reviewed ATM10 provider promotion records with explicit rollback posture."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
from typing import Any, Mapping

from atm10_agent.proof import ProvenanceRef


PROVIDER_EVIDENCE_SCHEMA_VERSION = "atm10_provider_evidence_v1"
PROVIDER_COMPARISON_SCHEMA_VERSION = "atm10_provider_comparison_v1"
PROVIDER_PROMOTION_CANDIDATE_SCHEMA_VERSION = (
    "atm10_provider_promotion_candidate_v1"
)
PROVIDER_PROMOTION_REVIEW_SCHEMA_VERSION = "atm10_provider_promotion_review_v1"
PROVIDER_ACTIVATION_SCHEMA_VERSION = "atm10_provider_activation_v1"
PROVIDER_POST_CHECK_SCHEMA_VERSION = "atm10_provider_post_activation_check_v1"
PROVIDER_ROLLBACK_SCHEMA_VERSION = "atm10_provider_rollback_v1"
PROVIDER_PROMOTION_AUTHORITY_CEILING = (
    "bounded_runtime_posture_not_general_provider_quality_proof"
)
PROVIDER_EVIDENCE_KINDS = {
    "machine_fit",
    "bounded_pilot",
    "benchmark",
    "post_activation_check",
}
PROVIDER_EVIDENCE_STATUSES = {"pass", "degraded", "fail", "unknown"}


def _validate_timestamp(name: str, value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


def _required_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _metric_value(name: str, value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"metric {name!r} must be a finite number")
    return float(value)


@dataclass(frozen=True)
class ProviderEvidence:
    """One bounded, public-safe evidence packet for a provider posture."""

    evidence_id: str
    provider_id: str
    kind: str
    status: str
    observed_at_utc: str
    host_scope: str
    fixture_scope: str | None
    benchmark_family: str | None
    contract_fit: bool
    evidence_refs: tuple[ProvenanceRef, ...]
    metrics: Mapping[str, float | int | None] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    schema_version: str = PROVIDER_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROVIDER_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported provider evidence schema_version")
        for name, value in (
            ("evidence_id", self.evidence_id),
            ("provider_id", self.provider_id),
            ("host_scope", self.host_scope),
        ):
            _required_text(name, value)
        if self.kind not in PROVIDER_EVIDENCE_KINDS:
            raise ValueError(f"unsupported provider evidence kind: {self.kind!r}")
        if self.status not in PROVIDER_EVIDENCE_STATUSES:
            raise ValueError(
                f"unsupported provider evidence status: {self.status!r}"
            )
        if self.kind in {"bounded_pilot", "benchmark"} and (
            self.fixture_scope is None or not self.fixture_scope.strip()
        ):
            raise ValueError(f"{self.kind} evidence requires fixture_scope")
        if self.kind in {"bounded_pilot", "benchmark"} and (
            self.benchmark_family is None or not self.benchmark_family.strip()
        ):
            raise ValueError(f"{self.kind} evidence requires benchmark_family")
        if self.kind not in {"bounded_pilot", "benchmark"} and (
            self.benchmark_family is not None
        ):
            raise ValueError(
                "benchmark_family is valid only for bounded_pilot or benchmark"
            )
        _validate_timestamp("observed_at_utc", self.observed_at_utc)
        if not self.evidence_refs:
            raise ValueError("provider evidence refs must not be empty")
        if any(not isinstance(item, ProvenanceRef) for item in self.evidence_refs):
            raise ValueError("provider evidence refs must use ProvenanceRef")
        for name, value in self.metrics.items():
            _required_text("metric name", str(name))
            if value is not None:
                _metric_value(str(name), value)
        if any(
            not isinstance(item, str) or not item.strip()
            for item in self.limitations
        ):
            raise ValueError("provider evidence limitations must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "provider_id": self.provider_id,
            "kind": self.kind,
            "status": self.status,
            "observed_at_utc": self.observed_at_utc,
            "host_scope": self.host_scope,
            "fixture_scope": self.fixture_scope,
            "benchmark_family": self.benchmark_family,
            "contract_fit": self.contract_fit,
            "metrics": dict(self.metrics),
            "evidence_refs": [item.to_dict() for item in self.evidence_refs],
            "limitations": list(self.limitations),
            "authority_ceiling": PROVIDER_PROMOTION_AUTHORITY_CEILING,
        }


def compare_provider_evidence(
    *,
    comparison_id: str,
    current: ProviderEvidence,
    challenger: ProviderEvidence,
    metric: str,
    lower_is_better: bool,
) -> dict[str, Any]:
    """Compare matched bounded packets without producing a promotion."""

    _required_text("comparison_id", comparison_id)
    _required_text("metric", metric)
    reasons: list[str] = []
    if current.provider_id == challenger.provider_id:
        reasons.append("providers_must_differ")
    if current.kind not in {"bounded_pilot", "benchmark"}:
        reasons.append("current_evidence_not_comparable_runtime_packet")
    if challenger.kind not in {"bounded_pilot", "benchmark"}:
        reasons.append("challenger_evidence_not_comparable_runtime_packet")
    if current.host_scope != challenger.host_scope:
        reasons.append("host_scope_mismatch")
    if current.fixture_scope != challenger.fixture_scope:
        reasons.append("fixture_scope_mismatch")
    if current.benchmark_family != challenger.benchmark_family:
        reasons.append("benchmark_family_mismatch")
    if current.kind != challenger.kind:
        reasons.append("evidence_kind_mismatch")
    if current.status != "pass" or challenger.status != "pass":
        reasons.append("evidence_status_not_pass")
    if not current.contract_fit or not challenger.contract_fit:
        reasons.append("contract_fit_not_pass")
    if metric not in current.metrics or metric not in challenger.metrics:
        reasons.append("comparison_metric_missing")

    current_value: float | None = None
    challenger_value: float | None = None
    if not reasons:
        try:
            current_value = _metric_value(metric, current.metrics[metric])
            challenger_value = _metric_value(metric, challenger.metrics[metric])
        except ValueError:
            reasons.append("comparison_metric_invalid")

    if reasons:
        verdict = "not_comparable"
        delta = None
    else:
        if current_value is None or challenger_value is None:
            raise ValueError("comparable metrics must resolve to numeric values")
        delta = challenger_value - current_value
        if challenger_value == current_value:
            verdict = "tie"
        elif (challenger_value < current_value) == lower_is_better:
            verdict = "challenger_better"
        else:
            verdict = "current_better"

    return {
        "schema_version": PROVIDER_COMPARISON_SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "status": "comparable" if not reasons else "not_comparable",
        "verdict": verdict,
        "current_provider": current.provider_id,
        "challenger_provider": challenger.provider_id,
        "current_observed_at_utc": current.observed_at_utc,
        "challenger_observed_at_utc": challenger.observed_at_utc,
        "host_scope": (
            current.host_scope if current.host_scope == challenger.host_scope else None
        ),
        "fixture_scope": (
            current.fixture_scope
            if current.fixture_scope == challenger.fixture_scope
            else None
        ),
        "benchmark_family": (
            current.benchmark_family
            if current.benchmark_family == challenger.benchmark_family
            else None
        ),
        "metric": metric,
        "lower_is_better": lower_is_better,
        "current_value": current_value,
        "challenger_value": challenger_value,
        "delta": delta,
        "not_comparable_reasons": reasons,
        "evidence_refs": [
            ProvenanceRef(
                kind="artifact",
                ref=current.evidence_id,
                role="supporting",
            ).to_dict(),
            ProvenanceRef(
                kind="artifact",
                ref=challenger.evidence_id,
                role="supporting",
            ).to_dict(),
        ],
        "automatic_promotion": False,
        "authority_ceiling": PROVIDER_PROMOTION_AUTHORITY_CEILING,
        "claim_limit": (
            "A matched bounded comparison is a runtime signal only; it does "
            "not establish general provider quality or activate a provider."
        ),
    }


def build_promotion_candidate(
    *,
    candidate_id: str,
    capability: str,
    comparison: Mapping[str, Any],
    machine_fit: ProviderEvidence,
    proposed_at_utc: str,
) -> dict[str, Any]:
    """Create a review candidate only after bounded fit and comparison pass."""

    for name, value in (("candidate_id", candidate_id), ("capability", capability)):
        _required_text(name, value)
    proposed_at = _validate_timestamp("proposed_at_utc", proposed_at_utc)
    challenger = str(comparison.get("challenger_provider", "")).strip()
    current = str(comparison.get("current_provider", "")).strip()
    if comparison.get("schema_version") != PROVIDER_COMPARISON_SCHEMA_VERSION:
        raise ValueError("promotion candidate requires a provider comparison")
    if comparison.get("status") != "comparable":
        raise ValueError("promotion candidate requires comparable evidence")
    if comparison.get("verdict") != "challenger_better":
        raise ValueError("promotion candidate requires challenger_better verdict")
    if machine_fit.kind != "machine_fit":
        raise ValueError("promotion candidate requires machine_fit evidence")
    if machine_fit.provider_id != challenger:
        raise ValueError("machine_fit provider must match comparison challenger")
    if machine_fit.status != "pass" or not machine_fit.contract_fit:
        raise ValueError("promotion candidate requires passing machine fit")
    if machine_fit.host_scope != comparison.get("host_scope"):
        raise ValueError("machine_fit host must match comparison host")
    evidence_times = (
        _validate_timestamp(
            "current_observed_at_utc",
            str(comparison.get("current_observed_at_utc", "")),
        ),
        _validate_timestamp(
            "challenger_observed_at_utc",
            str(comparison.get("challenger_observed_at_utc", "")),
        ),
        _validate_timestamp("machine_fit observed_at_utc", machine_fit.observed_at_utc),
    )
    if any(observed > proposed_at for observed in evidence_times):
        raise ValueError("promotion evidence must not postdate the candidate")

    return {
        "schema_version": PROVIDER_PROMOTION_CANDIDATE_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "capability": capability,
        "status": "candidate",
        "current_provider": current,
        "challenger_provider": challenger,
        "comparison_id": str(comparison.get("comparison_id", "")),
        "machine_fit_evidence_id": machine_fit.evidence_id,
        "host_scope": machine_fit.host_scope,
        "fixture_scope": comparison.get("fixture_scope"),
        "benchmark_family": comparison.get("benchmark_family"),
        "proposed_at_utc": proposed_at_utc,
        "review_required": True,
        "automatic_activation": False,
        "production_status": "not_active",
        "authority_ceiling": PROVIDER_PROMOTION_AUTHORITY_CEILING,
        "claim_limit": (
            "A candidate is eligible for review only; it is not approval, "
            "activation, or proof of general provider quality."
        ),
    }


def review_promotion_candidate(
    *,
    candidate: Mapping[str, Any],
    decision: str,
    reviewed_by: str,
    reviewed_at_utc: str,
    evidence_refs: tuple[ProvenanceRef, ...],
) -> dict[str, Any]:
    """Record an explicit ATM10-owned approve, reject, or hold decision."""

    if candidate.get("schema_version") != PROVIDER_PROMOTION_CANDIDATE_SCHEMA_VERSION:
        raise ValueError("review requires a provider promotion candidate")
    if candidate.get("status") != "candidate":
        raise ValueError("review requires candidate status")
    if decision not in {"approve", "reject", "hold"}:
        raise ValueError("promotion review decision must be approve, reject, or hold")
    _required_text("reviewed_by", reviewed_by)
    reviewed_at = _validate_timestamp("reviewed_at_utc", reviewed_at_utc)
    proposed_at = _validate_timestamp(
        "candidate proposed_at_utc",
        str(candidate.get("proposed_at_utc", "")),
    )
    if reviewed_at <= proposed_at:
        raise ValueError("promotion review must follow candidate creation")
    if not evidence_refs:
        raise ValueError("promotion review evidence refs must not be empty")
    review_status = {
        "approve": "approved_not_active",
        "reject": "rejected",
        "hold": "held",
    }[decision]
    return {
        "schema_version": PROVIDER_PROMOTION_REVIEW_SCHEMA_VERSION,
        "candidate_id": candidate["candidate_id"],
        "capability": candidate["capability"],
        "status": review_status,
        "decision": decision,
        "current_provider": candidate["current_provider"],
        "challenger_provider": candidate["challenger_provider"],
        "host_scope": candidate["host_scope"],
        "fixture_scope": candidate["fixture_scope"],
        "benchmark_family": candidate["benchmark_family"],
        "reviewed_by": reviewed_by,
        "reviewed_at_utc": reviewed_at_utc,
        "evidence_refs": [item.to_dict() for item in evidence_refs],
        "automatic_activation": False,
        "production_status": "not_active",
        "authority_ceiling": PROVIDER_PROMOTION_AUTHORITY_CEILING,
    }


def record_provider_activation(
    *,
    review: Mapping[str, Any],
    activation_id: str,
    activated_by: str,
    activated_at_utc: str,
    activation_ref: ProvenanceRef,
) -> dict[str, Any]:
    """Record an externally performed reviewed activation pending a live check."""

    if review.get("schema_version") != PROVIDER_PROMOTION_REVIEW_SCHEMA_VERSION:
        raise ValueError("activation requires a provider promotion review")
    if review.get("status") != "approved_not_active":
        raise ValueError("activation requires an approved_not_active review")
    for name, value in (
        ("activation_id", activation_id),
        ("activated_by", activated_by),
    ):
        _required_text(name, value)
    activated_at = _validate_timestamp("activated_at_utc", activated_at_utc)
    reviewed_at = _validate_timestamp(
        "review reviewed_at_utc",
        str(review.get("reviewed_at_utc", "")),
    )
    if activated_at <= reviewed_at:
        raise ValueError("provider activation must follow review")
    return {
        "schema_version": PROVIDER_ACTIVATION_SCHEMA_VERSION,
        "activation_id": activation_id,
        "candidate_id": review["candidate_id"],
        "capability": review["capability"],
        "status": "pending_post_activation_check",
        "previous_provider": review["current_provider"],
        "activated_provider": review["challenger_provider"],
        "host_scope": review["host_scope"],
        "fixture_scope": review["fixture_scope"],
        "benchmark_family": review["benchmark_family"],
        "activated_by": activated_by,
        "activated_at_utc": activated_at_utc,
        "activation_ref": activation_ref.to_dict(),
        "automatic_activation": False,
        "production_status": "pending_verification",
        "authority_ceiling": PROVIDER_PROMOTION_AUTHORITY_CEILING,
        "claim_limit": (
            "An activation record requires a separate post-activation check "
            "before the provider may be treated as the current verified route."
        ),
    }


def record_post_activation_check(
    *,
    activation: Mapping[str, Any],
    check: ProviderEvidence,
) -> dict[str, Any]:
    """Separate live-lane verification from the challenger and activation."""

    if activation.get("schema_version") != PROVIDER_ACTIVATION_SCHEMA_VERSION:
        raise ValueError("post-activation check requires an activation record")
    if activation.get("status") != "pending_post_activation_check":
        raise ValueError("activation is not awaiting a post-activation check")
    if check.kind != "post_activation_check":
        raise ValueError("activation verification requires post_activation_check evidence")
    if check.provider_id != activation.get("activated_provider"):
        raise ValueError("post-activation provider must match activated provider")
    if check.host_scope != activation.get("host_scope"):
        raise ValueError("post-activation host must match activation host")
    if check.fixture_scope != activation.get("fixture_scope"):
        raise ValueError("post-activation fixture must match activation fixture")
    checked_at = _validate_timestamp("check observed_at_utc", check.observed_at_utc)
    activated_at = _validate_timestamp(
        "activation activated_at_utc",
        str(activation.get("activated_at_utc", "")),
    )
    if checked_at <= activated_at:
        raise ValueError("post-activation check must follow activation")
    passed = check.status == "pass" and check.contract_fit
    return {
        "schema_version": PROVIDER_POST_CHECK_SCHEMA_VERSION,
        "activation_id": activation["activation_id"],
        "candidate_id": activation["candidate_id"],
        "capability": activation["capability"],
        "status": "active" if passed else "rollback_required",
        "previous_provider": activation["previous_provider"],
        "checked_provider": activation["activated_provider"],
        "host_scope": activation["host_scope"],
        "fixture_scope": activation["fixture_scope"],
        "benchmark_family": activation["benchmark_family"],
        "check_evidence_id": check.evidence_id,
        "checked_at_utc": check.observed_at_utc,
        "production_status": "verified_active" if passed else "degraded",
        "automatic_rollback": False,
        "authority_ceiling": PROVIDER_PROMOTION_AUTHORITY_CEILING,
        "claim_limit": (
            "A passing post-check verifies only this bounded active route; a "
            "failure requires explicit rollback and is not repaired automatically."
        ),
    }


def record_provider_rollback(
    *,
    verification: Mapping[str, Any],
    rollback_id: str,
    rolled_back_by: str,
    rolled_back_at_utc: str,
    rollback_ref: ProvenanceRef,
) -> dict[str, Any]:
    """Record explicit restoration of the previous provider after failed check."""

    if verification.get("schema_version") != PROVIDER_POST_CHECK_SCHEMA_VERSION:
        raise ValueError("rollback requires a post-activation check")
    if verification.get("status") != "rollback_required":
        raise ValueError("rollback requires rollback_required status")
    for name, value in (
        ("rollback_id", rollback_id),
        ("rolled_back_by", rolled_back_by),
    ):
        _required_text(name, value)
    rolled_back_at = _validate_timestamp("rolled_back_at_utc", rolled_back_at_utc)
    checked_at = _validate_timestamp(
        "verification checked_at_utc",
        str(verification.get("checked_at_utc", "")),
    )
    if rolled_back_at <= checked_at:
        raise ValueError("provider rollback must follow failed post-check")
    return {
        "schema_version": PROVIDER_ROLLBACK_SCHEMA_VERSION,
        "rollback_id": rollback_id,
        "activation_id": verification["activation_id"],
        "candidate_id": verification["candidate_id"],
        "capability": verification["capability"],
        "status": "rolled_back",
        "failed_provider": verification["checked_provider"],
        "restored_provider": verification["previous_provider"],
        "rolled_back_by": rolled_back_by,
        "rolled_back_at_utc": rolled_back_at_utc,
        "rollback_ref": rollback_ref.to_dict(),
        "automatic_rollback": False,
        "production_status": "restored_previous_provider",
        "authority_ceiling": PROVIDER_PROMOTION_AUTHORITY_CEILING,
    }
