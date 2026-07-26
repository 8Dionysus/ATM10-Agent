# Autonomous Modular Monolith

## Index Metadata

- Decision ID: ATM10-D-0003
- Original date: 2026-07-25
- Surface classes: architecture, owner boundary, dependency law, runtime topology
- Companion layers: root, core, adapters, tests, docs, workflows
- Operator surfaces: CLI, Windows product edge, optional UI
- Guard families: autonomy, dry-run safety, degraded honesty, provenance
- Posture: accepted

## Context

The repository proved many useful behaviors, but its active shape inverted the
product boundary. Eighty-two scripts, seven workflows, gateway SLA promotion
machinery, a repo-self KAG family, external stats/eval routes, and OS-profile
guidance surrounded 34 source files. The current green baseline contains 40
scripts that inject the repository root and 23 scripts that import
`scripts.*`; it has nine requirements files and no installable-project
metadata.

The companion loop still exists inside that shell: perception, interpretation,
retrieval and product KAG, a grounded response or plan, optional safe action
and voice, and artifacted evidence. That loop, not a service topology or
federated tool plane, is the durable product.

## Decision

Rebuild `ATM10-Agent` as one autonomous modular monolith around:

`Perception -> Interpretation -> World/Memory -> Response/Plan -> optional Action/Voice -> Trace`.

A fresh clone must be able to install the core, build, run deterministic
stub/replay acceptance, execute tests, and produce release artifacts without
AoA sibling repositories, `.aoa`, an OS skill profile, shared validators,
shared runtimes, or hidden OS configuration. Repository self-KAG, central
stats/eval ports, and gateway-governance machinery have no protected
architectural status. Useful semantics are retained only through
source-owned contracts and tests.

Windows capture, OpenVINO, remote models, Qdrant, Neo4j, FastAPI, Streamlit,
voice, and future providers remain explicit optional adapters. Mutable world
state and append-only traces remain separate. Safe automation stays dry-run by
default. Missing optional providers must yield honest degraded behavior.

Donor repositories may be read only after the standalone autonomy gate is
green. Intake is one-way, pinned to immutable revisions, path-bounded,
license-reviewed, transformed into ATM10-owned code or data, and recorded in a
local receipt. No donor checkout, action, validator, runtime, or config may
remain required.

This decision narrows `ATM10-D-0002`: removing copied skill projections remains
valid, but an OS user profile is no longer a dependency or continuity route
for this repository. Maintainers may use external tools; the product and its
source contract cannot require them.

## Options Considered

- Continue hardening the gateway, nightly promotion, and federated read-model
  shell as the production architecture.
- Split the companion into independently deployed services and shared AoA
  organs.
- Recenter one installable package and composition root, with optional adapters
  and one-way donor intake after standalone proof.

## Rationale

The third option preserves the useful loop while reducing authority surfaces,
process count, dependency ambiguity, and failure modes. A modular monolith
keeps provider replacement and domain boundaries explicit without forcing
local companion behavior through services or sibling repositories. The
standalone gate also prevents donor archaeology from quietly recreating the
dependency web being removed.

## Consequences

- `atm10_agent` becomes the only importable product package and owns one CLI and
  composition root.
- Script bodies, gateway layers, workflows, docs, and tests are deleted or
  rewritten when they no longer protect product behavior.
- File-backed world and replay are the deterministic baseline; external stores
  and live providers are additive.
- Linux can prove the standalone core, but Windows 11 + PowerShell 7 remains a
  separate product-edge acceptance lane.
- Current green tests prove the pre-rebuild baseline, not completion of this
  decision.
- Donor intake is blocked until clone/build/test/stub/replay/release gates are
  green without external owner surfaces.

## Source Surfaces

- `docs/autonomy/README.md`
- `docs/autonomy/dependency-ledger.json`
- `docs/autonomy/protected-behavior.json`
- `AGENTS.md`
- `MANIFEST.md`
- `ROADMAP.md`
- `docs/SOURCE_OF_TRUTH.md`
- `docs/PRODUCT_EDGE_POSTURE.md`

## Validation

- Validate the autonomy ledgers and their evidence anchors through
  `tests/test_autonomy_contract.py`.
- Regenerate and validate the decision indexes.
- Run the public and nested-guidance hardening tests.
- Run the full deterministic repository test suite.
- Treat fresh-clone standalone, package build, stub/replay, negative cases,
  release artifacts, and separate Windows acceptance as later executable gates;
  this decision record alone does not satisfy them.
