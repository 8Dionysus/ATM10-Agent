# AGENTS.md

Local guidance for `examples/` in `ATM10-Agent`. Read the root `AGENTS.md` first.
This directory carries sanitized contract examples for operator and antifragility surfaces.

## Scope

Examples here show minimal, public-safe shapes for stressor receipts, adaptation deltas, gateway operator return events, return summaries, and reason catalogs.
They should help validation and docs stay grounded without leaking maintainer-local runtime detail.

## Local contract

- Keep examples sanitized contract examples, not private run artifacts.
- Make examples match the schemas exactly enough for tests to catch drift.
- Use placeholders, loopback-safe values, and fake IDs. Include no secrets, private logs, internal hostnames, real account names, or machine-local paths.
- When an example changes because behavior changed, update the schema, docs, and tests in the same patch.
- Do not use examples to imply that real input automation or destructive behavior is now the default.

## Validate

Common gates:

```powershell
python -m pytest tests/test_antifragility_public_surface.py
python -m pytest
```
