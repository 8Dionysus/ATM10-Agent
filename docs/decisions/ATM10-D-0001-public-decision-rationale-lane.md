# Public Decision Rationale Lane

## Index Metadata

- Decision ID: ATM10-D-0001
- Original date: 2026-06-04
- Surface classes: docs/decisions, docs/source-of-truth, scripts/validation, tests/public-surface
- Companion layers: docs, scripts, tests
- Operator surfaces: none
- Guard families: public-surface hygiene, generated index parity, owner boundary
- Posture: accepted

## Context

`ATM10-Agent` already has a local-only ignored `docs/DECISIONS.md` scratch surface for maintainer notes. That protects private planning, but it does not give public contributors a stable place to find durable rationale for repository-visible route, boundary, validator, operator posture, or product-edge decisions.

The repository also has strong public owner surfaces: `MANIFEST.md` for current status, `ROADMAP.md` for direction, `docs/RUNBOOK.md` for runnable commands, `docs/SOURCE_OF_TRUTH.md` for document roles, and tests for public-surface hygiene. Decision rationale should be discoverable without competing with those stronger surfaces.

Sibling AoA repositories now use generated decision indexes to keep durable rationale findable. `ATM10-Agent` should adopt that discoverability pattern with local companion language rather than importing sibling mechanics or tree vocabulary.

## Decision

Adopt `docs/decisions/` as the tracked public decision rationale lane for `ATM10-Agent`.

Decision records use canonical `ATM10-D-####` IDs, full canonical-ID filenames, and an `## Index Metadata` block. Generated lookup indexes under `docs/decisions/indexes/` expose records by number, date, surface class, companion layer, operator surface, and guard family.

Decision records explain why a route was chosen. They do not replace current docs, implementation, tests, schemas, workflows, or generated/artifact evidence.

## Options Considered

- Keep all decisions in ignored `docs/DECISIONS.md`. This preserves maintainer privacy, but public rationale remains invisible and non-indexed.
- Put a flat tracked `docs/DECISIONS.md` ledger in the public tree. This is simple at first, but it drifts into a mutable live ledger and becomes expensive to search.
- Create a generated-indexed public lane under `docs/decisions/`. This keeps durable rationale public, indexed, and weaker than the owning source surfaces.

## Rationale

`ATM10-Agent` decisions often cross operator-facing boundaries: dry-run safety, public document roles, product-edge support claims, host-profile posture, CI smoke gates, gateway behavior, and artifact policy.

Those choices need durable rationale, but they must not become runtime authority. The owning implementation, docs, schemas, workflows, tests, and artifact contracts remain stronger.

The metadata is local to this repository:

- `Companion layers` names repo layers such as docs, scripts, src, schemas, examples, tests, and workflows.
- `Operator surfaces` names product-facing surfaces such as gateway, Streamlit, pilot runtime, safe automation, retrieval, KAG, voice, host profile, CI, or `none`.
- `Guard families` names the public-surface, safety, validation, owner-boundary, product-edge, or artifact-policy pressure that shaped the decision.

## Consequences

Future durable route-law, validator, public-surface, product-edge, host-profile, safe-automation, or operator-posture decisions should land as `ATM10-D-####` notes when the rationale would otherwise be hard to reconstruct.

Ignored `docs/DECISIONS.md` remains local-only scratch. Public decisions that affect repo-visible contracts belong in `docs/decisions/`.

If a decision changes, a new decision supersedes the old one. Existing IDs and filenames are not renumbered.

Generated indexes must stay derived from decision metadata and must not be hand-edited.

## Source Surfaces

- `AGENTS.md`
- `README.md`
- `MANIFEST.md`
- `ROADMAP.md`
- `docs/AGENTS.md`
- `docs/SOURCE_OF_TRUTH.md`
- `scripts/AGENTS.md`
- `tests/AGENTS.md`

## Validation

The executable decision-lane checks are owned by
`docs/decisions/AGENTS.md`. This first landing also used the public-surface
hardening route because it changed document roles and nested guidance.
