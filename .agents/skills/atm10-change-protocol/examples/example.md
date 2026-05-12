# Example

## Scenario

An `atm10-*` repository needs a bounded code-and-doc change that touches `README.md`,
`docs/ARCHITECTURE.md`, and a small implementation file, and the maintainer wants the local
commands, approval posture, and review surface named explicitly before editing.

## Why this skill fits

- the base `aoa-change-protocol` workflow is already the right shape
- the repo still needs repo-relative files, commands, and review rules spelled out locally
- the task is a thin local adaptation, not a new workflow or playbook
- the family review doc and bundle-local checklist need to stay aligned

## Expected inputs

- the local files or surfaces under change
- the smallest repo-relative check, such as `python -m pytest` or `python scripts/[local-check].py`
- any local approval or review rule that still requires a maintainer decision
- the family review doc at `mechanics/boundary-bridge/overlays/atm10/REVIEW.md`

## Expected outputs

- a bounded local change plan
- repo-relative command and verification notes
- a short report that names what remains explicitly downstream

## Boundary notes

- do not use this overlay if the base skill can be used directly with no local adaptation
- do not widen the request into project doctrine or cross-repo automation

## Verification notes

- verify that the plan still follows the base `plan -> scoped change -> verify -> report` shape
- verify that all local files and commands stay repo-relative and reviewable
- verify that the family review doc and bundle-local checklist still agree
