# PRODUCT_EDGE_POSTURE.md

Current as of: 2026-04-21

This document defines the public product-edge contract for `ATM10-Agent`.
It keeps release cadence, supported profiles, CI/test tiers, and the `ATM10-Agent` x `abyss-stack` boundary short and explicit.

## Public release cadence

- `main` is the rolling integration branch. It is not a tagged public release channel by itself.
- Public release checkpoints are milestone-backed and wave-shaped: when a bounded milestone closes with the relevant CI tiers green for the currently supported profile, update `MANIFEST.md`, update `ROADMAP.md` if direction changed, and add a scoped `docs/RELEASE_*.md` reference when that checkpoint needs an engineering note.
- As of 2026-04-07, this repository has no GitHub releases or tags yet. The first explicit public tracking milestone is `WS12 - Public Product Edge Contract` (milestone `#1`), tracked in issue `#49`.
- Until tags exist, this repository publishes release posture through canonical docs first rather than through a semantic-version promise.

## Public test tiers

| tier | purpose | current surface | what it honestly proves |
|---|---|---|---|
| Tier 1 | merge confidence on the current repo contract | `.github/workflows/pytest.yml` | Windows-host repo validation, unit/integration regression, and core smoke coverage for the current public scripts and operator paths |
| Tier 2 | nightly guardrails and promotion evidence | `.github/workflows/gateway-sla-readiness-nightly.yml`, `.github/workflows/kag-neo4j-guardrail-nightly.yml`, `.github/workflows/security-nightly.yml` | trend/governance/security signals that can justify or block promotion, but are not a blanket support claim for every host/runtime path |
| Tier 3 | additive parity profile validation | `.github/workflows/combo-a-profile-smoke.yml` | the additive `combo_a` profile stays runnable and reviewable without replacing the default repo-host baseline |
| Dev lane | portable-core Linux development smoke | `.github/workflows/portable-core-linux.yml` | validates preliminary Fedora dev-companion mechanics and receipt seams; it is not a Fedora ATM10 product-edge support tier |

Rule: a public support claim should not exceed the highest tier that actually validates it.

As of 2026-04-21, the portable-core Linux lane is development validation only. It can support `fedora_local_dev` companion work and receipt mechanics, but it is not a Fedora ATM10 product-edge support claim.

## Supported profiles

| profile | status | current meaning |
|---|---|---|
| `ov_intel_core_ultra_local` | supported baseline | the validated repo-host baseline on Windows 11 + PowerShell 7 with the current `OpenVINO-first` runtime posture |
| `combo_a` | supported additive parity profile | an additive gateway/operator profile with external `Qdrant` + `Neo4j`, kept explicit and reviewable through dedicated smoke/nightly surfaces |
| `fedora_local_dev` | preliminary development profile | an additive Fedora-first workspace path for portable-core and dev-companion stabilization with a Linux development lane; not a public ATM10 product-edge support default |
| future host profiles such as `ollama_nvidia_local` or other non-OpenVINO paths | preliminary only | they may be explored, but they are not public supported defaults until they land as explicit host profiles with their own measurements, docs, and promotion evidence |

## ATM10-Agent x abyss-stack boundary

- `ATM10-Agent` remains a Windows 11 product-edge repository with its own runnable scripts, docs, tests, and operator surfaces.
- `fedora_local_dev` may be used as a Fedora-first development profile for portable core and operator-companion stabilization. It does not by itself prove ATM10/Minecraft parity, Windows-edge replacement, or broad `abyss-stack` deployment support.
- `abyss-stack` is the broader infrastructure substrate in the ecosystem. This repository may consume or align with that substrate, but its current public validation does not prove Fedora-first stack parity or broad deployment support across `abyss-stack` profiles.
- A future explicit supported-profile bridge to `abyss-stack` must be additive, named here, and reflected in `MANIFEST.md` and `ROADMAP.md` when it becomes a real public claim.

## Boundary hardening

- `ATM10-Agent` owns product-edge behavior, public docs, workflow hardening, and tests in this repository.
- It does not replace global AoA doctrine, sibling-repo ownership, or `abyss-stack` runtime authority.
- The internal agent stack remains bounded inside one local product/runtime boundary; public docs should not let that convenience read like a hidden federation center or monolith claim.

## Related surfaces

- `MANIFEST.md` for current public status
- `ROADMAP.md` for direction and milestones
- `docs/QWEN3_MODEL_STACK.md` for the current validated repo-host baseline
- `docs/RELEASE_WAVE6.md` for the current public hardening-wave reference
- `docs/SOURCE_OF_TRUTH.md` for public document roles
- `docs/FEDORA_COMPANION_MILESTONE.md` for the Fedora dev-companion receipt boundary
- `docs/WINDOWS_PRODUCT_EDGE_BOUNDARY.md` for the Windows ATM10 edge contract