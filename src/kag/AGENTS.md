# AGENTS.md

Local guidance for `src/kag/` in `ATM10-Agent`.

Read the root `AGENTS.md` first. This file only adds local rules for KAG and graph backends.

## Scope

This directory currently owns:

- `baseline.py`
- `neo4j_backend.py`

## Local contract

- Keep the file baseline as the easiest local default. Neo4j remains additive, not mandatory for the baseline path.
- Preserve explicit provenance and citation behavior. If graph output fields change, update scripts, fixtures, evals, and tests together.
- Neo4j configuration must stay env or config driven. Use `NEO4J_PASSWORD` and loopback examples, not literal credentials.
- On graph degradation, fail clearly and surface the reason. Do not hide backend failure behind silent empty results unless the calling contract explicitly requires fallback behavior.

## Change rules

- Keep backend boundaries clean: baseline file logic in `baseline.py`, database integration in `neo4j_backend.py`.
- Avoid import-time attempts to connect to Neo4j.
- Treat query shape, ranking, and citation semantics as contract changes that need test updates.

## Validate

Run the nearest KAG and Neo4j coverage:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_kag_neo4j_backend.py tests/test_kag_build_baseline.py tests/test_kag_query_demo.py tests/test_kag_query_neo4j.py tests/test_kag_sync_neo4j.py tests/test_eval_kag_file.py tests/test_eval_kag_neo4j.py
```
