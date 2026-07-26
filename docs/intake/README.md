# Controlled donor intake

This directory owns the one-way intake record for ideas researched after the
portable Linux autonomy gate passed. It does not vendor donor repositories and
does not make them part of clone, build, test, runtime, or release.

## Authority map

| surface | authority and role |
|---|---|
| pinned authored donor paths | authoritative only for the selected donor meaning at the recorded revision |
| ATM10 source, contracts, and tests | authoritative for ATM10 product behavior after local implementation |
| donor generated indexes, exports, runtime state, installed tools, and deployed mirrors | weaker navigation or operational evidence; never an intake source |
| `docs/intake/donor-ledger.json` | admission and provenance record; it does not prove implementation or benefit |

The source-owner boundary does not move. A transformed ATM10 contract may cite
a donor, but it becomes an ATM10-owned product surface and cannot inherit live
authority, synchronization, validation, or runtime requirements from that
donor.

## Current boundary

The deterministic Linux package gate passed at
`3a724cb0f0dd12ffc03713448cd9cc21dba2fc3f`. That evidence admits bounded
research and local reimplementation. Live Windows 11 + PowerShell 7 acceptance
is still unfinished and is assigned to a separate session; it is not evidence
for this gate and is not a prerequisite for donor intake.

Each admitted entry records:

- immutable repository revision and selected authored paths;
- reviewed license;
- transformation into a named ATM10-owned target;
- local tests required before `status` may become `adapted`;
- rejected nearest-wrong surfaces;
- runtime and synchronization prohibitions;
- a claim limit.

## Intake sequence

1. Re-read only the pinned selected paths and their owner guidance.
2. Implement the smallest ATM10-owned contract without donor imports, tools,
   services, config, or generated data.
3. Add deterministic local positive, negative, and degraded cases.
4. Update the ledger entry from `admitted_for_implementation` to `adapted`
   only in the same reviewed change that owns the target and tests.
5. Re-run standalone build, installed-wheel, replay, eval, and dependency
   checks before landing.

No automatic update path exists. A newer donor revision requires a new explicit
review and ledger change.

## Conflicts, fan-out, and residual edges

The earlier status text incorrectly coupled the Windows live lane to the
portable donor gate. `ATM10-D-0003` already kept them separate; current docs
now follow that decision. The ledger fans out only into the named ATM10 source
and test targets.

The unresolved edge is live Windows product acceptance. It remains visible in
`docs/WINDOWS_PRODUCT_EDGE_BOUNDARY.md` and blocks only claims that require the
physical Windows edge or a complete release, not this Linux intake.

## Claim limit and stop line

Schema-valid provenance proves that the intake was bounded and reviewable. It
does not prove that later code is correct, invoked, useful, or promoted.

Stop if an implementation needs a donor checkout, sibling validator, `.aoa`,
OS skill profile, shared runtime, generated donor artifact, network lookup, or
automatic synchronization. Keep the candidate admitted but unadapted until an
ATM10-owned deterministic route exists.
