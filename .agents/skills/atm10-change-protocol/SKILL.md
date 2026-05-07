---
name: atm10-change-protocol
description: Apply the aoa-change-protocol workflow inside an atm10-* repository using repo-relative paths, commands, review checklists, and explicit local approval notes. Use when the base change protocol is correct but a thin project overlay is needed for local commands and source-of-truth surfaces. Do not use when the base skill is sufficient without local adaptation or when a broader playbook is needed.
license: Apache-2.0
compatibility: Designed for Codex or similar coding agents with repository file access and an interactive shell. Network access is optional and only needed when repository validation or referenced workflows require it.
metadata:
  aoa_scope: project
  aoa_status: evaluated
  aoa_invocation_mode: explicit-preferred
  aoa_source_skill_path: skills/project/atm10/atm10-change-protocol/SKILL.md
  aoa_source_repo: 8Dionysus/aoa-skills
  aoa_technique_dependencies: AOA-T-0001,AOA-T-0002
  aoa_portable_profile: codex-facing-wave-3
---

# atm10-change-protocol

## Intent
Use this skill to adapt `aoa-change-protocol` to an `atm10-*` repository without changing the base workflow meaning.

## Trigger boundary
Use this skill when:
- the base `aoa-change-protocol` workflow is already correct, but an `atm10-*` repo needs repo-relative paths, commands, or local approval notes
- a bounded non-trivial change still needs an explicit plan and verification path inside the local repo
- a contributor needs a thin local overlay rather than a fresh workflow design
- the family review doc and bundle-local checklist still need to stay aligned

Do not use this skill when:
- the task really needs a broader playbook or scenario bundle rather than a thin overlay
- the work would introduce new upstream technique meaning instead of adapting the local repo surface
- a more specific risk skill is still the clearer fit, such as `aoa-dry-run-first`, `aoa-safe-infra-change`, or `aoa-approval-gate-check`
- the task does not need repo-relative local adaptation and the base skill can be used directly

## Inputs
- target goal and touched local surface
- repo-relative source-of-truth files
- repo-relative commands or checks
- local approval or review rules
- base skill reference

## Outputs
- bounded local change plan
- repo-relative command or path sketch
- pointer to the family review surface
- verification note for the local repo surface
- concise handoff on what stays downstream and explicit

## Procedure
1. start from `aoa-change-protocol` rather than rewriting the workflow
2. name the repo-relative files, commands, and approval posture that matter locally
3. keep the adaptation bounded to the local repo surface under change
4. preserve the base `plan -> scoped change -> verify -> report` shape
5. make explicit what still requires downstream human approval or repo-specific judgment

## Contracts
- preserve the base skill meaning
- keep paths and commands repo-relative
- keep local authority explicit
- keep the overlay reviewable and public-safe

## Risks and anti-patterns
- hiding downstream authority inside vague local notes
- turning a thin overlay into repo doctrine or a scenario bundle
- naming local commands without enough verification context
- silently changing the base workflow instead of adapting it

## Verification
- confirm the base skill is still the correct workflow
- confirm repo-relative paths and commands are named explicitly
- confirm approval posture is still downstream and explicit
- confirm the adaptation remains bounded to the local repo surface
- confirm the family review doc and bundle-local checklist stay aligned

## Technique traceability
Manifest-backed techniques:
- AOA-T-0001 from `8Dionysus/aoa-techniques` at `cd276f040d55d490bd015b8698c7a5d594b9f875` using path `techniques/execution/agent-workflows-core/plan-diff-apply-verify-report/TECHNIQUE.md` and sections: Intent, When to use, Inputs, Outputs, Core procedure, Contracts, Risks, Validation
- AOA-T-0002 from `8Dionysus/aoa-techniques` at `cd276f040d55d490bd015b8698c7a5d594b9f875` using path `techniques/instruction/docs-boundary/source-of-truth-layout/TECHNIQUE.md` and sections: summary

## Adaptation points
- repo-relative change surfaces
- local commands and verification steps
- local source-of-truth files
- local approval or review notes
- family review doc and bundle-local review checklist
