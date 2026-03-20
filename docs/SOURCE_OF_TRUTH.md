# SOURCE_OF_TRUTH.md — atm10-agent

This file defines the roles of the project's documents to remove duplication and drift.

## Canonical Roles

* `README.md`
  * Short human-facing entrypoint.
  * High-level status + links to canonical documents only.
  * Does not store long lists of run IDs or historical metrics.

* `MANIFEST.md`
  * Short machine/human repository snapshot (current date, capabilities, links).
  * No detailed chronology; details live in `docs/SESSION_*.md`.

* `TODO.md`
  * Step-by-step execution plan.
  * Format: `Now`, `Next`, `Blocked`, `Done this week`.
  * Constraint: WIP limit = 3.

* `PLANS.md`
  * Goals, milestones, DoD, constraints, and risks.
  * No long chronology of run artifacts.

* `docs/SESSION_YYYY-MM-DD.md`
  * Detailed chronology of changes, runs, metrics, and artifacts.
  * This is the place for the "long history".
  * Weekly summary uses template `docs/SESSION_WEEKLY_TEMPLATE.md`.

* `docs/DECISIONS.md`
  * Architecture decisions and policy changes.
  * Format: 1-3 bullets per meaningful decision.

* `docs/RUNBOOK.md`
  * Runnable commands, operational profiles, quickstart for launches.

* `docs/ARCHIVED_TRACKS.md`
  * Archived/recoverable directions and re-open criteria.

* `docs/ECOSYSTEM_CONTEXT.md`
  * Context-only reference about the repository's place in the broader AoA/ToS ecosystem.
  * Used for high-level compatibility direction.
  * Does not replace or override local repo rules, the execution plan, or operating policy.

## Precedence

* In case of conflict, priority always belongs to repo-local docs:
  * `TODO.md`
  * `docs/DECISIONS.md`
  * `docs/RUNBOOK.md`
  * `docs/SESSION_*.md`
* `docs/ECOSYSTEM_CONTEXT.md` is used only as a reference/context layer.

## Update Rules

* If behavior/architecture changed -> update `docs/DECISIONS.md`.
* If commands/setup changed -> update `docs/RUNBOOK.md`.
* If there is an important run/result -> add it to `docs/SESSION_*.md`.
* Update active steps only in `TODO.md`.
* Update goals/DoD only in `PLANS.md`.

## What Not To Store Everywhere

* Do not duplicate counters like `N passed` across all files at once.
  Preferred truth:
  * Truth for current state is CI + the latest `docs/SESSION_*.md`.
* Do not keep long run ID lists in `TODO.md`.
