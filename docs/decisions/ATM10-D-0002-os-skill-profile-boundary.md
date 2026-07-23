# OS Skill Profile Boundary

## Index Metadata

- Decision ID: ATM10-D-0002
- Original date: 2026-07-23
- Surface classes: owner boundary, skill exposure, generated/read-model
- Companion layers: root, tests, KAG
- Operator surfaces: none
- Guard families: owner boundary, discovery, generated/read-model
- Posture: accepted

## Context

`ATM10-Agent` still carried 27 copied AoA bundles under `.agents/skills`.
Twenty-five were shared procedures owned elsewhere; two were thin ATM10
overlays over repository change and source-authority work. The copies entered
repository-local discovery, competed with the OS user profile, and were indexed
by the local KAG family as though they were ATM10-authored sources. A dedicated
test exercised scripts and wording inside those copies instead of an ATM10
runtime contract.

Manual read-only comparisons covered the two local overlays against the current
root and nested `AGENTS.md`, `docs/SOURCE_OF_TRUTH.md`, the host-native change
loop, global knowledge stewardship, and owner-qualified semantic adapters. Raw
trial prompts and traces remain session-owned.

## Decision

Remove the copied `.agents/skills` catalog and the test that exists only for
that catalog. Shared and globally advertised skills are supplied once through
the OS user profile. ATM10 project facts, commands, and stop lines remain in
their authored repository surfaces.

The two former ATM10 overlays remain discoverable as owner-qualified semantic
adapters in the shared capability graph; they do not justify callable
repository bundles. If a future ATM10-specific procedure develops a distinct
trigger, ABI, composition value, and demonstrated benefit, its canonical source
must first be admitted under a top-level owner `skills/` home. A repository
projection may not duplicate a same-name global installation.

## Landing Gate

Do not merge the projection deletion until a fresh Codex session using the
intended OS user profile demonstrates a callable front door or an explicit
owner/host route for every shared capability outcome being removed from
ATM10-local discovery. The historical bundle name need not survive when the
central migration has a manually evaluated functional successor or a proven
non-skill owner. A graph node or migration row alone is not evidence.

The two ATM10-specific overlays have already passed that manual comparison.
Their raw prompts and traces remain session-owned.

The landing gate passed on 2026-07-23:

- a fresh read-only Codex session in the cleaned ATM10 checkout selected the
  global `aoa-knowledge-stewardship` authority-map front door without being
  given either historical ATM10 skill name;
- it selected Artifact Trust only as a conditional second capability for a
  concrete generated-artifact consumer boundary and correctly excluded it from
  an ordinary source edit;
- both installed packages returned through v2 receipts to byte-identical owner
  bundles, while full-owner ref lag was bounded to changes outside those bundle
  paths;
- the current checkout contained no `.agents/`, no active `SKILL.md`, and no
  same-name repository definition;
- the former change overlay's useful remainder stayed in root and nested
  `AGENTS.md`, `docs/SOURCE_OF_TRUTH.md`, owner builders and checks, and the
  host-native `plan -> scoped edit -> verify -> report` loop.

The central migration ledger separately carries the manually evaluated
functional disposition for every removed shared name. This gate proves
delivery and selection for the two ATM10-specific outcomes; it does not claim
that every historical bundle name remains callable or that the installed
profile is permanently drift-free.

## Options Considered

- Keep refreshing the full copied catalog inside ATM10.
- Retain only the two ATM10 overlay bundles under `.agents/skills`.
- Remove the projection, use one OS user profile for callable skills, and keep
  owner routing in authored ATM10 surfaces plus the federated capability graph.

## Rationale

The change overlay reproduced the host and repository change loop while adding
context and premature workflow ceremony. The authority overlay improved route
focus over an unassisted case, but the current global authority-map procedure
plus the ATM10 owner adapter preserved the same useful boundary without a
second callable package. Neither overlay owns ATM10 truth.

Deleting the projection restores one prompt-visible copy per globally exposed
skill, removes stale technique-bound packages, and prevents the local KAG
read-model from treating foreign copies as owner sources.

## Consequences

- A new session can still discover global AoA functions through the OS user
  profile.
- ATM10 repository work continues to route through root and nearest
  `AGENTS.md`, current source surfaces, and owner commands.
- The local KAG family must be rebuilt so deleted copies disappear as active
  source, artifact, anchor, entity, assertion, and relation records. Event
  history may retain them only as explicit deletion evidence.
- Git history preserves the removed packages; it does not make them active
  instructions.
- This decision does not forbid future repository-only skills or claim that
  every semantic adapter should become a skill.

## Source Surfaces

- `AGENTS.md`
- `docs/SOURCE_OF_TRUTH.md`
- `docs/decisions/ATM10-D-0002-os-skill-profile-boundary.md`
- `.agents/skills/` at the parent revision
- `tests/test_aoa_skill_contract_scripts.py` at the parent revision
- `kag/`
- `8Dionysus/aoa-skills` owner skill-profile and capability contracts

## Validation

- Regenerate and validate the decision indexes.
- Rebuild the canonical repo-local KAG family from the cleaned source tree and
  verify source/full-incremental parity through its owner route.
- Run the focused public, nested-guidance, and KAG checks plus the full
  repository test suite.
- Inspect a fresh repository-root skill inventory and confirm the deleted
  copies no longer appear while the OS user profile remains the global route.
