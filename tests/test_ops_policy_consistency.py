from __future__ import annotations

import sys

import pytest

import scripts.build_ops_contract_index as index_builder
import scripts.check_gateway_sla_fail_nightly_governance as governance_checker
import scripts.check_gateway_sla_fail_nightly_progress as progress_checker
import scripts.check_gateway_sla_fail_nightly_readiness as readiness_checker
import scripts.check_gateway_sla_fail_nightly_transition as transition_checker
import scripts.validate_ops_contracts as validator
from src.agent_core import ops_policy


def test_gateway_readiness_defaults_follow_ops_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_fail_nightly_readiness.py"])
    args = readiness_checker.parse_args()
    assert args.readiness_window == ops_policy.READINESS_WINDOW
    assert args.required_baseline_count == ops_policy.REQUIRED_BASELINE_COUNT
    assert args.max_warn_ratio == ops_policy.MAX_WARN_RATIO


def test_gateway_governance_defaults_follow_ops_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_fail_nightly_governance.py"])
    args = governance_checker.parse_args()
    assert args.required_ready_streak == ops_policy.REQUIRED_READY_STREAK
    assert args.expected_readiness_window == ops_policy.READINESS_WINDOW
    assert args.expected_required_baseline_count == ops_policy.REQUIRED_BASELINE_COUNT
    assert args.expected_max_warn_ratio == ops_policy.MAX_WARN_RATIO


def test_gateway_progress_defaults_follow_ops_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_fail_nightly_progress.py"])
    args = progress_checker.parse_args()
    assert args.required_ready_streak == ops_policy.REQUIRED_READY_STREAK
    assert args.expected_readiness_window == ops_policy.READINESS_WINDOW
    assert args.expected_required_baseline_count == ops_policy.REQUIRED_BASELINE_COUNT
    assert args.expected_max_warn_ratio == ops_policy.MAX_WARN_RATIO


def test_gateway_transition_defaults_follow_ops_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_gateway_sla_fail_nightly_transition.py"])
    args = transition_checker.parse_args()
    assert args.required_ready_streak == ops_policy.REQUIRED_READY_STREAK
    assert args.expected_readiness_window == ops_policy.READINESS_WINDOW
    assert args.expected_required_baseline_count == ops_policy.REQUIRED_BASELINE_COUNT
    assert args.expected_max_warn_ratio == ops_policy.MAX_WARN_RATIO


def test_validator_and_index_defaults_follow_ops_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["validate_ops_contracts.py", "--profile", "ci_smoke"])
    validator_args = validator.parse_args()
    assert validator_args.policy == "report_only"

    monkeypatch.setattr(sys, "argv", ["build_ops_contract_index.py", "--profile", "ci_smoke"])
    index_args = index_builder.parse_args()
    assert index_args.stale_after_hours == ops_policy.SOURCE_STALE_AFTER_HOURS
