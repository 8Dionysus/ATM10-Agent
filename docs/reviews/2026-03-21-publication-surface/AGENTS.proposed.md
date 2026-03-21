# AGENTS.md

Guidance for coding agents and humans contributing to `atm10-agent`.

## Purpose

`atm10-agent` is a local-first ATM10 companion built around reproducible scripts, public-safe docs, artifacted runs, and regression coverage on Windows 11 + PowerShell 7.

This repository owns:

- perception and HUD ingestion paths
- retrieval and KAG paths
- gateway and operator-panel surfaces
- safe automation intent -> plan -> dry-run flows
- voice and service wrappers
- public docs, workflow hardening, and tests

## Read first

Before changing anything, read in this order:

1. `README.md`
2. `MANIFEST.md`
3. `ROADMAP.md`
4. `docs/RUNBOOK.md`
5. `docs/SOURCE_OF_TRUTH.md`
6. the scripts, modules, and tests you will touch

If the task touches archived or security-sensitive areas, also check:

- `docs/ARCHIVED_TRACKS.md`
- `docs/RELEASE_WAVE6.md`
- `docs/QWEN3_MODEL_STACK.md`

## Core rule

Prefer the smallest reviewable change that preserves reproducibility, safety posture, and public-doc hygiene.

## Operating doctrine

Use this flow:

`PLAN -> DIFF -> VERIFY -> REPORT`

### PLAN

Before editing:

- restate the task as a short executable plan
- name the files you expect to touch
- call out risks separately: Windows paths, dependency weight, service or auth changes, schema drift, artifact policy

### DIFF

While editing:

- keep diffs focused and reviewable
- prefer `pathlib` and config or env driven paths over hardcoded paths
- preserve Windows 11 + PowerShell 7 operability
- keep automation dry-run by default unless the task explicitly requires otherwise
- keep public docs sanitized with placeholders such as `<repo-root>` and `<path-to-...>`
- use env or config patterns like `ATM10_SERVICE_TOKEN` instead of literal secrets in examples

### VERIFY

Minimum validation after code changes:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pytest
```

If you touch a runnable entrypoint, also run the nearest smoke path or add targeted tests.

Examples:

```powershell
python scripts/phase_a_smoke.py
python scripts/start_operator_product.py --runs-dir runs
python scripts/automation_intent_chain_smoke.py --intent-json tests/fixtures/intent_open_quest_book.json --runs-dir runs\smoke-intent
```

### REPORT

When reporting back, include:

- what changed
- which files changed
- whether meaning changed or only docs, tests, or metadata changed
- what validation you actually ran
- any remaining limits, follow-ups, or risks

Do not claim validation you did not execute.

## Boundaries

### Allowed

Safe, normal contributions include:

- improving scripts, source modules, tests, fixtures, and public docs
- tightening gateway, voice, retrieval, KAG, or operator-panel contracts
- expanding smoke coverage or artifact validation
- improving public documentation clarity without leaking maintainer-local detail
- adding a new automation `intent_type` only when it follows checklist `M6.19`

### Ask first

Request explicit confirmation before:

- changing `requirements*.txt`
- adding new services, ports, or infrastructure assumptions
- downloading large models or datasets
- enabling real input events that can change game state
- committing files larger than 10 MB
- changing security posture in a way that affects default local behavior

### Never

Do not:

- commit `models/**`, `data/**`, `runs/**`, `.codex/**/logs/**`, secrets, or private logs
- paste workstation-specific paths into public docs
- hardcode reusable credentials or tokens
- disable tests to make a change pass
- hide semantic contract changes behind “docs-only” wording
- run destructive commands or change host or system settings as part of normal repo work
- silently route `Safe Actions` to real input events

## Documentation rules

Follow `docs/SOURCE_OF_TRUTH.md`.

In practice:

- keep `README.md` as a short human entrypoint
- put current public status in `MANIFEST.md`
- put direction and milestone posture in `ROADMAP.md`
- put runnable commands and setup changes in `docs/RUNBOOK.md`
- reflect doc-role or boundary changes in `docs/SOURCE_OF_TRUTH.md`

## Automation rule

Every new automation `intent_type` should follow the existing public intent -> plan -> dry-run contract and checklist `M6.19`.

Current public donor records already exist for:

- `open_quest_book`
- `check_inventory_tool`
- `open_world_map`

## Public hygiene

Assume everything committed here is public and reusable by strangers.

Write for portability:

- use `<repo-root>` and `<path-to-...>` placeholders in docs
- use generic loopback URLs in examples
- prefer public-safe summaries over local run-history dumps
- keep secrets and sensitive runtime details out of committed artifacts
