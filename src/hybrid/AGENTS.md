# AGENTS.md

Local guidance for `src/hybrid/` in `ATM10-Agent`.

Read the root `AGENTS.md` first. This file only adds local rules for hybrid planner behavior.

## Scope

This directory currently centers on `planner.py`, the merge and orchestration layer between retrieval and KAG.

## Local contract

- Keep `baseline_first` as the default planning posture unless the task explicitly changes the public contract.
- Keep `combo_a` additive. It may enrich retrieval and KAG wiring, but it must not silently replace the baseline default.
- Preserve explicit fallback behavior on KAG degradation. Retrieval-only fallback should be intentional and surfaced, not accidental.
- Keep merge, ranking, and citation rationale deterministic enough for fixture-driven tests.

## Change rules

- Treat score fusion, citation ordering, and fallback policy as semantic changes.
- If `planner.py` changes user-visible behavior, update the matching scripts, gateway surfaces, and tests in the same diff.
- Avoid burying policy decisions in convenience helpers without tests.

## Validate

Run the nearest hybrid and gateway-contract coverage:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_hybrid_query_demo.py tests/test_gateway_v1_local.py tests/test_gateway_v1_contract_parity_matrix.py tests/test_cross_service_benchmark_suite.py
```
