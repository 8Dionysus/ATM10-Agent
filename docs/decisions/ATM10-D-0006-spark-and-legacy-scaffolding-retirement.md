# ATM10-D-0006 Spark And Legacy Scaffolding Retirement

## Index Metadata

- Decision ID: ATM10-D-0006
- Original date: 2026-09-04
- Surface classes: agent route, mechanics/topology, docs/route-law, scripts/validation, legacy/provenance
- Companion layers: docs, scripts, tests, agent-lane
- Operator surfaces: none
- Guard families: owner boundary, source/history preservation, validator restraint
- Posture: accepted retirement record; current active routes remain authoritative

## Decision

Retire the listed Spark and legacy scaffolding roots from the current owner surface. Historical bytes remain recoverable in git; this note records immutable baseline links and does not recreate compatibility stubs. Active validators and route maps must describe only current package surfaces.

## Baseline historical links

- [Spark/AGENTS.md](https://github.com/8Dionysus/ATM10-Agent/blob/d31c5e841070f3a7177f8c4a082a25c7e4daff06/Spark/AGENTS.md)

## Consequences

No runtime, memo, `.aoa`, remote, tag, or merge state is changed by this record. Generated indexes are read models and must be regenerated from this authored note. ATM10 remains local-first and source-owned.
