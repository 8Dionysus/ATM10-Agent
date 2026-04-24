# AGENTS.md

Local guidance for `schemas/` in `ATM10-Agent`. Read the root `AGENTS.md` first.
This directory owns operator and antifragility contracts for the companion project.

## Scope

Schemas here describe project-local receipts and operator surfaces such as `stressor_receipt_v1.json`, `adaptation_delta_v1.json`, `gateway_operator_return_event.schema.json`, and return-summary catalogs.
They do not define federation-wide proof, role, checkpoint, or self-agent doctrine.

## Local contract

- Treat schema changes are contract changes.
- Keep `$schema`, `$id`, version suffixes, required fields, enums, and example expectations aligned.
- Pair schema changes with matching examples, docs, and tests.
- Preserve dry-run and public-safe assumptions unless the task explicitly requests a reviewed widening.
- Do not encode private logs, real tokens, or workstation-specific paths into examples or defaults.

## Validate

Use targeted contract checks, then broader pytest if needed:

```powershell
python -m pytest tests/test_antifragility_public_surface.py tests/test_operator_product_safe_actions.py tests/test_operator_return_recovery.py
python -m pytest
```
