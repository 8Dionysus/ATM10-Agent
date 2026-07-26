# AGENTS.md

Local guidance for `scripts/` in `ATM10-Agent`.

Read the root `AGENTS.md` first. This file only adds local rules for the
transitional maintainer-tool shell.

## Scope

This directory is the transitional maintainer-tool shell of the repo. It
contains focused demos, data preparation, provider diagnostics, audits,
decision tooling, and export helpers. It is not a second application.

Representative surfaces include:

- `phase_a_smoke.py`
- `retrieve_demo.py`, `eval_retrieval.py`, `normalize_ftbquests.py`, `ingest_qdrant.py`
- `kag_build_baseline.py`, `kag_sync_neo4j.py`, `kag_query_demo.py`, `kag_query_neo4j.py`
- `openvino_diag.py` and the explicit model export/probe helpers
- `generate_decision_indexes.py` and `validate_decision_records.py`

## Local contract

- The product composition root is `atm10_agent.app.CompanionApp`; scripts may
  expose compatibility or focused maintainer operations but may not become a
  second application.
- Do not add new product semantics here. Move reusable behavior into its owning
  package module and keep any proven-consumer wrapper thin.
- Retire obsolete compatibility entrypoints once package-owned behavior and
  acceptance evidence replace their real consumers.
- Prefer `pathlib`, explicit arguments, and `--runs-dir` driven artifacts over hidden local defaults.
- Keep dry-run or report-only behavior as the default for automation and policy surfaces unless the task explicitly requires stronger behavior.
- Preserve the file-backed baseline and keep external stores additive.
- Keep public examples loopback-safe and token-safe. Use env or config patterns
  such as `NEO4J_PASSWORD`.

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
