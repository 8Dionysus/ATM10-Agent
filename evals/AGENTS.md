# AGENTS.md

## Applies to

This card applies to `ATM10-Agent/evals/` and every file below it.

## Role

This companion eval lane owns deterministic ATM10 cases, suite membership,
ATM10-owned verdicts, reports, and source refs.

## Read before editing

Read the root `AGENTS.md`, then this card, `README.md`, `manifest.json`, and the
nearest intake, deterministic cases, suites, or reports surface you will touch.

## Boundaries

- Keep perception, retrieval, project KAG, safe automation, operator panel,
  voice, and recovery behavior in `ATM10-Agent`.
- Keep verdict and regression authority for the ATM10 product inside this
  repository.
- Do not treat an intake packet as proof acceptance or a test result.
- Do not place private traces, secrets, or unreduced operator evidence here.

## Validation

```powershell
cd <repo-root>
python scripts/validate_local_evals.py
```

## Closeout

Report changed eval surfaces, current manifest/suite status, validation run,
tests actually executed, and uncovered protected behavior.
