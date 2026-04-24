# AGENTS.md

Root route card for `ATM10-Agent`.

## Purpose

`ATM10-Agent` is a local-first ATM10 companion for Windows 11 and PowerShell 7.
It combines perception, retrieval, KAG-in-project, safe automation, voice, gateway, operator-panel, public docs, artifacted runs, and regression coverage into one reproducible local companion stack.
It is an operator-facing project surface, not a federation-wide doctrine owner.

## Owner lane

This repository owns:

- perception and HUD ingestion paths
- retrieval and KAG paths inside this project
- gateway, operator-panel, voice, service wrappers, safe automation intent to plan to dry-run flows
- project-local recurrence, operator recovery, public docs, workflow hardening, tests, and explicitly defined stressor/adaptation receipts

It does not own:

- global AoA technique, skill, eval, routing, memo, playbook, KAG, stats, role, progression, or self-agent policy
- sibling repo ownership boundaries or hidden operational lore

## Start here

1. `README.md`
2. `MANIFEST.md`
3. `ROADMAP.md`
4. `docs/RUNBOOK.md`
5. `docs/SOURCE_OF_TRUTH.md`
6. scripts, modules, tests, schemas, docs, or examples you will touch
7. `docs/AGENTS_ROOT_REFERENCE.md` for preserved full root branches


## AGENTS stack law

- Start with this root card, then follow the nearest nested `AGENTS.md` for every touched path.
- Root guidance owns repository identity, owner boundaries, route choice, and the shortest honest verification path.
- Nested guidance owns local contracts, local risk, exact files, and local checks.
- Authored source surfaces own meaning. Generated, exported, compact, derived, runtime, and adapter surfaces summarize, transport, or support meaning.
- Self-agency, recurrence, quest, progression, checkpoint, or growth language must stay bounded, reviewable, evidence-linked, and reversible.
- Report what changed, what was verified, what was not verified, and where the next agent should resume.

## Operator rules

- Preserve reproducibility, Windows 11 plus PowerShell 7 operability, public-doc hygiene, and artifact policy.
- Safe automation stays dry-run by default unless the task explicitly requires otherwise and repo-owned docs support that widening.
- Do not silently route safe actions or quest-facing helpers to real input events.
- Keep secrets, private logs, workstation-specific paths, models, data, and runs out of committed public surfaces.

## Verify

Minimum validation after code changes:

```powershell
cd <repo>
.\.venv\Scripts\Activate.ps1
python -m pytest
```

If a runnable entrypoint changes, run the nearest smoke path or add targeted tests. Examples remain in `docs/AGENTS_ROOT_REFERENCE.md`.

## Report

State which files changed, whether meaning or only docs/tests/metadata changed, whether automation safety or operator recovery posture changed, and what validation ran.

## Full reference

`docs/AGENTS_ROOT_REFERENCE.md` preserves the former detailed root guidance, including ask-first boundaries, smoke examples, review priorities, and documentation-role rules.
