# ATM10-Agent manifest

Current as of: 2026-07-26

## Product

`ATM10-Agent` is an autonomous local-first ATM10 companion. One installable
package, `atm10_agent`, owns:

1. perception;
2. interpretation;
3. source-owned file world recall and product KAG;
4. embedded temporal memory with explicit online capture and offline
   consolidation;
5. cited response/plan;
6. optional dry-run action and voice;
7. append-only trace and deterministic replay.

The composition root is `atm10_agent.app.CompanionApp`. The supported command
surface is
`atm10 doctor|run|replay|eval|consolidate-memory|windows-acceptance|verify-windows-acceptance`.

## Active capabilities

- dependency-free core metadata and import-safe package modules;
- deterministic placeholder perception and replaceable VLM providers;
- fixture or user-file retrieval with ranked citations;
- local file KAG with optional Neo4j backend;
- source-owned world knowledge with resolvable return handles, derived relation
  context, and bounded readiness;
- explicit hybrid degradation and useful negative evidence;
- deterministic `M6.19` plans for `open_quest_book`,
  `check_inventory_tool`, and `open_world_map`;
- hard dry-run action fence with `executed=false`;
- explicit no-provider voice degradation;
- separate mutable state, append-only memory objects, mutable working context,
  turn traces, action traces, and eval reports;
- explicit five-kind memory canon with separate trust axes and
  proposed-only offline semantic/procedural consolidation;
- Windows ATM10 session discovery plus package-owned DXcam-first capture with
  Pillow fallback evidence;
- owner-typed live Windows receipt collection with source revision, OS/shell,
  session, screenshot, explicit degraded no-audio posture, hashed turn
  artifacts, dry-run correlation checks, and bounded offline verification;
- executable seven-case `companion-core` product eval;
- bounded eval v2 reports with categorical support, named scope, provenance,
  blind spots, portability limits, and measurement-only metrics;
- Windows package tests/smoke and portable installed-package Linux smoke.

## Retired architecture

The gateway, HTTP service, gateway-SLA promotion, cross-service benchmark,
operator snapshot/recovery, Streamlit panel, pilot loop, separate HTTP
voice/TTS services, and Fedora parallel launcher are not active product
surfaces. Their protected semantics now live behind package contracts and
tests; their process topology, schemas, workflows, and compatibility runners
were removed.

FastAPI and Streamlit are no longer declared package dependencies. A future UI
or transport must be a small optional adapter over `CompanionApp`, not a
second owner of the turn.

## Acceptance posture

Currently proven in source:

- package core behavior and product eval;
- package boundary without `scripts.*` imports or repository path injection;
- standalone repository-owned CI routes;
- import-safe optional dependency boundaries;
- a single `pyproject.toml` dependency authority plus dependency-free core lock;
- verified wheel/sdist structure and installed-wheel doctor, turn, replay, and
  eval from a clean environment outside the checkout;
- fresh-clone and merged-main Linux proof at
  `3a724cb0f0dd12ffc03713448cd9cc21dba2fc3f`;
- admitted, immutable-revision-pinned donor candidates in
  `docs/intake/donor-ledger.json`, with no live donor dependency;
- Windows capture/session contracts through deterministic tests;
- Linux execution of the live collector is explicitly blocked rather than
  accepted as substitute evidence.

Still required before the full rebuild and release may be called complete:

- live Windows 11 + PowerShell 7 session, capture, trace, and dry-run evidence;
- ATM10-owned implementation and local validation of the admitted donor
  foundations;
- final fresh-clone and merged-main Linux verification after those slices.

The Linux standalone gate admits controlled donor intake. Windows product-edge
acceptance remains unfinished and moves independently in a separate session.

## Canonical routes

- architecture and dependency law: `docs/autonomy/README.md`
- donor provenance and admission status: `docs/intake/README.md`
- direction and definition of done: `ROADMAP.md`
- active commands: `docs/RUNBOOK.md`
- product-edge claims: `docs/PRODUCT_EDGE_POSTURE.md`
- document authority: `docs/SOURCE_OF_TRUTH.md`
- durable decisions: `docs/decisions/README.md`
- bounded hybrid degradation receipts: `docs/ANTIFRAGILITY_FIRST_WAVE.md`
