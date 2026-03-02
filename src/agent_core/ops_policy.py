from __future__ import annotations

from typing import Any

# Gateway fail_nightly baseline policy for readiness/governance/progress/transition.
READINESS_WINDOW = 14
REQUIRED_BASELINE_COUNT = 5
MAX_WARN_RATIO = 0.20
REQUIRED_READY_STREAK = 3

# Ops visibility defaults.
SOURCE_STALE_AFTER_HOURS = 36
GATEWAY_SLA_PROFILE = "conservative"
SWITCH_SURFACE = "nightly_only"


def readiness_baseline() -> dict[str, Any]:
    return {
        "readiness_window": READINESS_WINDOW,
        "required_baseline_count": REQUIRED_BASELINE_COUNT,
        "max_warn_ratio": MAX_WARN_RATIO,
    }


def governance_baseline() -> dict[str, Any]:
    return {
        "required_ready_streak": REQUIRED_READY_STREAK,
        "expected_readiness_window": READINESS_WINDOW,
        "expected_required_baseline_count": REQUIRED_BASELINE_COUNT,
        "expected_max_warn_ratio": MAX_WARN_RATIO,
    }
