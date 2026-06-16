# AGENTS.md

Local guidance for `docs/decisions/` in `ATM10-Agent`. Read the root `AGENTS.md` first.

This directory owns durable public decision rationale for the local companion surface.
Use `<repo-root>` as the public placeholder for repository-local commands.

## Scope

`docs/decisions/` records why a route, boundary, validator, operator posture, host-profile rule, or public-surface decision was chosen.

Decision notes explain rationale. They do not own current runtime behavior, public status, roadmap direction, runnable commands, schemas, examples, source modules, workflows, or artifact evidence.

## Local contract

- Use canonical `ATM10-D-####` IDs and full canonical-ID filenames.
- Keep one meaningful decision per note.
- Keep decision notes weaker than the implementation, tests, and canonical public docs they describe.
- Keep safe automation dry-run by default unless the owning implementation, docs, and tests explicitly widen behavior.
- Keep local paths, private logs, hostnames, screenshots, model paths, tokens, and run artifacts out of tracked decision notes.
- Treat generated indexes under `docs/decisions/indexes/` as read models only.
- Keep `modeled_surfaces` in `docs/decisions/indexes/index_contract.yaml` as a top-level list of normalized repo-relative paths under `docs/decisions/`; do not use it for root non-record Markdown.

## Record shape

Every decision record has an `## Index Metadata` block with:

- `Decision ID`
- `Original date` in canonical `YYYY-MM-DD` form
- `Surface classes`
- `Companion layers`
- `Operator surfaces`
- `Guard families`
- `Posture`

Use `Companion layers` for repo layers such as `docs`, `scripts`, `src`, `schemas`, `examples`, `tests`, and `workflows`.
Use `Operator surfaces` for product surfaces such as `gateway`, `streamlit`, `pilot runtime`, `safe automation`, `retrieval`, `KAG`, `voice`, `host profile`, `CI`, or `none`.

## Change rules

- Do not hand-edit generated indexes.
- Do not renumber existing decisions.
- If a decision materially changes, add a new decision note and name what it supersedes.
- If the current public surface changes, update the owning canonical docs and tests in the same change.
- Keep ignored `docs/DECISIONS.md` local-only; public durable decisions belong here.

## Validate

For decision-lane changes, run:

```powershell
cd <repo-root>
python scripts/generate_decision_indexes.py
python scripts/generate_decision_indexes.py --check
python scripts/validate_decision_records.py
python -m pytest tests/test_decision_indexes.py tests/test_nested_agents_docs.py tests/test_validate_nested_agents.py
```
