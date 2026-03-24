# AGENTS.md

Local guidance for `src/rag/` in `ATM10-Agent`.

Read the root `AGENTS.md` first. This file only adds local rules for retrieval and document-contract code.

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

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_rag_doc_contract.py tests/test_ftbquests_ingest.py tests/test_retrieval_profiles.py tests/test_retrieval_demo.py tests/test_retrieve_demo_script.py tests/test_eval_retrieval.py
```
