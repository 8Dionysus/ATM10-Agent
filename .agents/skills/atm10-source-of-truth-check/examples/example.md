# Example

## Scenario

An `atm10-*` repository has a `README.md`, `docs/ARCHITECTURE.md`, and `docs/[canonical-guide].md`,
and contributors keep changing the overview doc when the canonical instructions really belong in one
repo-relative guide with a separate local review rule and a visible family review surface.

## Why this skill fits

- the base `aoa-source-of-truth-check` workflow is already correct
- the repo still needs a local canonical-file pattern and explicit doc review posture
- the task is a thin overlay on one repository family, not a broader policy redesign
- the family review doc and bundle-local checklist need to stay aligned

## Expected inputs

- the overlapping repo-relative docs
- the local concern under review, such as startup, deployment, or maintenance guidance
- any local review rule that decides how doc changes are approved
- the family review doc at `mechanics/boundary-bridge/overlays/atm10/REVIEW.md`

## Expected outputs

- a local source-of-truth map
- a repo-relative canonical-file recommendation
- a short verification summary that explains why the docs surface is easier to navigate

## Boundary notes

- do not use this overlay for purely code-local work with no document-authority question
- do not turn the example into a family-wide governance doctrine

## Verification notes

- verify that each local concern now points to a named authoritative file
- verify that overview docs no longer silently compete with the canonical guide
- verify that the family review doc and bundle-local checklist stay aligned
