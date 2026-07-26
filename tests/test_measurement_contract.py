from __future__ import annotations

import pytest

from atm10_agent.proof import MetricDefinition, MetricObservation, ProvenanceRef


OBSERVED_AT = "2026-07-25T13:00:00+00:00"
EVIDENCE = (
    ProvenanceRef(kind="artifact", ref="eval-results/report.json", role="primary"),
)


def _definition(*, zero_is_observation: bool) -> MetricDefinition:
    return MetricDefinition(
        metric_id="eval.case_count",
        description="Number of deterministic eval cases.",
        unit="case",
        window="one suite run",
        zero_is_observation=zero_is_observation,
    )


def test_observed_measurement_preserves_definition_and_evidence() -> None:
    observation = MetricObservation(
        definition=_definition(zero_is_observation=False),
        status="observed",
        observed_at_utc=OBSERVED_AT,
        value=7,
        evidence=EVIDENCE,
        source_revision="198f223a6a971c5088778f3273ea820c132e72f6",
    ).to_dict()

    assert observation["status"] == "observed"
    assert observation["value"] == 7
    assert observation["definition"]["unit"] == "case"
    assert observation["definition"]["window"] == "one suite run"
    assert observation["definition"]["authority_ceiling"] == "measurement_only_not_proof"
    assert observation["evidence"][0]["role"] == "primary"


@pytest.mark.parametrize("status", ["missing", "unknown", "stale"])
def test_unavailable_measurement_has_no_numeric_value(status: str) -> None:
    observation = MetricObservation(
        definition=_definition(zero_is_observation=False),
        status=status,
        observed_at_utc=OBSERVED_AT,
        value=None,
        evidence=EVIDENCE,
        notes=f"{status} is explicit",
    )

    assert observation.to_dict()["value"] is None


def test_zero_requires_an_explicit_observation_policy() -> None:
    with pytest.raises(ValueError, match="zero is not an observation"):
        MetricObservation(
            definition=_definition(zero_is_observation=False),
            status="observed",
            observed_at_utc=OBSERVED_AT,
            value=0,
            evidence=EVIDENCE,
        )

    observed_zero = MetricObservation(
        definition=_definition(zero_is_observation=True),
        status="observed",
        observed_at_utc=OBSERVED_AT,
        value=0,
        evidence=EVIDENCE,
    )
    assert observed_zero.value == 0


def test_measurement_rejects_hidden_values_and_missing_evidence() -> None:
    with pytest.raises(ValueError, match="must not carry a value"):
        MetricObservation(
            definition=_definition(zero_is_observation=True),
            status="unknown",
            observed_at_utc=OBSERVED_AT,
            value=3,
            evidence=EVIDENCE,
        )
    with pytest.raises(ValueError, match="evidence must not be empty"):
        MetricObservation(
            definition=_definition(zero_is_observation=True),
            status="observed",
            observed_at_utc=OBSERVED_AT,
            value=3,
            evidence=(),
        )
