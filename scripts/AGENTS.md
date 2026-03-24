# AGENTS.md

Local guidance for `scripts/` in `ATM10-Agent`.

Read the root `AGENTS.md` first. This file only adds local rules for runnable entrypoints and operator tooling.

## Scope

This directory is the operational shell of the repo. It owns smoke paths, demos, operator startup, gateway flows, retrieval and KAG runners, audits, policy checks, export helpers, and PowerShell launchers.

Representative surfaces include:

- `phase_a_smoke.py`
- `start_operator_product.py`
- `gateway_v1_local.py`, `gateway_v1_http_service.py`, `gateway_v1_http_smoke.py`
- `retrieve_demo.py`, `eval_retrieval.py`, `normalize_ftbquests.py`, `ingest_qdrant.py`
- `kag_build_baseline.py`, `kag_sync_neo4j.py`, `kag_query_demo.py`, `kag_query_neo4j.py`
- `automation_dry_run.py`, `intent_to_automation_plan.py`, `automation_intent_chain_smoke.py`
- `cross_service_benchmark_suite.py`, `run_combo_a_operating_cycle.py`
- `pilot_runtime_loop.py`, `operator_product_snapshot.py`, `streamlit_operator_panel.py`

## Local contract

- Treat these scripts as canonical runnable surfaces. Keep CLI flags, artifact paths, and public-facing behavior stable unless the task explicitly changes the contract.
- Prefer `pathlib`, explicit arguments, and `--runs-dir` driven artifacts over hidden local defaults.
- Keep dry-run or report-only behavior as the default for automation and policy surfaces unless the task explicitly requires stronger behavior.
- Preserve baseline defaults and keep `combo_a` additive.
- Keep public examples loopback-safe and token-safe. Use env or config patterns such as `ATM10_SERVICE_TOKEN` and `NEO4J_PASSWORD`.

## Change rules

- PowerShell wrappers should stay thin launchers, not hidden policy forks.
- If a script changes artifact schema, readiness checks, or documented commands, update the matching tests and the canonical docs in the same change.
- Avoid hidden machine mutation, destructive host actions, or workstation-specific assumptions.

## Validate

At minimum, run full pytest plus the nearest smoke or contract path for the edited surface.

Useful commands:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pytest
python scripts/phase_a_smoke.py --vlm-provider stub --runs-dir runs\smoke-phase-a
python scripts/retrieve_demo.py --in tests/fixtures/retrieval_docs_sample.jsonl --query "mekanism steel" --topk 3 --candidate-k 10 --reranker none --runs-dir runs\smoke-retrieve
python scripts/automation_intent_chain_smoke.py --intent-json tests/fixtures/intent_open_quest_book.json --runs-dir runs\smoke-intent
```
