# ATM10-Agent product-edge posture

Current as of: 2026-07-25

## Product edge

Windows 11 + PowerShell 7 is the first supported ATM10 product edge. Portable
Linux CI proves the deterministic package, not Minecraft window identity,
DXGI capture, or Windows hardware acceptance.

The portable core and release contract remain autonomous: no sibling checkout,
`.aoa`, OS skill profile, shared validator/runtime, live store, model, or
service is required.

## Test tiers

| tier | surface | honest claim |
|---|---|---|
| Package regression | `.github/workflows/pytest.yml` | full tests and installed-package `doctor`, turn, replay, and eval on Windows |
| Repository boundary | `.github/workflows/repo-validation.yml` | autonomy ledgers, decisions, package boundary, deterministic smoke, and installed-wheel release verification are source-owned |
| Portable core | `.github/workflows/portable-core-linux.yml` | core wheel behavior is portable and does not import Windows extras |
| Optional store | `.github/workflows/kag-neo4j-guardrail-nightly.yml` | Neo4j adapter quality only; it does not promote Neo4j into core |
| Security | `.github/workflows/security-nightly.yml` | declared dependency audit at the scheduled revision |
| Live Windows acceptance | `atm10 windows-acceptance` local receipt plus `atm10 verify-windows-acceptance` artifact verification | current ATM10 session, DXcam/Pillow source, explicit degraded no-audio posture, trace, artifact hashes, and dry-run fence on Windows 11 + PowerShell 7; neither a source-owned collector nor an offline consistency pass is evidence until collection passes on the real edge |

A support claim may not exceed the evidence tier that actually ran.

## Provider posture

- deterministic stub and file world: supported core;
- Windows ATM10 session and capture: first product edge, live acceptance still
  required for each release checkpoint;
- OpenVINO, remote model, Qdrant, Neo4j, ASR, and TTS: optional providers;
- HTTP transport and UI: absent; any future implementation must adapt
  `CompanionApp` without owning the turn;
- Linux: portable-core development lane, not a Windows parity claim.

## OS Abyss and donor boundary

OS Abyss, AoA, `abyss-stack`, and other repositories may be researched only
after standalone autonomy is green. They are not required clone, build, test,
runtime, validator, configuration, or release surfaces. Any accepted donor
material must be pinned, path-bounded, license-reviewed, transformed into
ATM10-owned code/data, receipt-backed, and one-way.

The portable Linux gate is green and the admitted sources live in
`docs/intake/donor-ledger.json`. Live Windows acceptance remains unfinished and
separate: it still gates physical Windows and complete-release claims, but it
does not gate this one-way research and reimplementation lane.

## Release cadence

`main` is rolling integration, not a release claim. A release checkpoint
requires the relevant package, standalone artifact, and live Windows evidence,
plus updates to `MANIFEST.md` and `ROADMAP.md`. Until that gate exists, semantic
version `0.1.0` describes package maturity, not a blanket hardware-support
promise.

## Related surfaces

- `MANIFEST.md`
- `ROADMAP.md`
- `docs/autonomy/README.md`
- `docs/WINDOWS_PRODUCT_EDGE_BOUNDARY.md`
- `docs/RUNBOOK.md`
- `docs/SOURCE_OF_TRUTH.md`
