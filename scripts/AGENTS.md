# AGENTS.md

Local guidance for `scripts/` in `ATM10-Agent`.

This is the local delta beneath root `AGENTS.md` for the transitional
maintainer-tool shell.

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

## Validation

Use this directory's [`VALIDATION.md`](VALIDATION.md) for the nearest smoke or
contract route. Use the repository root validation map for the full suite and
decision-index lane.
