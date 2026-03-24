# AGENTS.md

Local guidance for `tests/` in `ATM10-Agent`.

Read the root `AGENTS.md` first. This file only adds local rules for regression and public-surface checks.

## Scope

`pytest.ini` points test discovery at `tests/`, so this directory is the validation gate for scripts, source modules, workflows, docs, and fixtures.

## Local contract

- Every meaningful behavior change should land with the nearest targeted test.
- Keep tests deterministic, fixture-first, and public-safe. Prefer loopback URLs, temp directories, and stub providers over live dependencies.
- Do not rely on workstation-specific paths, private logs, local models, or network access for default test coverage.
- Keep `tests/fixtures/` small, sanitized, and reusable. Treat fixture format changes as contract changes.
- When public docs or workflow surfaces change, update the matching hardening tests instead of relying on manual review.

## Change rules

- Mirror the production surface closely enough to catch semantic drift, but keep tests cheap to run in CI.
- Prefer precise contract tests over broad snapshot dumps.
- Add or extend tests for new scripts, new source modules, new artifact schemas, and new nested `AGENTS.md` guidance files.

## Validate

The default gate is:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pytest
```

For doc and public-surface changes, also run the nearest hardening subset:

```powershell
python -m pytest tests/test_public_repo_hardening.py tests/test_workflow_public_surface.py tests/test_nested_agents_docs.py
```
