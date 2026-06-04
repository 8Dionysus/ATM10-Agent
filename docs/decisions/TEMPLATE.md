# ATM10-D-#### Short Decision Title

## Index Metadata

- Decision ID: ATM10-D-####
- Original date: YYYY-MM-DD
- Surface classes: docs/route-law
- Companion layers: docs
- Operator surfaces: none
- Guard families: public-surface hygiene
- Posture: proposed

## Context

What pressure made the decision necessary?

Name the docs, scripts, modules, tests, schemas, examples, workflows, or operator surfaces that shaped the choice.

## Decision

State the chosen route in one or two paragraphs.

## Options Considered

- Option A:
- Option B:
- Option C:

## Rationale

Explain why this route fits `ATM10-Agent` as a local-first operator-facing companion with dry-run safety, reproducible artifacts, public-doc hygiene, and explicit host-profile posture.

## Consequences

Name what becomes easier, what remains constrained, and what future contributors must not infer from this decision.

## Source Surfaces

- `AGENTS.md`
- `MANIFEST.md`
- `ROADMAP.md`
- `docs/SOURCE_OF_TRUTH.md`

## Validation

Run:

```powershell
python scripts/generate_decision_indexes.py
python scripts/generate_decision_indexes.py --check
python scripts/validate_decision_records.py
```

Also run the validator for the owning surface the decision describes.
