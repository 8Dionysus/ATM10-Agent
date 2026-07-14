# AGENTS.md

Route card for owner-local statistical questions in `ATM10-Agent`.
Read the root `AGENTS.md` first.
Use `<repo-root>` as the portable repository placeholder.

## Applies to

Everything under `stats/`.

## Role

This directory owns questions, populations, evidence routes, privacy posture,
and authority ceilings whose meaning belongs to the local companion. Shared
measurement grammar and cross-owner composition remain owned by `aoa-stats`.

## Read before editing

1. Root `AGENTS.md`, `MANIFEST.md`, and `docs/SOURCE_OF_TRUTH.md`.
2. `stats/README.md` and `stats/port.manifest.json`.
3. `scripts/cross_service_benchmark_suite.py` and
   `src/agent_core/service_sla.py`.
4. The central measurement and packet contracts under `aoa-stats/stats/`.

## Boundaries

- The expected service lanes are profile-owned and form an exact census; a
  missing expected lane makes the ratio unknown instead of shrinking the
  denominator.
- A complete suite in which every expected lane breaches is an observed zero.
- The ratio counts each lane's own SLA verdict. It does not aggregate latency,
  retrieval quality, audio quality, or other heterogeneous child metrics.
- An incomplete, malformed, unsupported, or internally contradictory
  `cross_service_benchmark_suite_v1` artifact is unknown, not zero.
- Raw run paths, child samples, secrets, host state, and session evidence do
  not enter portable packets.
- The ratio does not establish operator readiness, gameplay success, host
  health, product support, or an eval verdict.

## Validation

Inspect the producer artifact and packet first, then run:

```powershell
python scripts/validate_local_stats_port.py
python -m pytest tests/test_local_stats_port.py tests/test_cross_service_benchmark_suite.py tests/test_service_sla.py
```

Use the root route for repository-wide validation.

## Closeout

Report the local question, profile population, manual positive and negative
cases, live/reference posture, central validation, and repository validation.
