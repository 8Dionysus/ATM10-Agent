# Local Provider Routing and Reviewed Promotion

## Index Metadata

- Decision ID: ATM10-D-0004
- Original date: 2026-07-25
- Surface classes: architecture, provider selection, runtime promotion, owner boundary
- Companion layers: src, tests, docs, scripts
- Operator surfaces: perception, retrieval, KAG, voice, safe automation, host profile
- Guard families: autonomy, degraded honesty, provenance, explicit review, rollback
- Posture: accepted

## Context

The autonomous companion now owns one process and one composition root, but
provider choice still appeared only as scattered `provider`, `backend`, and
degradation fields. That is sufficient for deterministic execution but not for
explaining which bounded candidate was selected, why a fallback was used, or
how an operator can return to the selected implementation.

The same ambiguity existed around runtime improvement. A local benchmark may
show that a challenger is faster on one Linux host and fixture, but that packet
does not approve a provider, alter the active route, prove general quality, or
show that the repointed live lane still works.

## Decision

Keep routing thin and turn-local. Each active companion turn records explicit
capability-scoped route results with the selected provider, ordered attempts,
unavailable/degraded/rejected posture, fallback reason, return handle, and
trace-correlated decision ID. The route result describes a choice already made
inside `ATM10-Agent`; it is not a global selector, federation router,
capability graph, or persistent execution DAG.

Keep provider promotion as a separate reviewed artifact chain:

`machine fit + matched bounded comparison -> candidate -> explicit review -> externally evidenced activation -> separate post-activation check -> active or explicit rollback`.

No benchmark, candidate builder, or review record automatically changes
runtime configuration. A failed post-activation check requires a separately
recorded rollback; a passing check verifies only the named provider route,
host scope, and fixture contract.

## Options Considered

- Keep provider identity and fallback meaning implicit in each stage. Rejected
  because traces could not distinguish selection, unavailability, rejection,
  and bounded degraded use consistently.
- Add a central ATM10 or AoA-style global router and let benchmark winners
  repoint it automatically. Rejected because it creates a second composition
  authority, revives shared-runtime coupling, and collapses evidence into
  activation.
- Add local route records plus a reviewed, non-mutating promotion contract.
  Accepted because it improves traceability while preserving the modular
  monolith, provider ownership, and explicit operator boundary.

## Rationale

The accepted route makes every current provider family inspectable without
probing absent optional services or importing donor machinery. It also keeps
contract fit, host comparability, performance signal, review, activation, live
verification, and rollback as different facts. This prevents a flattering
benchmark or a source card from becoming hidden production authority.

## Consequences

- Deterministic capture/input, VLM, embedded world/store, product KAG, text
  response, ASR/TTS, and dry-run game-tool routes are visible in turn traces.
- Optional providers remain caller-supplied candidates; the route contract
  does not discover, install, start, or health-check them globally.
- Matched runtime evidence can create only a review candidate.
- Approval remains `approved_not_active` until a separately evidenced
  activation is recorded.
- Activation remains pending until its own post-check passes.
- Failed post-checks are explicit degraded posture and require an explicit
  rollback record.
- Provider quality, gameplay benefit, and cross-host superiority remain
  outside this decision.

## Source Surfaces

- `src/atm10_agent/providers/routing.py`
- `src/atm10_agent/providers/promotion.py`
- `src/atm10_agent/app.py`
- `src/atm10_agent/trace/__init__.py`
- `tests/test_provider_routing.py`
- `tests/test_provider_promotion.py`
- `evals/suites/companion-core.json`
- `docs/intake/donor-ledger.json`

## Validation

- Run the provider routing, promotion, companion, trace, and eval tests.
- Regenerate and validate decision indexes from this source record.
- Build wheel and sdist, then verify the installed dependency-free wheel
  outside the repository.
- Keep live optional providers and Windows product-edge acceptance outside the
  bounded claim until their separate evidence exists.
