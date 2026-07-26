# ATM10 autonomy contract

This directory is the source-owned transition contract for rebuilding
`ATM10-Agent` as an autonomous modular monolith.

## Product boundary

The product is one local companion loop:

`Perception -> Interpretation -> World/Memory -> Response/Plan -> optional Action/Voice -> Trace`

The loop, its deterministic stub/replay path, and its tests must work from a
fresh clone without an AoA sibling checkout, `.aoa`, an OS skill profile,
shared validators, a shared runtime, or hidden workstation configuration.

Optional providers may enrich a turn, but they do not own the loop:

- Windows capture and ATM10 session discovery;
- OpenVINO or remote model providers;
- Qdrant and Neo4j stores;
- FastAPI and Streamlit presentation;
- ASR and TTS;
- future provider families.

Missing optional providers must produce an explicit degraded result and trace,
not an import failure, silent empty answer, or false success.

## State and evidence

Mutable companion state and append-only execution traces are different owner
surfaces. A state update may be retried or replaced. A trace records what was
observed, selected, degraded, planned, and optionally executed; it is never a
hidden control plane.

## Dependency law

`dependency-ledger.json` classifies every known boundary pressure as one of:

- `keep`: product-owned and allowed in the standalone core;
- `rewrite`: useful semantics move behind the package or a local contract;
- `optionalize`: adapter/provider only, absent from the core install and stub
  acceptance path;
- `cut`: removed from the active product and required validation plane;
- `import_once`: a pinned, reviewed donor input allowed only after the
  standalone autonomy gate is green.

No `import_once` item may become a live runtime, build, test, or release
dependency. Donor intake is one-way and must record source repository, immutable
revision, selected paths, local destination, transformation, license review,
and acceptance evidence.

## Protected behavior

`protected-behavior.json` names the semantics that must survive the rebuild.
The current implementations are evidence anchors, not architectural
entitlements: scripts, gateway endpoints, nightly workflows, or service
topologies may be deleted after their protected behavior is covered through the
new package boundary.

## Gates

1. Record the baseline, dependency disposition, and protected behavior.
2. Establish the autonomy decision and a behavior fence.
3. Remove required OS and federation edges.
4. Build the installable `atm10_agent` package with one composition root and
   CLI, without path injection or `scripts.*` imports.
5. Collapse runtime ownership around the companion loop; keep UI, gateway,
   stores, voice, and hardware providers optional.
6. Prove fresh-clone, build, test, stub/replay, negative, and release behavior.
   Windows 11 + PowerShell 7 acceptance remains a separate evidence lane.
7. Only after gate 6 is green, admit bounded one-way donor intake.
8. Land reviewable waves and close against the complete definition of done.

Current status is transition, not completion. The source baseline below is the
last known green pre-rebuild state:

- source revision: `f0108816981e81a5951ed0f74743982a46a8fad1`;
- host baseline: Python 3.14.6 on Linux;
- test baseline: `764 passed, 1 skipped`;
- tracked shape: `src/` 34 files / 6,422 lines, `scripts/` 82 files /
  41,487 lines, `tests/` 118 files / 27,004 lines, root `kag/` 301 files /
  7,410,728 bytes;
- structural debt: 40 scripts inject repository paths, 23 scripts import
  `scripts.*`, nine requirements files exist, and no installable-project
  metadata exists.

This baseline does not make the old topology the target. It makes removals and
behavioral regressions reviewable.

## Current migration progress

- Waves 0-2 are landed through source revision
  `43c801fc57b07515783b31c5b246e360344f5f4c`: the autonomy
  decision and behavior fence are source-owned, required federation edges are
  removed, and repository validation is local.
- Waves 3-5 introduced `pyproject.toml`, the single
  `src/atm10_agent/` namespace, `CompanionApp`, and `atm10
  doctor|run|replay|eval|windows-acceptance`. The package now owns
  deterministic intent planning, action normalization, the no-input dry-run
  fence, trace correlation, the executable companion-core eval, and a typed
  live Windows evidence collector.
- The gateway/governance, operator/Streamlit, pilot-loop, separate HTTP
  voice/TTS service, and Fedora parallel-launcher control plane is removed.
  Windows capture is now package-owned and independently tested.
- Dependency declarations now have one authority, the core lock resolves only
  the local package, and release verification builds wheel/sdist then exercises
  the installed wheel without dependencies outside the checkout.
- Wave 6 remains open for final fresh-clone/merged-main proof and current live
  Windows 11 + PowerShell 7 session, capture, trace, and dry-run evidence.
  The collector exists but has not passed on a physical Windows edge in this
  migration session. Donor intake remains blocked until both lanes are green.
