# VIA_NEGATIVA_CHECKLIST

This checklist is for `ATM10-Agent` as the product edge and public operator
surface.

## Keep intact

- README as a short entrypoint rather than an operations encyclopedia
- MANIFEST and ROADMAP as the main public status and direction surfaces
- PRODUCT_EDGE_POSTURE for support claims and the `ATM10-Agent` x
  `abyss-stack` boundary
- RUNBOOK for active runnable commands only
- ARCHIVED_TRACKS for rollback, restore, historical, and blocked paths

## Merge, move, suppress, quarantine, deprecate, or remove when found

- archived, rollback, or recoverable-only command blocks inside
  `docs/RUNBOOK.md`
- public status paragraphs duplicated across README, MANIFEST, ROADMAP, and
  wave docs
- ecosystem doctrine copied into product-edge docs without local product reason
- tracked review or session scratch docs that belong in local-only ignored
  space
- wave-scoped docs whose surviving content has already graduated into canonical
  docs

## Questions before adding anything new

1. Does this belong in RUNBOOK, or is it archival and better moved to
   ARCHIVED_TRACKS?
2. Is this status, direction, support boundary, or context, and does it
   already have a canonical home?
3. Does a new public file beat updating SOURCE_OF_TRUTH.md and one canonical
   target instead?

## Safe exceptions

- a new wave-scoped public doc when it carries materially distinct release or
  hardening reference
- short clarifications that remove ambiguity in active commands

## Exit condition

- The public surface should feel smaller and more role-pure after the pass.
