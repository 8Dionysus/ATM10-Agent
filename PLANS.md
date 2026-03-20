# PLANS.md — atm10-agent

English is the primary language. Technical terms remain in their conventional English form (Phase, smoke, RAG, KAG, artifacts, DoD, guardrail, gateway).

## Source Of Truth

Canonical document map: `docs/SOURCE_OF_TRUTH.md`.

Document roles:

* `TODO.md` — step-by-step execution (`Now/Next/Blocked`, WIP limit).
* `PLANS.md` — goals, milestones, Definition of Done, risks.
* `docs/SESSION_*.md` — detailed chronology of runs and artifacts.
* `docs/ARCHIVED_TRACKS.md` — archived/recoverable directions.

## Strategic Baseline (as of 2026-02-24)

Selected strategic baseline:

* Production baseline: **Combo A**.
* Frontend path: **Streamlit** (operator web panel) + CLI fallback.
* Backend path: FastAPI gateway + workers + Qdrant + Neo4j + file artifacts (`runs/...`).
* Runtime policy: `OpenVINO-first` with `CPU/GPU/NPU` fallback.
* Model policy: pragmatic hybrid by task:
  * text/retrieval/rerank: Qwen3 stack,
  * ASR active path: Whisper GenAI,
  * archived paths remain recoverable via explicit opt-in.

## North Star

Build a local-first game companion for ATM10 with a production-ready operator loop:

* Phase A: vision loop (screenshot -> VLM interface -> structured output + artifacts).
* Phase B: memory (retrieval + KAG + citations + guardrails).
* Phase C: voice (active ASR path + resilient TTS service/fallback).
* Phase D: operator control plane (Streamlit) on top of a unified local API.
* Automation: safe assistive path, dry-run by default, no real input events by default.

## Constraints

* OS/Runtime: Windows 11 + PowerShell 7 (first-class).
* Dev style: small, reviewable diffs + reproducible commands + tests/smoke.
* Paths/files: `pathlib`, no hardcoded machine-specific paths.
* Data hygiene: do not commit models/dumps/artifacts/secrets.
* Architecture hygiene: record important policy/architecture decisions in `docs/DECISIONS.md`.
* Runtime policy: `OpenVINO-first`.
* WIP limit (execution): maximum 3 active tasks at a time.

## Milestone Map

### Completed

* M0: Instance discovery + repo hygiene.
* M1: Phase A vision loop baseline.
* M2: Retrieval baseline + benchmark + profile defaults.
* M3: Voice runtime operational path (active ASR + archived policy).
* M3.1: OpenVINO rollout (text-core + retrieval profile).
* M4: HUD baselines (OCR + mod-hook ingest).
* M5: KAG baseline + Neo4j path + nightly guardrail + trend/severity policy.
* M6.0: Automation safe scaffold (dry-run only) + CI contract checks.
* M6.1-M6.19: Intent-chain contract hardening (trace/intent correlation, strict CI checks, rollout checklist).
* M8.0: Streamlit IA spec (`docs/STREAMLIT_IA_V0.md`) as the decision-complete source of truth.
* M8.1: Streamlit operator panel v0 core + no-crash smoke gate + CI summary/artifact wiring.

### Active Goals

#### G1 — M7 Combo A Service Foundation

Goal:

* Move the current script-per-task baseline to a unified local gateway without losing reproducibility.

Definition of Done:

* There is a FastAPI gateway as a single entrypoint for health, retrieval, KAG query, and automation dry-run orchestration.
* There is a stable artifact contract for gateway runs (request/response + status + links to child artifacts).
* There are at least 2 gateway-path smoke checks in CI (without unstable external dependencies).

Open tasks:

* Harden policy around gateway artifacts/errors (`retention`, rotation policy, redaction checklist for error logs).
* Lock a unified startup sequence (gateway HTTP + existing runnable services) in the runbook with a minimal operator profile.

#### G2 — M8 Streamlit Operator Panel (Combo A UI)

Goal:

* Provide an operator web UI for day-to-day local stack control and quick diagnostics.

Definition of Done:

* There is a runnable Streamlit app with at least 4 working areas:
  * stack health,
  * run explorer (`runs/<timestamp>/...`),
  * latest metrics (smoke/guardrail snapshots),
  * safe action triggers (smoke/dry-run only).
* The UI works locally on Windows 11 and does not require cloud/deploy infrastructure.
* UI actions leave traceable artifacts/log entries.

Open tasks:

* Preserve no-drift policy for panel contracts (`history filters`, `safe action audit trail`, `compact mobile baseline`) through future UX changes.

#### G3 — M6.1 Automation Safe Loop (ongoing)

Goal:

* Maintain the safe intent -> plan -> dry-run loop as a required automation layer.

Definition of Done:

* Every new `intent_type` follows policy `M6.19` (fixture + smoke + strict contract-check + summary/artifact wiring + regression test).
* Contract `automation_plan_v1` remains backward-compatible and traceable.

Open tasks:

* Apply checklist `M6.19` whenever intent templates are expanded.

#### G4 — KAG Quality/Latency Guardrail

Goal:

* Keep a stable quality/latency baseline on sample+hard sets without silent regressions.

Definition of Done:

* Nightly trend snapshot reliably reflects rolling-baseline status (`mrr`, `latency_p95`, severity).
* Retrieval/KAG changes pass sample/hard profiles without violating agreed thresholds.

Open tasks:

* Re-evaluate readiness for switching `critical_policy=fail_nightly` (baseline is currently `signal_only`).
* Periodically recalibrate latency severity thresholds against current noise floor.

#### G5 — CI Smoke Expansion & Contract Uniformity

Goal:

* Expand coverage of new runnable entrypoints without increasing flaky risk.

Definition of Done:

* Every new smoke entrypoint has a machine-readable summary and a stable CI step.
* Runbook and Decisions stay synchronized with actual CI contracts.

Open tasks:

* Preserve a unified summary-contract approach for core smoke and automation smoke.
* Maintain the unified runbook-link helper (`scripts/build_runbook_link.py`) in CI summaries.

## Roadmap Horizons

### 0-30 days

* Move `gateway_sla_summary_v1` from the signal-only baseline to a managed tightening plan (`conservative -> moderate`) based on historical data.
* Extend the Streamlit post-`M8.1` UX/operability layer with the next operator scenarios on top of already implemented `history filters` / `audit trail` / `compact mobile baseline`.

### 30-60 days

* Introduce a default hybrid query planner (`retrieval first + KAG expansion/citations`).
* Formalize SLA at the API/summary-contract level (voice, retrieval, KAG).
* Add a cross-service benchmark suite for Combo A.

### 60-90 days

* Prepare a pilot overlay/hotkey UX on top of the stabilized API.
* Evaluate moving part of automation from dry-run to supervised mode (only after security gates).
* Revisit archived R&D paths using the re-open criteria from `docs/ARCHIVED_TRACKS.md`.

## Archived Tracks

All archived/recoverable directions are tracked in:

* `docs/ARCHIVED_TRACKS.md`

Key archived directions:

* `Qwen3-ASR-0.6B` self-conversion pipeline (blocked upstream).
* `Qwen3-TTS` operational path (deactivated due to latency/SLA).

## Risks & Mitigations

* Risk: scope creep (simultaneous growth of voice + KAG + gateway + UI).
  Mitigation: WIP-limit=3 + milestone gates + explicit Now/Next/Blocked in `TODO.md`.

* Risk: drift between documented policy and actual runtime.
  Mitigation: synchronize `PLANS` + `RUNBOOK` + `DECISIONS` on every milestone update.

* Risk: security gaps in local services while expanding API/UI.
  Mitigation: sandboxed paths, sanitized errors, request limits, dry-run by default.

* Risk: disk/RAM pressure from the model zoo.
  Mitigation: OpenVINO pre-converted models, INT4/INT8 priority, controlled cache lifecycle.
