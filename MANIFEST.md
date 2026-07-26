# ATM10-Agent manifest

Current as of: 2026-07-25

## Product

`ATM10-Agent` is an autonomous local-first ATM10 companion. One installable
package, `atm10_agent`, owns:

1. perception;
2. interpretation;
3. file-backed world recall and product KAG;
4. cited response/plan;
5. optional dry-run action and voice;
6. append-only trace and deterministic replay.

The composition root is `atm10_agent.app.CompanionApp`. The supported command
surface is `atm10 doctor|run|replay|eval`.

## Active capabilities

- dependency-free core metadata and import-safe package modules;
- deterministic placeholder perception and replaceable VLM providers;
- fixture or user-file retrieval with ranked citations;
- local file KAG with optional Neo4j backend;
- explicit hybrid degradation and useful negative evidence;
- deterministic `M6.19` plans for `open_quest_book`,
  `check_inventory_tool`, and `open_world_map`;
- hard dry-run action fence with `executed=false`;
- explicit no-provider voice degradation;
- separate mutable state, turn traces, action traces, and eval reports;
- Windows ATM10 session discovery plus package-owned DXcam-first capture with
  Pillow fallback evidence;
- executable seven-case `companion-core` product eval;
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
- Windows capture/session contracts through deterministic tests.

Still required before the autonomy gate may be called complete:

- reproducible dependency resolution and release artifact receipts;
- clean-environment/fresh-clone proof from the final tree;
- live Windows 11 + PowerShell 7 session, capture, trace, and dry-run evidence;
- merged-main verification after all migration slices.

Donor intake is blocked until those gates are green.

## Canonical routes

- architecture and dependency law: `docs/autonomy/README.md`
- direction and definition of done: `ROADMAP.md`
- active commands: `docs/RUNBOOK.md`
- product-edge claims: `docs/PRODUCT_EDGE_POSTURE.md`
- document authority: `docs/SOURCE_OF_TRUTH.md`
- durable decisions: `docs/decisions/README.md`
- bounded hybrid degradation receipts: `docs/ANTIFRAGILITY_FIRST_WAVE.md`
