# AUDIT.md

This file is the repo-local audit contract for `ATM10-Agent`.

Read it after `AGENTS.md` and before making changes.

## Repository role

`ATM10-Agent` is a local-first ATM10 companion for Windows 11 + PowerShell 7.

It owns:

- perception and HUD ingestion paths,
- retrieval and KAG paths,
- gateway and operator-panel surfaces,
- safe automation intent -> plan -> dry-run flows,
- voice and service wrappers,
- public docs, workflow hardening, and tests.

It does **not** own:

- AoA ecosystem-center definitions,
- ToS-authored knowledge meaning,
- infra substrate ownership that belongs in `abyss-stack`.

## Source-of-truth docs

Default reading order for audits:

1. `README.md`
2. `MANIFEST.md`
3. `ROADMAP.md`
4. `docs/RUNBOOK.md`
5. `docs/SOURCE_OF_TRUTH.md`
6. touched scripts, modules, and tests

Also read when relevant:

- `docs/ARCHIVED_TRACKS.md`
- `docs/RELEASE_WAVE6.md`
- `docs/QWEN3_MODEL_STACK.md`

## High-risk surfaces

Treat the following as review-critical:

### Automation safety

- anything that changes `intent -> plan -> dry-run`
- anything that can route a safe action toward real input events
- anything that changes the public automation checklist or donor contract

### Runnable entrypoints

- files under `scripts/`
- gateway launch paths
- operator startup paths
- pilot runtime paths
- smoke runners and benchmark entrypoints

### Dependency and service posture

- `requirements*.txt`
- service URLs, ports, auth expectations, or cross-service assumptions
- new downloads of large models or datasets
- anything that changes the default local runtime profile

### Public hygiene

- placeholders in docs
- workstation-specific paths
- committed artifacts, logs, runs, or private history
- any example that could leak tokens, secrets, or private host detail

## Approval-required changes

Do not make these changes without explicit human confirmation:

- changing `requirements*.txt`
- adding new services, ports, or infrastructure assumptions
- downloading large models or datasets
- enabling real input events that can change game state
- committing files larger than 10 MB
- changing default security posture

## Mandatory verification

### Minimum after code changes

```powershell
cd <repo>
.\.venv\Scripts\Activate.ps1
python -m pytest
```

### Also run when entrypoints or operational flows change

Use the nearest applicable smoke path.

Common public examples already documented in the repository:

```powershell
python scripts/phase_a_smoke.py
python scripts/start_operator_product.py --runs-dir runs
python scripts/automation_intent_chain_smoke.py --intent-json tests/fixtures/intent_open_quest_book.json --runs-dir runs\smoke-intent
python scripts/cross_service_benchmark_suite.py --runs-dir runs\cross-service-suite --smoke-stub-voice-asr
python scripts/run_combo_a_operating_cycle.py --runs-dir runs --policy report_only --summary-json runs\nightly-combo-a-operating-cycle\operating_cycle_summary.json --summary-md runs\nightly-combo-a-operating-cycle\summary.md
```

Do not list a smoke command in the report unless it was actually run.

## Review guidelines

Use these severity rules for Codex GitHub review and local `/review`.

### Treat as P0

- committed secrets, tokens, or private logs
- a change that makes real input events or destructive automation the default path
- a change that silently routes a safe action to game-state-changing input

### Treat as P1

- weakening dry-run-by-default behavior
- widening service exposure, auth posture, or network assumptions without explicit callout
- changes to `requirements*.txt`, services, or ports made without the required ask-first posture
- semantic contract changes in scripts, gateway, retrieval, KAG, voice, or automation flows without matching tests/docs updates
- public docs leaking workstation-specific paths, internal hostnames, or sensitive runtime detail
- claiming validation that was not actually run

Ignore trivial wording nits unless the task explicitly requests copyediting.

## Required report shape

Every audit or patch report for this repo should include:

### PLAN

- task restatement
- files touched or inspected
- main risk: automation, dependency, service, docs, or security

### DIFF

- what changed
- whether meaning changed or only docs/tests/metadata changed

### VERIFY

- `python -m pytest` status
- which smoke commands were run
- what was not run

### REPORT

- current behavior after the change
- whether dry-run/default-local/public-safe posture changed
- any follow-up work still needed

### RESIDUAL RISK

- untested paths
- external service assumptions
- unresolved runtime caveats

## Routing rule

If the requested work mainly changes:

- ecosystem identity or cross-repo ownership, route to `Agents-of-Abyss`;
- infra substrate, deployment, runtime body, storage, or secrets bootstrap, route to `abyss-stack`;
- authored knowledge architecture meaning, route to `Tree-of-Sophia`.
