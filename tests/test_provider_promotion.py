from __future__ import annotations

import pytest

from atm10_agent.proof import ProvenanceRef
from atm10_agent.providers import (
    ProviderEvidence,
    build_promotion_candidate,
    compare_provider_evidence,
    record_post_activation_check,
    record_provider_activation,
    record_provider_rollback,
    review_promotion_candidate,
)


OBSERVED_AT = "2026-07-26T05:00:00+00:00"
REVIEWED_AT = "2026-07-26T05:10:00+00:00"
ACTIVATED_AT = "2026-07-26T05:20:00+00:00"
CHECKED_AT = "2026-07-26T05:30:00+00:00"
ROLLED_BACK_AT = "2026-07-26T05:40:00+00:00"


def _ref(name: str) -> ProvenanceRef:
    return ProvenanceRef(kind="artifact", ref=name, role="primary")


def _benchmark(
    evidence_id: str,
    provider_id: str,
    latency_ms: float,
    *,
    host_scope: str = "linux:test-host-class",
    fixture_scope: str = "fixture:companion-turn-v1",
    benchmark_family: str = "latency-single-turn",
) -> ProviderEvidence:
    return ProviderEvidence(
        evidence_id=evidence_id,
        provider_id=provider_id,
        kind="benchmark",
        status="pass",
        observed_at_utc=OBSERVED_AT,
        host_scope=host_scope,
        fixture_scope=fixture_scope,
        benchmark_family=benchmark_family,
        contract_fit=True,
        metrics={"latency_ms": latency_ms},
        evidence_refs=(_ref(evidence_id),),
        limitations=("One bounded fixture on one Linux host class.",),
    )


def _machine_fit(provider_id: str) -> ProviderEvidence:
    return ProviderEvidence(
        evidence_id=f"fit:{provider_id}",
        provider_id=provider_id,
        kind="machine_fit",
        status="pass",
        observed_at_utc=OBSERVED_AT,
        host_scope="linux:test-host-class",
        fixture_scope=None,
        benchmark_family=None,
        contract_fit=True,
        evidence_refs=(_ref(f"fit:{provider_id}"),),
        limitations=("Public-safe synthetic host class only.",),
    )


def _candidate_chain() -> tuple[dict[str, object], dict[str, object]]:
    comparison = compare_provider_evidence(
        comparison_id="comparison:text-provider",
        current=_benchmark("bench:current", "current-local", 125.0),
        challenger=_benchmark("bench:challenger", "challenger-local", 90.0),
        metric="latency_ms",
        lower_is_better=True,
    )
    candidate = build_promotion_candidate(
        candidate_id="candidate:text-provider",
        capability="response.text",
        comparison=comparison,
        machine_fit=_machine_fit("challenger-local"),
        proposed_at_utc=OBSERVED_AT,
    )
    return comparison, candidate


def test_bounded_comparison_never_auto_promotes() -> None:
    comparison, candidate = _candidate_chain()

    assert comparison["status"] == "comparable"
    assert comparison["verdict"] == "challenger_better"
    assert comparison["delta"] == -35.0
    assert comparison["automatic_promotion"] is False
    assert candidate["status"] == "candidate"
    assert candidate["review_required"] is True
    assert candidate["automatic_activation"] is False
    assert candidate["production_status"] == "not_active"


def test_comparison_rejects_host_or_fixture_drift() -> None:
    comparison = compare_provider_evidence(
        comparison_id="comparison:drifted",
        current=_benchmark("bench:current", "current-local", 125.0),
        challenger=_benchmark(
            "bench:challenger",
            "challenger-local",
            90.0,
            host_scope="linux:different-host-class",
            fixture_scope="fixture:different",
            benchmark_family="throughput-stream",
        ),
        metric="latency_ms",
        lower_is_better=True,
    )

    assert comparison["status"] == "not_comparable"
    assert comparison["verdict"] == "not_comparable"
    assert set(comparison["not_comparable_reasons"]) == {
        "host_scope_mismatch",
        "fixture_scope_mismatch",
        "benchmark_family_mismatch",
    }
    with pytest.raises(ValueError, match="comparable evidence"):
        build_promotion_candidate(
            candidate_id="candidate:drifted",
            capability="response.text",
            comparison=comparison,
            machine_fit=_machine_fit("challenger-local"),
            proposed_at_utc=OBSERVED_AT,
        )


def test_promotion_candidate_requires_machine_fit_for_comparison_host() -> None:
    comparison = compare_provider_evidence(
        comparison_id="comparison:text-provider",
        current=_benchmark("bench:current", "current-local", 125.0),
        challenger=_benchmark("bench:challenger", "challenger-local", 90.0),
        metric="latency_ms",
        lower_is_better=True,
    )
    wrong_host_fit = ProviderEvidence(
        evidence_id="fit:wrong-host",
        provider_id="challenger-local",
        kind="machine_fit",
        status="pass",
        observed_at_utc=OBSERVED_AT,
        host_scope="linux:different-host-class",
        fixture_scope=None,
        benchmark_family=None,
        contract_fit=True,
        evidence_refs=(_ref("fit:wrong-host"),),
        limitations=("Synthetic mismatch.",),
    )

    with pytest.raises(ValueError, match="machine_fit host"):
        build_promotion_candidate(
            candidate_id="candidate:wrong-host",
            capability="response.text",
            comparison=comparison,
            machine_fit=wrong_host_fit,
            proposed_at_utc=OBSERVED_AT,
        )


def test_approved_candidate_stays_inactive_until_explicit_activation() -> None:
    _, candidate = _candidate_chain()
    review = review_promotion_candidate(
        candidate=candidate,
        decision="approve",
        reviewed_by="operator:test",
        reviewed_at_utc=REVIEWED_AT,
        evidence_refs=(_ref("review:text-provider"),),
    )

    assert review["status"] == "approved_not_active"
    assert review["production_status"] == "not_active"
    assert review["automatic_activation"] is False
    activation = record_provider_activation(
        review=review,
        activation_id="activation:text-provider",
        activated_by="operator:test",
        activated_at_utc=ACTIVATED_AT,
        activation_ref=_ref("config-change:text-provider"),
    )
    assert activation["status"] == "pending_post_activation_check"
    assert activation["production_status"] == "pending_verification"
    assert activation["automatic_activation"] is False


def test_rejected_candidate_cannot_be_activated() -> None:
    _, candidate = _candidate_chain()
    review = review_promotion_candidate(
        candidate=candidate,
        decision="reject",
        reviewed_by="operator:test",
        reviewed_at_utc=REVIEWED_AT,
        evidence_refs=(_ref("review:rejected"),),
    )

    assert review["status"] == "rejected"
    with pytest.raises(ValueError, match="approved_not_active"):
        record_provider_activation(
            review=review,
            activation_id="activation:forbidden",
            activated_by="operator:test",
            activated_at_utc=ACTIVATED_AT,
            activation_ref=_ref("config-change:forbidden"),
        )


def test_promotion_lifecycle_rejects_out_of_order_activation() -> None:
    _, candidate = _candidate_chain()
    review = review_promotion_candidate(
        candidate=candidate,
        decision="approve",
        reviewed_by="operator:test",
        reviewed_at_utc=REVIEWED_AT,
        evidence_refs=(_ref("review:text-provider"),),
    )

    with pytest.raises(ValueError, match="must follow review"):
        record_provider_activation(
            review=review,
            activation_id="activation:too-early",
            activated_by="operator:test",
            activated_at_utc="2026-07-26T05:05:00+00:00",
            activation_ref=_ref("config-change:too-early"),
        )


def test_failed_post_check_requires_explicit_rollback() -> None:
    _, candidate = _candidate_chain()
    review = review_promotion_candidate(
        candidate=candidate,
        decision="approve",
        reviewed_by="operator:test",
        reviewed_at_utc=REVIEWED_AT,
        evidence_refs=(_ref("review:text-provider"),),
    )
    activation = record_provider_activation(
        review=review,
        activation_id="activation:text-provider",
        activated_by="operator:test",
        activated_at_utc=ACTIVATED_AT,
        activation_ref=_ref("config-change:text-provider"),
    )
    failed_check = ProviderEvidence(
        evidence_id="check:failed",
        provider_id="challenger-local",
        kind="post_activation_check",
        status="fail",
        observed_at_utc=CHECKED_AT,
        host_scope="linux:test-host-class",
        fixture_scope="fixture:companion-turn-v1",
        benchmark_family=None,
        contract_fit=False,
        evidence_refs=(_ref("check:failed"),),
        limitations=("Synthetic failure path.",),
    )
    verification = record_post_activation_check(
        activation=activation,
        check=failed_check,
    )

    assert verification["status"] == "rollback_required"
    assert verification["automatic_rollback"] is False
    rollback = record_provider_rollback(
        verification=verification,
        rollback_id="rollback:text-provider",
        rolled_back_by="operator:test",
        rolled_back_at_utc=ROLLED_BACK_AT,
        rollback_ref=_ref("config-restore:text-provider"),
    )
    assert rollback["status"] == "rolled_back"
    assert rollback["failed_provider"] == "challenger-local"
    assert rollback["restored_provider"] == "current-local"
    assert rollback["automatic_rollback"] is False


def test_passing_post_check_marks_only_bounded_route_active() -> None:
    _, candidate = _candidate_chain()
    review = review_promotion_candidate(
        candidate=candidate,
        decision="approve",
        reviewed_by="operator:test",
        reviewed_at_utc=REVIEWED_AT,
        evidence_refs=(_ref("review:text-provider"),),
    )
    activation = record_provider_activation(
        review=review,
        activation_id="activation:text-provider",
        activated_by="operator:test",
        activated_at_utc=ACTIVATED_AT,
        activation_ref=_ref("config-change:text-provider"),
    )
    passed_check = ProviderEvidence(
        evidence_id="check:passed",
        provider_id="challenger-local",
        kind="post_activation_check",
        status="pass",
        observed_at_utc=CHECKED_AT,
        host_scope="linux:test-host-class",
        fixture_scope="fixture:companion-turn-v1",
        benchmark_family=None,
        contract_fit=True,
        evidence_refs=(_ref("check:passed"),),
        limitations=("One bounded live-lane check.",),
    )

    verification = record_post_activation_check(
        activation=activation,
        check=passed_check,
    )
    assert verification["status"] == "active"
    assert verification["production_status"] == "verified_active"
    assert "bounded active route" in verification["claim_limit"]
    with pytest.raises(ValueError, match="rollback_required"):
        record_provider_rollback(
            verification=verification,
            rollback_id="rollback:not-needed",
            rolled_back_by="operator:test",
            rolled_back_at_utc=ROLLED_BACK_AT,
            rollback_ref=_ref("rollback:not-needed"),
        )
