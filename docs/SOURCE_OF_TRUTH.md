# SOURCE_OF_TRUTH.md - atm10-agent

This file defines the roles of the repository documents so the public surface stays small, clear, and non-duplicative.

## Canonical Roles

* `README.md`
  * Short human-facing entrypoint.
  * Link-first and non-operational.
  * Keeps a brief status/highlights layer, but not command blocks, launch matrices, or runbook-scale inventories.

* `MANIFEST.md`
  * Short public repository snapshot (current date, capabilities, links).
  * Primary public current-state document.

* `ROADMAP.md`
  * Public direction, milestones, horizons, and high-level risks.
  * Public replacement for the old tracked `PLANS.md` role.

* `docs/RUNBOOK.md`
  * Active runnable commands and operational paths only.
  * This is where current setup, launch, smoke, and troubleshooting commands live.
  * Archived, historical, rollback, or recoverable-only command references do not belong here.

* `docs/ARCHIVED_TRACKS.md`
  * Canonical home for archived, recoverable, and historical command references.
  * Holds non-default rollback paths, blocked experiments, and restore guidance that should remain public-readable but not appear in the active runbook.

* `docs/QWEN3_MODEL_STACK.md`
  * Machine-specific model/runtime posture and validated host profiles.
  * Records the current `OpenVINO-first` repo-host baseline and additive future runtime-path rules.

* `docs/ECOSYSTEM_CONTEXT.md`
  * Context-only reference about the repository's place in the broader AoA/ToS ecosystem.
  * Does not replace local repo rules, execution policy, or operating guidance.

* `TODO.md` (local-only, ignored)
  * Maintainer execution scratchpad.
  * Not part of the public repository contract.

* `PLANS.md` (local-only, ignored)
  * Maintainer planning and decomposition notes behind the public roadmap.
  * Not part of the public repository contract.

* `docs/DECISIONS.md` (local-only, ignored)
  * Maintainer architecture/policy decision ledger.
  * Public-facing outcomes should be reflected in canonical public docs as needed.

* `docs/SESSION_YYYY-MM-DD.md` and `docs/SESSION_WEEKLY_TEMPLATE.md` (local-only, ignored)
  * Maintainer chronology and templates.
  * Not part of the public repository contract.

* `docs/internal/**`
  * Internal-only chronology, PR/release scratch material, review snapshots, and proposed-doc drafts.
  * Ignored by git for the public repository.
  * Future review scratch or proposed-doc snapshots belong here instead of tracked `docs/reviews/**`.

* `.codex/config.toml` (local-only, ignored)
  * Local tool configuration only.
  * Not part of the public repository contract.

## Precedence

* For the public repo surface, priority belongs to:
  * `MANIFEST.md`
  * `ROADMAP.md`
  * `docs/RUNBOOK.md`
  * `docs/ARCHIVED_TRACKS.md`
  * `docs/QWEN3_MODEL_STACK.md`
  * `docs/SOURCE_OF_TRUTH.md`
* `docs/ECOSYSTEM_CONTEXT.md` is reference-only.
* Local-only planning, chronology, tool config, and scratch docs never define the public repo surface.

## Update Rules

* If behavior/architecture changed -> update any impacted canonical public docs, and local `docs/DECISIONS.md` when needed.
* If active commands/setup changed -> update `docs/RUNBOOK.md`.
* If an archived or recoverable command/reference changed -> update `docs/ARCHIVED_TRACKS.md`.
* If the machine/runtime baseline or host-profile policy changed -> update `docs/QWEN3_MODEL_STACK.md`.
* If there is an important public status/result -> update `MANIFEST.md`, and `ROADMAP.md` if direction changed.
* If there is local execution planning -> update local `TODO.md` / `PLANS.md`.
* If there is internal chronology, proposed-doc scratch, or review packaging -> use ignored local-only surfaces under `docs/internal/**`.
* Keep `README.md` pointed at canonical docs instead of duplicating operational detail.

## What Not To Store Everywhere

* Do not duplicate long command blocks across `README.md`, `MANIFEST.md`, and `docs/RUNBOOK.md`.
* Do not mix active runbook content with archived or historical command references.
* Do not keep tracked review snapshots, proposed-doc scratch copies, or tool-local config in the public tree.
* Do not duplicate counters like `N passed` or long run-id lists across multiple public docs.
