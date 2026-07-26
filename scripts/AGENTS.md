# AGENTS.md

Local guidance for `scripts/` in `ATM10-Agent`.

Read the root `AGENTS.md` first. This file only adds local rules for runnable entrypoints and operator tooling.

## Scope

This directory is the transitional compatibility and maintainer-tool shell of
the repo. It still contains smoke paths, demos, legacy operator startup,
gateway flows, retrieval and KAG runners, audits, policy checks, export
helpers, and PowerShell launchers while protected behavior moves into the
installable `atm10_agent` package.

Representative surfaces include:

- `phase_a_smoke.py`
- `start_operator_product.py`
- `gateway_v1_local.py`, `gateway_v1_http_service.py`, `gateway_v1_http_smoke.py`
- `retrieve_demo.py`, `eval_retrieval.py`, `normalize_ftbquests.py`, `ingest_qdrant.py`
- `kag_build_baseline.py`, `kag_sync_neo4j.py`, `kag_query_demo.py`, `kag_query_neo4j.py`
- thin package-compatibility wrappers `automation_dry_run.py` and
  `intent_to_automation_plan.py`, plus the transitional
  `automation_intent_chain_smoke.py`
- `cross_service_benchmark_suite.py`, `run_combo_a_operating_cycle.py`
- `pilot_runtime_loop.py`, `operator_product_snapshot.py`, `streamlit_operator_panel.py`

`cross_service_benchmark_suite.py` owns the live evidence artifact used by the
local stats surface. `validate_local_stats_port.py` validates that contract
entirely from repository-owned files; keep measurement meaning under `stats/`.

## Local contract

- The product composition root is `atm10_agent.app.CompanionApp`; scripts may
  expose compatibility or focused maintainer operations but may not become a
  second application.
- Do not add new product semantics here. Move reusable behavior into its owning
  package module and keep any proven-consumer wrapper thin.
- Keep proven compatibility CLI flags, artifact paths, and public-facing
  behavior stable until their consumer is migrated or explicitly retired.
- Prefer `pathlib`, explicit arguments, and `--runs-dir` driven artifacts over hidden local defaults.
- Keep dry-run or report-only behavior as the default for automation and policy surfaces unless the task explicitly requires stronger behavior.
- Preserve baseline defaults and keep `combo_a` additive.
- Keep public examples loopback-safe and token-safe. Use env or config patterns such as `ATM10_SERVICE_TOKEN` and `NEO4J_PASSWORD`.

## Change rules

- PowerShell wrappers should stay thin launchers, not hidden policy forks.
- If a script changes artifact schema, readiness checks, or documented commands, update the matching tests and the canonical docs in the same change.
- If decision-index tooling changes, update `docs/decisions/AGENTS.md`, regenerate indexes, and run the decision validator.
- Avoid hidden machine mutation, destructive host actions, or workstation-specific assumptions.

## Validate

At minimum, run full pytest plus the nearest smoke or contract path for the edited surface.

Useful commands:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pytest
python -m scripts.phase_a_smoke --vlm-provider stub --runs-dir runs\smoke-phase-a
python -m scripts.retrieve_demo --in tests/fixtures/retrieval_docs_sample.jsonl --query "mekanism steel" --topk 3 --candidate-k 10 --reranker none --runs-dir runs\smoke-retrieve
atm10 eval --suite companion-core --runs-dir runs\eval --state-dir .atm10-state\eval --reports-dir eval-results
python -m scripts.generate_decision_indexes --check
python -m scripts.validate_decision_records
```
