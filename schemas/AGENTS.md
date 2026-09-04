# AGENTS.md

Local delta beneath root `AGENTS.md` for `schemas/` in `ATM10-Agent`.
This directory owns antifragility contracts for the companion project.

## Scope

Schemas here describe project-local receipts such as `stressor_receipt_v1.json`
and `adaptation_delta_v1.json`.
They do not define federation-wide proof, role, checkpoint, or self-agent doctrine.

## Local contract

- Treat schema changes are contract changes.
- Keep `$schema`, `$id`, version suffixes, required fields, enums, and example expectations aligned.
- Pair schema changes with matching examples, docs, and tests.
- Preserve dry-run and public-safe assumptions unless the task explicitly requests a reviewed widening.
- Do not encode private logs, real tokens, or workstation-specific paths into examples or defaults.

## Validate

Use targeted contract checks, then broader pytest if needed:

Run the public-surface route in `../VALIDATION.md#public-surface-and-hardening` on demand.
