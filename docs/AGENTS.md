# AGENTS.md

Local delta beneath root `AGENTS.md` for `docs/` in `ATM10-Agent`.
This directory owns operator-facing public docs for the local companion surface.

## Scope

Docs here explain current capabilities, runbooks, recurrence and recovery, source-of-truth boundaries, durable decision rationale, release posture, and operator safety.
They must stay aligned with `MANIFEST.md`, `ROADMAP.md`, `docs/RUNBOOK.md`, and `docs/SOURCE_OF_TRUTH.md`.

## Local contract

- Keep safe automation dry-run by default in docs unless the repo-owned implementation and tests explicitly support a wider behavior.
- Do not publish private workstation paths, private logs, hostnames, tokens, screenshots with sensitive details, or local model paths as if they were portable facts.
- Keep runnable commands honest for Windows 11 + PowerShell 7, and call out Linux/Fedora variants separately.
- If docs widen operator authority, service exposure, auth posture, or recovery behavior, update tests and report the risk.
- Keep `README.md` short, `MANIFEST.md` current, `ROADMAP.md` directional, and `docs/RUNBOOK.md` executable.

## Validate

For public docs and runbook changes, use the nearest hardening checks:

Run `VALIDATION.md` in this directory on demand, including
`tests/test_public_repo_hardening.py`.

For decision-rationale changes, also run:

Run the decision route in `decisions/VALIDATION.md` on demand.
