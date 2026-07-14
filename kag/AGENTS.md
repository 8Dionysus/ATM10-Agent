# AGENTS.md

## Applies to

This card applies to `ATM10-Agent/kag/` and every nested path until a nearer card
narrows the lane.

## Role

`kag/` is the local KAG provider home for `ATM10-Agent`. It exposes compact,
source-linked records over the project-local KAG runtime route and operator
runbook surfaces for `aoa-kag` registry, composition, and MCP consumers.

## Read before editing

Read the root `AGENTS.md`, this card, `kag/README.md`, `kag/manifest.json`,
`stats/README.md`, `docs/RUNBOOK.md`, `docs/SOURCE_OF_TRUTH.md`, and
`src/kag/AGENTS.md` before changing provider records.

## Boundaries

Keep project-local KAG and retrieval behavior with `ATM10-Agent`. Keep shared
KAG schema, registry, composition, and provider validation with `aoa-kag`. Keep
global runtime service ownership with `abyss-stack` and keep operator automation
safety inside the project-local docs and tests.

## Validation

Use the owner validator named in `manifest.json`, then validate this provider
through the `aoa-kag` local subtree validator.

## Closeout

Report provider records changed, source-return route changed, owner validation,
`aoa-kag` validation, and the next MCP consumer route.
