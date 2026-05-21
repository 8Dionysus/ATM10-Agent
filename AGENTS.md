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

## Memory route

For recall, continuity, compaction recovery, comparison with past work, or
preserved lessons, start with `aoa_memo` and the workspace memory map. Session
grounding routes through `.aoa`; local candidate writing routes through this
project's `memo/` port when that port exists; durable reviewed memory lands
through `aoa-memo`.

## Operator rules

- Preserve reproducibility, Windows 11 plus PowerShell 7 operability, public-doc hygiene, and artifact policy.
- Safe automation stays dry-run by default unless the task explicitly requires otherwise and repo-owned docs support that widening.
- Do not silently route safe actions or quest-facing helpers to real input events.
- Keep secrets, private logs, workstation-specific paths, models, data, and runs out of committed public surfaces.

## GitHub landing workflow

Root `AGENTS.md` owns the repository-wide branch, PR, CI, and merge route.
`.github/AGENTS.md` owns the GitHub-native files that support it.

When the user asks to commit, push, and merge in this repository, use this route:

1. Start from a branch based on the current `origin/main`. If the worktree is already dirty, inventory it first and carry forward only the intended diff.
2. Commit the intended change with a message that names the changed surface.
3. Push the branch and open a pull request that states changed surfaces, validation run, skipped checks, and remaining risk.
4. Wait for GitHub `Repo Validation` and any required GitHub checks. If a check fails, fix the branch and wait for the new result.
5. Merge through GitHub after green validation. Use squash unless repository settings report a different required method; report the method that landed.
6. Return to `main`, fast-forward from `origin/main`, and confirm the worktree is clean before closeout.

If GitHub status or merge permissions cannot be observed, stop the landing route and report the exact blocker instead of guessing.

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
