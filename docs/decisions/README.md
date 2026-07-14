# Decision Records Index

This directory is the durable public decision surface for `ATM10-Agent`.

Use it when a future contributor needs the rationale for a route, topology, owner boundary, validator route, operator posture, host-profile rule, public-surface rule, or dry-run safety decision.

Ordinary implementation notes, generated output, runtime logs, local run artifacts, private evidence, maintainer scratch notes, and one-off planning thoughts route to their owning surfaces instead.

## Operating Card

| Field | Route |
| --- | --- |
| role | durable ATM10 companion decision rationale entrypoint and index chooser |
| input | changed operator route, owner boundary, rejected option, validation guard, host-profile posture, or public-surface pressure |
| output | canonical decision note, generated lookup indexes, and route back to the owning source surface |
| owner | `docs/decisions/AGENTS.md` for lane law; decision notes for rationale; generated indexes for lookup only |
| next route | owning implementation or doc first, then nearest route card, `MANIFEST.md`, `ROADMAP.md`, `docs/SOURCE_OF_TRUTH.md`, generated lookup indexes, or the affected sibling owner |
| validation | executable decision-lane checks in `docs/decisions/AGENTS.md`, plus the owning validator for the changed surface |

## Authority

Decision notes explain why a route was chosen.

They are weaker than the source surface they describe:

- public status stays in `MANIFEST.md`;
- public direction stays in `ROADMAP.md`;
- active commands stay in `docs/RUNBOOK.md`;
- public document roles stay in `docs/SOURCE_OF_TRUTH.md`;
- product-edge support claims stay in `docs/PRODUCT_EDGE_POSTURE.md`;
- runtime and operator behavior stay in `scripts/`, `src/`, schemas, tests, and workflows;
- generated indexes stay derived from decision metadata;
- sibling repositories keep stronger truth for global AoA policy, KAG substrate ownership, stats, memo, skills, techniques, playbooks, evals, and runtime infrastructure.

Generated decision indexes are weaker than the decision notes. They exist to make lookup cheaper for agents, not to carry decision rationale.

## Index Shape

Each decision owns:

- a canonical `Decision ID: ATM10-D-####`;
- a full canonical-ID filename, for example `ATM10-D-0001-*.md`;
- an `## Index Metadata` block naming original date, surface classes, companion layers, operator surfaces, guard families, and posture.

The lookup indexes under [indexes](indexes/README.md) are generated from that metadata:

- [Decisions by canonical ID and number](indexes/by-number.md)
- [Decisions by date](indexes/by-date.md)
- [Decisions by surface class](indexes/by-surface.md)
- [Decisions by companion layer](indexes/by-companion-layer.md)
- [Decisions by operator surface](indexes/by-operator-surface.md)
- [Decisions by validation or guard family](indexes/by-guard.md)

Regenerate and check the read models after decision metadata changes through
the executable route in `docs/decisions/AGENTS.md`.

## Lookup Route

Do not hand-maintain a "latest decision" roster in this README. That list drifts as soon as a new decision lands.

Use the generated indexes instead:

- [by number](indexes/by-number.md) for the complete canonical ledger;
- [by date](indexes/by-date.md) for recent landings;
- [by surface](indexes/by-surface.md), [by companion layer](indexes/by-companion-layer.md), and [by operator surface](indexes/by-operator-surface.md) for owner-pressure lookup;
- [by guard](indexes/by-guard.md) for safety, validation, public-surface, or product-edge pressure.

The first decision records why this tracked public lane exists alongside the ignored local-only `docs/DECISIONS.md` scratch surface.

## Addressing

Full canonical-ID decision paths are the active source files:

- `docs/decisions/ATM10-D-0001-*.md`
- `docs/decisions/ATM10-D-0002-*.md`
- `docs/decisions/ATM10-D-####-*.md`

Canonical IDs remain stable handles. Previous path names belong to git, PR, or release history, not to a compatibility lookup layer.

## Naming

Use the full canonical decision ID as the filename prefix:

`ATM10-D-0001-short-decision-slug.md`

Prefer short titles that name the route, not the whole debate.

## Template

Start from [TEMPLATE.md](TEMPLATE.md) for new decisions. Keep notes concise, but include enough context, options, rationale, consequences, source surfaces, and validation for a future agent to avoid repeating the same route question.
