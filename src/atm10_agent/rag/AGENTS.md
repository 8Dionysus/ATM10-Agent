# AGENTS.md

Local guidance for `src/atm10_agent/rag/` in `ATM10-Agent`.

This is the local delta beneath root `AGENTS.md` for retrieval and
document-contract code.

## Scope

This directory currently centers on:

- `doc_contract.py`
- `ftbquests_ingest.py`
- `retrieval.py`
- `retrieval_profiles.py`

## Local contract

- Treat the document and evaluation schema as a public contract. If field names, required keys, or ranking inputs change, update fixtures, scripts, and tests together.
- Keep ingestion and normalization paths portable and public-safe. Do not bake maintainer-local filesystem assumptions into retrieval code.
- Preserve reproducible baseline behavior for fixture-driven runs.
- Keep retrieval profile intent explicit. If `baseline` or `ov_production` semantics move, reflect that change in tests and the runnable surfaces that depend on them.
- Ranking, filtering, and citation changes should be visible in tests, not hidden inside incidental refactors.

## Change rules

- Prefer small pure transformations around docs and queries.
- Keep JSONL and fixture compatibility in mind before widening schema or metadata requirements.
- Do not require private corpora, external indexes, or workstation-only paths for the default code path.

## Validate

Run the nearest retrieval and document-contract tests:

Run `VALIDATION.md` in this directory on demand, including
`tests/test_rag_doc_contract.py`.
