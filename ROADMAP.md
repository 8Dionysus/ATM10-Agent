# ROADMAP.md — ATM10-Agent

Public direction for rebuilding `ATM10-Agent` as an autonomous local companion.
Execution detail stays in reviewable wave branches; the durable boundary and
machine-readable ledgers live in `docs/autonomy/README.md`.

## Strategic baseline

The product is one modular monolith around:

`Perception -> Interpretation -> World/Memory -> Response/Plan -> optional Action/Voice -> Trace`.

The default proof path is deterministic, file-backed, dependency-light, and
replayable. Windows capture, OpenVINO, remote models, Qdrant, Neo4j, FastAPI,
Streamlit, ASR, and TTS are adapters or providers. They may enrich a turn but
must not own the loop or block core install, build, tests, stub/replay, or
release.

The package target is `atm10_agent`, with one composition root and CLI. The
source tree must not depend on repository-path injection or imports from
`scripts.*`.

## Autonomy law

- No required sibling repository, `.aoa`, OS skill profile, shared validator,
  shared runtime, or hidden workstation configuration.
- Mutable world state and append-only traces remain separate.
- Safe automation stays dry-run by default.
- Optional-provider failure is explicit degraded behavior, never false success.
- Windows 11 + PowerShell 7 remains first-class product-edge evidence and is
  validated separately from the portable deterministic gate.
- Donor repositories remain read-only. Intake begins only after standalone
  autonomy is green and is one-way, immutable-revision pinned, path-bounded,
  license-reviewed, transformed, and receipt-backed.

## Protected heritage

The rebuild preserves behavior, not the old topology:

- deterministic stub and replay;
- fixture-backed retrieval and product KAG with citations;
- honest hybrid fallback and negative cases;
- intent -> plan -> dry-run safety with trace correlation;
- provider replaceability and use-site optional dependency failures;
- ATM10 window/session and capture evidence on Windows;
- public-safe paths, tokens, errors, and artifacts;
- useful `M6.19` dry-run records for `open_quest_book`,
  `check_inventory_tool`, and `open_world_map`.

Gateway endpoints, Streamlit panels, worker/service splits, Combo A, root
repo-self KAG, cross-owner ports, and gateway nightly promotion machinery are
retired. A future transport or UI must earn a smaller optional-adapter role
through package-owned contracts and protected tests.

## Rebuild waves

### Wave 0 — baseline and disposition

- Pin the last green source revision and full test result.
- Record the dependency ledger and protected-behavior set.
- Distinguish product KAG from the external repo-self KAG read model.
- Classify each major surface as `keep`, `rewrite`, `optionalize`, `cut`, or
  post-gate `import_once`.

Exit: baseline and ledgers are source-owned, validated, and reviewable.

### Wave 1 — autonomy contract and behavior fence

- Accept the autonomous modular-monolith decision.
- Align canonical docs and repository guidance.
- Add contract tests for dependency dispositions and behavior anchors.
- State the no-donor stop line before the standalone gate.

Exit: direction cannot drift back to a gateway/federation center unnoticed.

### Wave 2 — sever OS and federation dependencies

- Replace external KAG action and stats checkout in `Repo Validation`.
- Remove root repo-self KAG from the active product and required CI plane while
  retaining `src/atm10_agent/kag` product behavior.
- Replace the eval skeleton and stats delegate with owner-local tests or delete
  them when they add no product signal.
- Remove `.aoa`, global-skill, sibling-validator, and shared-runtime assumptions
  from active guidance and commands.

Exit: repository validation is standalone and searches find no required
federation edge.

### Wave 3 — installable package and one composition root

- Add `pyproject.toml` and build metadata.
- Move product code under `atm10_agent`.
- Replace path injection and `scripts.*` imports with package imports.
- Expose one CLI/composition root; keep any remaining scripts thin.
- Normalize core and optional dependency groups.

Exit: clean environment install, import, CLI help, build, and tests pass without
repository path tricks.

### Wave 4 — companion-loop runtime

- Implement explicit turn contracts across perception, interpretation,
  world/memory, response/plan, optional action/voice, and trace.
- Make file-backed state and deterministic replay the baseline.
- Keep stores, live models, UI, gateway, hardware capture, and voice behind
  provider interfaces.
- Remove duplicated orchestration, service-only indirection, and gateway
  governance that does not protect a turn.

Exit: one in-process stub/replay turn exercises the complete product boundary.

### Wave 5 — dependency and artifact normalization

- Produce reproducible resolved dependency evidence.
- Declare missing direct dependencies and remove unused or contradictory
  profiles.
- Keep optional extras import-light and use-site checked.
- Define release artifacts and a clean source distribution/wheel boundary.

Exit: dependency audit, build, install-from-artifact, and negative optional
provider checks are green.

### Wave 6 — portable standalone proof and separate Windows evidence

- Prove fresh-clone core install, build, tests, deterministic stub/replay,
  cited retrieval/world behavior, dry-run action safety, degraded failures, and
  release artifacts.
- Run the proof without sibling checkouts, `.aoa`, OS skill profiles, shared
  validators, live stores, or model downloads.
- Record Windows 11 + PowerShell 7 acceptance separately for session discovery,
  capture, launch, trace, and dry-run fences.

Exit: all portable standalone acceptance gates are green. Windows remains an
independent product-edge evidence lane: an unfinished Windows run blocks
Windows and complete-release claims, but not controlled Wave 7 intake.

### Wave 7 — controlled donor intake

- Review only explicit donor candidates for evals, KAG/world, stats, memo,
  routing, and runtime discipline.
- Pin immutable revisions and selected paths.
- Record license, transformation, local ownership, tests, and rejection
  reasons.
- Vendor or reimplement only what improves the already autonomous product.
- Keep admission and implementation status in
  `docs/intake/donor-ledger.json`.

Exit: imported material has no live donor dependency and passes the same local
gates.

### Wave 8 — landing and closeout

- Land bounded, reviewable pull requests with required checks.
- Remove superseded docs, workflows, scripts, tests, and compatibility shells.
- Validate a clean merged `main`, release artifacts, and the full definition of
  done.
- Report residual debt without collapsing it into the green slice.

## Definition of done

The rebuild is complete only when all of the following are true:

1. One installable `atm10_agent` package owns the product.
2. One composition root and CLI can execute the full deterministic companion
   turn.
3. Clone, core install, build, tests, stub/replay, and release require no
   sibling repo, `.aoa`, OS skill profile, shared validator/runtime, service,
   model, or hidden host configuration.
4. Product KAG/world and cited retrieval remain useful without root repo-self
   KAG, Qdrant, or Neo4j.
5. Optional providers are replaceable, import-light, and honestly degraded.
6. Automation remains dry-run by default with executable negative tests.
7. Mutable state and append-only traces have distinct contracts.
8. Windows 11 + PowerShell 7 acceptance is current and separate.
9. No production code uses repository path injection or imports `scripts.*`.
10. Dependency metadata, resolved evidence, source distribution, and wheel are
    reproducible and installable.
11. Required GitHub checks are repository-owned and standalone.
12. Donor intake, if any, is pinned, path-bounded, licensed, transformed,
    receipt-backed, and one-way.
13. Obsolete gateway/governance/federation shells and their tests/docs are
    removed.
14. Full tests, focused smokes, negative cases, and release verification pass
    on merged `main`.
15. Pull requests are merged, the canonical worktree is clean/current, and
    remaining debt is reported explicitly.

The current Linux session may close its bounded rebuild slice after items
relevant to the portable core and donor foundations pass on merged `main`.
Item 8 remains intentionally open for the separate Windows session; that
bounded closeout must not be reported as complete Windows acceptance or a full
release.

## Principal risks

- Preserving files instead of behavior and accidentally recreating the old
  shell inside the new package.
- Treating Windows hardware evidence as a reason to make the portable core
  host-dependent.
- Letting optional stores or UI become implicit required services.
- Starting donor intake before autonomy and importing another owner's runtime
  along with useful ideas.
- Declaring completion from green unit tests while clean install, artifact,
  negative, Windows, or merged-main evidence is still missing.

Archived and recoverable implementation tracks remain in
`docs/ARCHIVED_TRACKS.md`; they do not override this roadmap.
