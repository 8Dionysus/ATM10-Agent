# AGENTS.md

Guidance for coding agents and humans contributing to `ATM10-Agent`.

## Purpose

`ATM10-Agent` is a local-first ATM10 companion built around reproducible
scripts, public-safe docs, artifacted runs, and regression coverage on Windows
11 + PowerShell 7.

It combines perception, retrieval, KAG, safe automation, voice, and
gateway-backed operator surfaces into one reproducible local companion stack.

This repository is an operator-facing project surface.
It may express recovery, recurrence, and bounded automation inside this local
stack, but it does not own federation-wide role doctrine, self-agent policy, or
sibling repo boundaries.

## Owns

This repository is the source of truth for:

- perception and HUD ingestion paths
- retrieval and KAG paths inside this project
- gateway and operator-panel surfaces
- safe automation intent -> plan -> dry-run flows
- voice and service wrappers
- project-local recurrence and operator recovery surfaces
- public project docs, workflow hardening, and tests
- project-local stressor and adaptation receipt contracts when explicitly defined here

## Does not own

Do not treat this repository as the source of truth for:

- global AoA technique, skill, eval, routing, memo, or playbook doctrine
- sibling repo ownership boundaries
- federation-wide role, progression, or self-agent checkpoint policy
- hidden infrastructure or secret-bearing operational lore

This repo consumes neighboring AoA surfaces.
It does not replace them.

## Read first

Before changing anything, read in this order:

1. `README.md`
2. `MANIFEST.md`
3. `ROADMAP.md`
4. `docs/RUNBOOK.md`
5. `docs/SOURCE_OF_TRUTH.md`
6. the scripts, modules, and tests you will touch

Then branch by task:

- operator commands, recurrence, or recovery:
  `docs/RUNBOOK.md` and
  `docs/RECURRENCE_OPERATOR_RECOVERY.md`
- public status, milestones, release cadence, or supported profiles:
  `MANIFEST.md`,
  `ROADMAP.md`, and
  `docs/PRODUCT_EDGE_POSTURE.md`
- source-of-truth and ecosystem placement:
  `docs/SOURCE_OF_TRUTH.md` and
  `docs/ECOSYSTEM_CONTEXT.md`
- validated host/model baseline or UI pilot surfaces:
  `docs/QWEN3_MODEL_STACK.md` and
  `docs/STREAMLIT_IA_V0.md`
- first-wave antifragility receipt surfaces:
  `docs/ANTIFRAGILITY_FIRST_WAVE.md`,
  `schemas/stressor_receipt_v1.json`, and
  `schemas/adaptation_delta_v1.json`

If the task touches archived or security-sensitive areas, also check:

- `docs/ARCHIVED_TRACKS.md`
- `docs/RELEASE_WAVE6.md`
- `docs/QWEN3_MODEL_STACK.md`

If a deeper directory defines its own `AGENTS.md`, follow the nearest one.

## Audit contract

For repository audits and GitHub review, read `AUDIT.md` after the core docs.

## Core rules

Prefer the smallest reviewable change that preserves reproducibility, safety
posture, Windows 11 + PowerShell 7 operability, and public-doc hygiene.

Safe automation stays dry-run by default unless the task explicitly requires
otherwise and the repo-owned docs support that widening.

Do not let convenience features silently widen operator authority, input
automation, or quest-like helper behavior.

## Contribution doctrine

Use this flow: `PLAN -> DIFF -> VERIFY -> REPORT`

### PLAN

Before editing:

- restate the task as a short executable plan
- name the files you expect to touch
- call out risks separately: Windows paths, dependency weight, service or auth changes, schema drift, artifact policy, automation safety posture, or operator recovery behavior

### DIFF

While editing:

- keep diffs focused and reviewable
- prefer `pathlib` and config or env driven paths over hardcoded paths
- preserve Windows 11 + PowerShell 7 operability
- keep automation dry-run by default unless the task explicitly requires otherwise
- keep public docs sanitized with placeholders such as `<repo-root>` and `<path-to-...>`
- use env or config patterns like `ATM10_SERVICE_TOKEN` instead of literal secrets in examples
- keep operator-facing helper surfaces bounded and explicit about whether they simulate, preview, or actually act

### VERIFY

Minimum validation after code changes:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pytest
```

If you touch a runnable entrypoint, also run the nearest smoke path or add
targeted tests.
Examples include:

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
- silently route `Safe Actions` or quest-facing helpers to real input events

## Review guidelines

For GitHub review in this repository, treat the following as P0:

- committed secrets, tokens, or private logs
- a change that makes real input events or destructive automation the default path
- a change that silently routes a safe action or quest-facing helper to game-state-changing input

Treat the following as P1:

- weakening dry-run-by-default behavior
- widening service exposure, auth posture, or network assumptions without explicit callout
- changes to `requirements*.txt`, services, or ports made without the required ask-first posture
- semantic contract changes in scripts, gateway, retrieval, KAG, voice, or automation flows without matching tests/docs updates
- public docs leaking workstation-specific paths, internal hostnames, or sensitive runtime detail
- claiming validation that was not actually run

Ignore trivial wording nits unless the task explicitly asks for copyediting.

## Documentation rule

Follow `docs/SOURCE_OF_TRUTH.md`.

In practice:

- keep `README.md` as the short human entrypoint
- keep current public status in `MANIFEST.md`
- keep direction and milestone posture in `ROADMAP.md`
- keep runnable commands and setup changes in `docs/RUNBOOK.md`
- keep release cadence and supported profiles in `docs/PRODUCT_EDGE_POSTURE.md`
- reflect doc-role or boundary changes in `docs/SOURCE_OF_TRUTH.md`
