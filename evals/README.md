# ATM10 companion eval lane

This directory owns deterministic ATM10 companion eval cases, suite membership,
local verdicts, and public-safe reports.

`manifest.json` and `suites/companion-core.json` route the first active suite to
existing fixture-first tests. An eval case becomes evidence only when its local
test runs and passes; location alone is not a verdict.

Executable reports use `atm10_eval_report_v2`. They name one bounded claim,
in-scope and out-of-scope surfaces, categorical support, separate measurement
observations, provenance handles, portability invariants, blind spots, and a
claim limit. Metrics remain measurement-only signals; they do not become a
proof score.

## Route

- Put proposed companion cases in [intake](intake/).
- Put accepted deterministic suites in [suites](suites/).
- Put local run or review reports in [reports](reports/).
- Validate the lane with `python scripts/validate_local_evals.py`.

## Current Status

Active: `atm10-companion-core` protects the deterministic stub turn, cited
retrieval, file product KAG, turn-local provider-route honesty, explicit
degradation, and the dry-run action fence. A passing report supports only that
deterministic core claim and does not prove Windows acceptance, live-provider
quality, gameplay correctness, or product benefit.
