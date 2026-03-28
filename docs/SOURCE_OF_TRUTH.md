# SOURCE_OF_TRUTH.md — atm10-agent

This file defines the roles of the project's documents to remove duplication and drift.

## Canonical Roles

* `README.md`
  * Short human-facing entrypoint.
  * High-level status + links to canonical documents only.
  * Does not store long lists of run IDs or historical metrics.

* `MANIFEST.md`
  * Short public repository snapshot (current date, capabilities, links).
  * This is the primary public current-state document.

* `ROADMAP.md`
  * Public direction, milestones, horizons, and high-level risks.
  * This is the public replacement for the old tracked `PLANS.md` role.

* `TODO.md` (local-only, ignored)
  * Maintainer execution scratchpad.
  * Format can stay `Now`, `Next`, `Blocked`, `Done this week`.
  * Not part of the public repository contract.

* `PLANS.md` (local-only, ignored)
  * Maintainer planning/decomposition notes behind the public roadmap.
  * Not part of the public repository contract.

* `docs/DECISIONS.md` (local-only, ignored)
  * Maintainer architecture/policy decision ledger.
  * Public-facing outcomes should be reflected in `MANIFEST.md`, `ROADMAP.md`, `docs/RUNBOOK.md`, and/or this file as needed.
  * Not part of the public repository contract.

* `docs/SESSION_YYYY-MM-DD.md` (local-only, ignored)
  * Maintainer session chronology and handoff notes.
  * Existing local copies may remain for continuity, but they are not part of the public repository contract.
  * New internal chronology should prefer `docs/internal/**`.

* `docs/SESSION_WEEKLY_TEMPLATE.md` (local-only, ignored)
  * Template for local weekly/session notes.

* `docs/internal/**`
  * Internal-only detailed chronology, PR/release scratch docs, and ad-hoc operational tails.
  * Ignored by git for the public repository.
  * Future session chronology belongs here by default.

* `docs/RUNBOOK.md`
  * Runnable commands, operational profiles, quickstart for launches.

* `docs/QWEN3_MODEL_STACK.md`
  * Machine-specific model/runtime posture and validated host profiles.
  * Records the current `OpenVINO-first` repo-host baseline and additive future runtime-path rules.

* `docs/ARCHIVED_TRACKS.md`
  * Archived/recoverable directions and re-open criteria.

* `docs/ECOSYSTEM_CONTEXT.md`
  * Context-only reference about the repository's place in the broader AoA/ToS ecosystem.
  * Used for high-level compatibility direction.
  * Does not replace or override local repo rules, the execution plan, or operating policy.

## Precedence

* For the public repo surface, priority belongs to:
  * `MANIFEST.md`
  * `ROADMAP.md`
  * `docs/RUNBOOK.md`
  * `docs/QWEN3_MODEL_STACK.md`
  * `docs/SOURCE_OF_TRUTH.md`
* `docs/ECOSYSTEM_CONTEXT.md` is used only as a reference/context layer.
* Local-only `TODO.md` / `PLANS.md` / `docs/DECISIONS.md` may guide maintainer workflow, but they do not replace public source-of-truth docs.
* Local-only session docs, templates, and PR/release scratch docs do not define the public repo surface.

## Update Rules

* If behavior/architecture changed -> update local `docs/DECISIONS.md` and any impacted public docs.
* If commands/setup changed -> update `docs/RUNBOOK.md`.
* If the machine/runtime baseline or host-profile policy changed -> update `docs/QWEN3_MODEL_STACK.md` and any impacted public docs.
* If there is an important public status/result -> update `MANIFEST.md` and, if policy/direction changed, `ROADMAP.md`, `docs/RUNBOOK.md`, and/or `docs/SOURCE_OF_TRUTH.md`.
* If there is local execution planning -> update local `TODO.md` / `PLANS.md`.
* If there is detailed internal chronology or PR/release scratch material -> use ignored local-only surfaces (`docs/internal/**` by default; existing local `docs/SESSION_*.md` copies are allowed for continuity).
* Keep `README.md` pointed only at public canonical docs.

## What Not To Store Everywhere

* Do not duplicate counters like `N passed` across all files at once.
  Preferred truth:
  * Truth for current public state is CI + `MANIFEST.md` + `ROADMAP.md` + `docs/RUNBOOK.md` / `docs/SOURCE_OF_TRUTH.md` where relevant.
  * Detailed internal chronology belongs only in local ignored docs.
* Do not keep long run ID lists in `TODO.md`.
