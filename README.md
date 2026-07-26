# ATM10-Agent

[![Windows package](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/pytest.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/pytest.yml)
[![Portable Core Linux](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/portable-core-linux.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/portable-core-linux.yml)
[![Security Nightly](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/security-nightly.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/security-nightly.yml)

Autonomous local-first companion for All the Mods 10. Windows 11 +
PowerShell 7 is the first product edge; the deterministic core is portable.

The product is one installable modular monolith:

`Perception -> Interpretation -> World/Memory -> Response/Plan -> optional Action/Voice -> Trace`

`atm10_agent` owns the composition root and the
`atm10 doctor|run|replay|eval|consolidate-memory|windows-acceptance|verify-windows-acceptance`
CLI. Core install,
deterministic turn, replay, and product eval need no model, service, sibling
repository, `.aoa`, OS skill profile, shared validator, or network access.

## Start here

- current capabilities and honest limits: `MANIFEST.md`
- direction and definition of done: `ROADMAP.md`
- active commands: `docs/RUNBOOK.md`
- autonomy law and dependency dispositions: `docs/autonomy/README.md`
- controlled donor intake and provenance: `docs/intake/README.md`
- Windows acceptance boundary: `docs/WINDOWS_PRODUCT_EDGE_BOUNDARY.md`
- bounded hybrid degradation receipts: `docs/ANTIFRAGILITY_FIRST_WAVE.md`
- public document roles: `docs/SOURCE_OF_TRUTH.md`
- durable rationale: `docs/decisions/README.md`

## Current posture

- deterministic full-loop turns and replay are package-owned;
- file-backed retrieval and product KAG return citations without external
  stores;
- action is fenced to deterministic dry-run output with intent/trace
  correlation;
- optional voice degrades explicitly when no provider is configured;
- Windows capture is package-owned, DXcam-first for monitor/region capture,
  and records Pillow fallback failures;
- live Windows acceptance has a package-owned v2 receipt collector with
  explicit degraded no-audio posture and an offline artifact verifier, while
  the current physical run remains a separate release gate;
- append-only run traces, mutable state, and eval reports use separate
  directories;
- online memory capture keeps observed world state and player episodes
  append-only, working context mutable, and consolidation explicit;
- file world/KAG returns authored-source handles, derived relation context, and
  bounded readiness without treating memory as world authority;
- eval reports keep bounded claims, categorical verdicts, provenance, blind
  spots, portability, and measurement-only metrics explicit;
- the legacy gateway/operator/pilot/service control plane is retired.

The useful `M6.19` intent vocabulary remains protected through the package:
`open_quest_book`, `check_inventory_tool`, and `open_world_map`. All three
produce plans and dry-run evidence; none emits keyboard or mouse input.

The portable Linux autonomy gate is green, so bounded one-way donor intake is
open through `docs/intake/donor-ledger.json`. Live Windows acceptance remains
unfinished in a separate lane and is not claimed by that gate.

## Project links

- `CONTRIBUTING.md`
- `SECURITY.md`
- `CODE_OF_CONDUCT.md`
- `LICENSE`
