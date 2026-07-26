# SOURCE_OF_TRUTH.md - atm10-agent

This file defines the roles of the repository documents so the public surface stays small, clear, and non-duplicative.

## Canonical Roles

* `pyproject.toml`
  * Canonical installable-project metadata, package discovery, supported Python
    floor, CLI entry point, and optional dependency groups.
  * Sole dependency authority; the repository does not maintain parallel
    requirements-file dependency graphs.

* `pylock.toml`
  * Resolved lock evidence for the dependency-free core install.
  * Optional provider environments are platform-specific and remain bounded by
    the named `pyproject.toml` extras rather than pretending to be one portable
    universal lock.

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

* `docs/autonomy/README.md`
  * Canonical autonomous-product boundary, dependency law, protected-behavior
    route, migration gates, and standalone claim limit.
  * Its JSON ledgers are executable transition inputs; they do not prove a gate
    until the referenced tests and acceptance commands pass.

* `docs/intake/README.md`
  * Canonical one-way donor authority map, review sequence, stop line, and
    claim limit.
  * `docs/intake/donor-ledger.json` owns immutable revisions, selected paths,
    license review, transformations, target surfaces, rejected surfaces, and
    admission/adaptation status.
  * Admission proves neither implementation nor product benefit.

* `docs/PRODUCT_EDGE_POSTURE.md`
  * Public release cadence, supported and preliminary profile claims, CI/test tiers, and the explicit `ATM10-Agent` x `abyss-stack` contract.
  * Short public boundary for product-edge support claims.

* `docs/WINDOWS_PRODUCT_EDGE_BOUNDARY.md`
  * Defines the live Windows claim limit and routes the package-owned
    `windows_live_acceptance_v2` collector and the bounded offline
    `windows_live_acceptance_verification_v1` consistency verifier.
  * Source code, schema, or a blocked example does not replace a passing
    receipt from a current physical ATM10 session.

* `docs/RUNBOOK.md`
  * Active runnable commands and operational paths only.
  * This is where current setup, launch, smoke, and troubleshooting commands live.
  * Archived, historical, rollback, or recoverable-only command references do not belong here.

* `docs/ARCHIVED_TRACKS.md`
  * Canonical home for archived, recoverable, and historical command references.
  * Holds non-default rollback paths, blocked experiments, and restore guidance that should remain public-readable but not appear in the active runbook.

* `docs/QWEN3_MODEL_STACK.md`
  * Provider research posture and archived model-path evidence.
  * Does not define a required host profile or the product's dependency graph.

* `docs/RELEASE_WAVE6.md`
  * Scoped public engineering reference for one hardening/release wave.
  * Not the repo-wide cadence or support-matrix surface.

* `docs/ECOSYSTEM_CONTEXT.md`
  * Context-only reference about the repository's place in the broader AoA/ToS ecosystem.
  * Does not replace local repo rules, execution policy, or operating guidance.

* `docs/ANTIFRAGILITY_FIRST_WAVE.md`
  * Context-only owner-local contract for bounded degraded hybrid-query evidence.
  * Defines the first-wave `stressor_receipt_v1` / `adaptation_delta_v1` posture and links to the repo-local schemas/examples.
  * Does not replace `docs/RUNBOOK.md` as the active operational surface.

* `docs/decisions/`
  * Tracked public decision-rationale lane for durable route, boundary, validator, operator posture, host-profile, product-edge, and public-surface decisions.
  * Uses canonical `ATM10-D-####` records and generated lookup indexes.
  * Explains why decisions were made; it does not replace current public status, roadmap direction, runnable commands, implementation, tests, schemas, workflows, or artifact evidence.

* `TODO.md` (local-only, ignored)
  * Maintainer execution scratchpad.
  * Not part of the public repository contract.

* `PLANS.md` (local-only, ignored)
  * Maintainer planning and decomposition notes behind the public roadmap.
  * Not part of the public repository contract.

* `docs/DECISIONS.md` (local-only, ignored)
  * Maintainer architecture/policy decision ledger.
  * Public-facing durable decisions should land in `docs/decisions/`; outcomes should still be reflected in canonical public docs as needed.

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
  * `docs/autonomy/README.md`
  * `docs/intake/README.md`
  * `docs/PRODUCT_EDGE_POSTURE.md`
  * `docs/RUNBOOK.md`
  * `docs/ARCHIVED_TRACKS.md`
  * `docs/QWEN3_MODEL_STACK.md`
  * `docs/SOURCE_OF_TRUTH.md`
  * `docs/decisions/README.md`
* `docs/RELEASE_WAVE6.md` is wave-scoped reference, not the repo-wide cadence surface.
* `docs/ECOSYSTEM_CONTEXT.md` is reference-only.
* `docs/ANTIFRAGILITY_FIRST_WAVE.md` is contract/reference-only.
* Local-only planning, chronology, tool config, and scratch docs never define the public repo surface.

## Update Rules

* If behavior/architecture changed -> update any impacted canonical public docs, and local `docs/DECISIONS.md` when needed.
* If the autonomy boundary, dependency disposition, protected behavior, or
  migration gate changed -> update `docs/autonomy/`, its contract tests, and
  any affected canonical public docs.
* If donor authority, revision, selected paths, license, transformation,
  target, rejection, or admission status changed -> update `docs/intake/`,
  its schema, and its contract tests.
* If a public durable decision needs rationale -> add a canonical `docs/decisions/ATM10-D-####-*.md` record and regenerate decision indexes.
* If active commands/setup changed -> update `docs/RUNBOOK.md`.
* If archived or recoverable command/reference changed -> update `docs/ARCHIVED_TRACKS.md`.
* If the machine/runtime baseline or host-profile policy changed -> update `docs/QWEN3_MODEL_STACK.md`.
* If public release cadence, supported/preliminary profile claims, CI/test tiers, or the `ATM10-Agent` x `abyss-stack` boundary changed -> update `docs/PRODUCT_EDGE_POSTURE.md`.
* If there is an important public status/result -> update `MANIFEST.md`, and `ROADMAP.md` if direction changed.
* If a wave-scoped public hardening or release reference changed -> update the matching `docs/RELEASE_*.md` document.
* If first-wave owner-local stressor or adaptation contract wording changes -> update `docs/ANTIFRAGILITY_FIRST_WAVE.md` and the linked `schemas/` + `examples/` surfaces.
* If there is local execution planning -> update local `TODO.md` / `PLANS.md`.
* If there is internal chronology, proposed-doc scratch, or review packaging -> use ignored local-only surfaces under `docs/internal/**`.
* Keep `README.md` pointed at canonical docs instead of duplicating operational detail.

## What Not To Store Everywhere

* Do not duplicate long command blocks across `README.md`, `MANIFEST.md`, and `docs/RUNBOOK.md`.
* Do not mix active runbook content with archived or historical command references.
* Do not keep tracked review snapshots, proposed-doc scratch copies, or tool-local config in the public tree.
* Do not duplicate counters like `N passed` or long run-id lists across multiple public docs.
* Do not spread release cadence, support-tier, or supported/preliminary profile claims across several public docs when `docs/PRODUCT_EDGE_POSTURE.md` already carries that contract.
