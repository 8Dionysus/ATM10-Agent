from __future__ import annotations

import pytest

from atm10_agent.proof import EvalCaseResult, EvalSpec, ProvenanceRef, build_eval_report


OBSERVED_AT = "2026-07-25T13:00:00+00:00"
SOURCE = ProvenanceRef(
    kind="source",
    ref="atm10_agent.evals:test-suite",
    role="primary",
)


def _spec() -> EvalSpec:
    return EvalSpec(
        suite_id="test-suite",
        bounded_claim="Two local deterministic cases execute their named checks.",
        in_scope=("local deterministic cases",),
        out_of_scope=("live provider quality",),
        case_ids=("case-a", "case-b"),
        portability_invariants=("case meaning", "verdict mapping"),
        replaceable_surfaces=("clock", "artifact directory"),
        claim_limit="This report does not establish product benefit.",
    )


def _case(case_id: str, status: str) -> EvalCaseResult:
    return EvalCaseResult(
        case_id=case_id,
        status=status,
        protects=("PB-TEST",),
        observed={"checked": True},
        evidence=(
            ProvenanceRef(
                kind="test",
                ref=f"tests/{case_id}.py",
            ),
        ),
        limitation="The case is deterministic and does not exercise a live provider.",
        error="RuntimeError: fixture failed" if status == "error" else None,
    )


def _report(statuses: tuple[str, str]) -> dict[str, object]:
    return build_eval_report(
        spec=_spec(),
        cases=(
            _case("case-a", statuses[0]),
            _case("case-b", statuses[1]),
        ),
        observed_at_utc=OBSERVED_AT,
        provenance=(SOURCE,),
        blind_spots=("No live provider is exercised.",),
        storage={"reports_root": "eval-results"},
        report_path="eval-results/report.json",
        network_required=False,
        live_services_required=False,
        real_input_emitted=False,
    )


def test_eval_report_supports_only_its_bounded_claim() -> None:
    report = _report(("pass", "pass"))

    assert report["schema_version"] == "atm10_eval_report_v2"
    assert report["status"] == "pass"
    assert report["verdict"] == "supports_bounded_claim"
    assert report["claim"]["authority"] == "ATM10-Agent"
    assert report["scope"]["out"] == ["live provider quality"]
    assert report["blind_spots"]
    assert len(report["metrics"]) == 3
    assert {
        metric["definition"]["authority_ceiling"] for metric in report["metrics"]
    } == {"measurement_only_not_proof"}
    assert report["metrics"][0]["evidence"][-1] == {
        "ref": "eval-results/report.json",
        "kind": "artifact",
        "role": "derived",
        "owner": "ATM10-Agent",
        "revision": None,
    }


@pytest.mark.parametrize(
    ("statuses", "verdict"),
    [
        (("pass", "fail"), "mixed_support"),
        (("fail", "error"), "does_not_support_bounded_claim"),
    ],
)
def test_eval_verdict_is_categorical_and_failure_sensitive(
    statuses: tuple[str, str],
    verdict: str,
) -> None:
    report = _report(statuses)

    assert report["status"] == "fail"
    assert report["verdict"] == verdict


def test_eval_report_rejects_case_drift_and_missing_blind_spots() -> None:
    with pytest.raises(ValueError, match="match spec case_ids"):
        build_eval_report(
            spec=_spec(),
            cases=(_case("case-b", "pass"), _case("case-a", "pass")),
            observed_at_utc=OBSERVED_AT,
            provenance=(SOURCE,),
            blind_spots=("No live provider is exercised.",),
            storage={"reports_root": "eval-results"},
            report_path="eval-results/report.json",
            network_required=False,
            live_services_required=False,
            real_input_emitted=False,
        )
    with pytest.raises(ValueError, match="blind spots"):
        build_eval_report(
            spec=_spec(),
            cases=(_case("case-a", "pass"), _case("case-b", "pass")),
            observed_at_utc=OBSERVED_AT,
            provenance=(SOURCE,),
            blind_spots=(),
            storage={"reports_root": "eval-results"},
            report_path="eval-results/report.json",
            network_required=False,
            live_services_required=False,
            real_input_emitted=False,
        )


def test_provenance_ref_rejects_unknown_kind_and_short_revision() -> None:
    with pytest.raises(ValueError, match="unsupported provenance kind"):
        ProvenanceRef(kind="memory", ref="candidate")
    with pytest.raises(ValueError, match="40-character git SHA"):
        ProvenanceRef(kind="revision", ref="commit", revision="198f223")
