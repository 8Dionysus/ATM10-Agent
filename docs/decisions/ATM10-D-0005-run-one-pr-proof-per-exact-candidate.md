# Run One PR Proof per Exact Candidate

## Index Metadata

- Decision ID: ATM10-D-0005
- Original date: 2026-08-13
- Surface classes: validation workflow, CI cost, landing latency
- Companion layers: workflows, tests, docs
- Operator surfaces: CI
- Guard families: exact candidate, required checks, post-merge proof, superseded-run cancellation
- Posture: accepted duplicate orchestration removed; proof unchanged

## Context

`portable-core-linux.yml` and `pytest.yml` listened to both every branch push
and `pull_request`. Opening or updating a PR therefore scheduled two copies of
the same Linux installed-package proof and two copies of both Windows jobs for
one source SHA. Public runs for at least five distinct July 2026 PR revisions
show this exact duplication. For example, revision
`09e416475767eec7b414d8105054fed1703699de` ran Linux smoke as push
`30189067904` and PR `30189078722`, plus Windows package as push `30189067934`
and PR `30189078714`. The redundant push copy consumed 94 hosted job-seconds
while proving no candidate identity absent from the PR copy.

Rapid updates also left an older run executing after a newer exact candidate
had superseded it. `repo-validation.yml` already used the correct PR plus
`main` trigger boundary, but did not cancel obsolete work in its own lane.

## Decision

Run each active candidate workflow on `pull_request` for pre-merge evidence and
on pushes to `main` for independent post-merge evidence. Do not run the same
workflow on non-main branch pushes as a second proof of the PR SHA.

Give each workflow its own concurrency group keyed by pull-request number or
Git ref and enable `cancel-in-progress`. Cancellation applies only when a newer
candidate supersedes an older run in the same workflow and PR/ref. Keep every
job, test selection, installed-package smoke, artifact check, check name, and
failure condition unchanged. Keep the portable workflow's manual dispatch.

## Options Considered

- Keep branch-push plus PR runs. Rejected because exact public history shows
  duplicate candidates and no additional claim class.
- Keep both triggers and group by source SHA. This can cancel one copy only
  after both have started, retaining avoidable checkout and runner allocation.
- Add path filters. Rejected because an incomplete impact map could skip a
  required owner proof.
- Use PR plus `main` push and cancel only superseded candidates. Accepted
  because it preserves the pre-merge and post-merge barriers while removing
  duplicate and stale orchestration.

## Rationale

The evidence barrier is candidate-scoped, not event-scoped. A second execution
of an identical workflow against the same SHA and environment class does not
strengthen the package, portable-core, or repository-boundary claim. The
selected event topology still proves every PR candidate before merge and the
landed tree after merge, while concurrency reduces retry amplification during
rapid agent fixes.

## Consequences

- One branch update with an open PR schedules three candidate workflows rather
  than five workflow runs and six jobs.
- `main` still schedules all three active workflows as post-merge proof.
- A newer PR SHA stops obsolete work, but cannot cancel another PR or another
  workflow's evidence.
- Direct non-main pushes without a PR no longer allocate hosted proof; local
  validation remains available, and opening a PR activates the full barrier.
- No semantic validation selection, Windows claim, portable claim, package
  smoke, artifact proof, or standalone owner boundary is weakened.

## Source Surfaces

- `.github/workflows/portable-core-linux.yml`
- `.github/workflows/pytest.yml`
- `.github/workflows/repo-validation.yml`
- `.github/AGENTS.md`
- `docs/PRODUCT_EDGE_POSTURE.md`
- `tests/test_workflow_public_surface.py`

## Validation

Run the public workflow-surface and decision-index contracts, then the complete
repository test suite. Require all three exact-head PR workflows to pass, merge
through GitHub, and require all three `main` workflow runs to pass without a
second non-main push copy.
