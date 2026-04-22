# ROADMAP.md — atm10-agent

Public roadmap for `atm10-agent`.

This document is the public planning surface of the repository. It describes direction, milestones, horizons, and high-level risks without exposing maintainer-local execution notes.

## Strategic Baseline

Selected strategic baseline:

* Production baseline: **Combo A**.
* Operator surface: **Streamlit** operator panel + CLI fallback.
* Agent-core path: FastAPI gateway + workers + Qdrant + Neo4j + file artifacts (`runs/...`).
* Runtime policy: current validated repo-host baseline is `OpenVINO-first` on this Intel machine, with explicit `CPU/GPU/NPU` placement and additive future host profiles for other hardware.
* Host-profile policy: Windows remains the first-class ATM10 product-edge path; `fedora_local_dev` is a preliminary Fedora-first development profile for portable-core and dev-companion stabilization, not a public product-edge support default.
* Model policy: pragmatic hybrid by task:
  * text/retrieval/rerank: Qwen3 stack,
  * vision active pilot path: Qwen2.5-VL-7B,
  * ASR active path: Whisper GenAI,
  * archived paths remain recoverable via explicit opt-in.
* Architecture posture: `ATM10-Agent` remains a companion with active operator interaction; current operator surfaces are the public entrypoint, while memory, evals, routing, and bounded worker/sub-agent roles stay under the hood inside the same local runtime boundary.

## North Star

Build a local-first ATM10 companion with a production-ready operator loop and an internal agent stack:

* Phase A: vision loop (screenshot -> VLM interface -> structured output + artifacts).
* Phase B: memory (retrieval + KAG + citations + guardrails).
* Phase C: voice (active ASR path + resilient TTS service/fallback).
* Phase D: operator control plane (Streamlit) on top of a unified local API.
* Automation: safe assistive path, dry-run by default, no real input events by default.
* Agent stack under the hood: memory, routing, evals, and bounded worker/sub-agent roles should remain explicit internal layers rather than being reduced to a UI-only shell.

## Completed Foundations

* M0: Instance discovery + repo hygiene.
* M1: Phase A vision loop baseline.
* M2: Retrieval baseline + benchmark + profile defaults.
* M3: Voice runtime operational path (active ASR + archived policy).
* M3.1: OpenVINO rollout (text-core + retrieval profile).
* M4: HUD baselines (OCR + mod-hook ingest).
* M5: KAG baseline + Neo4j path + nightly guardrail + trend/severity policy.
* M6.0-M6.19: Automation safe scaffold + intent-chain contract hardening.
* M8.0-M8.1: Streamlit IA spec and operator panel baseline with smoke coverage.
* M8.2: Observer pilot runtime slice (`F8` hotkey, local screen grounding/reply stack, additive operator snapshot and Streamlit surfaces).
* M8.3: Observer pilot acceptance/readiness layer (`pilot_runtime_readiness_v1`, additive operator snapshot + Streamlit surfaces, manual live-acceptance contract).
* M8.4: Operator recurrence recovery surface (`operator_context.returning`, bounded launcher/pilot return artifacts, gateway-safe-action recommendation posture, `Return / Recovery` inside the existing 4-tab IA).

## Active Public Themes

### G1 — Service Foundation

Goal:

* Move the script-per-task baseline to a unified local gateway without losing reproducibility.

Definition of Done:

* A FastAPI gateway acts as a single entrypoint for health, retrieval, KAG query, and automation dry-run orchestration.
* Gateway runs use a stable artifact contract.
* Core gateway paths have stable smoke coverage.

### G2 — Operator Panel and Gateway Governance

Goal:

* Keep the Streamlit operator panel and gateway governance surfaces reliable, diagnosable, and reviewable.

Definition of Done:

* Streamlit remains a stable operator surface for health, run exploration, metrics, and smoke-only safe actions.
* Gateway governance summaries remain machine-readable and publication-safe for nightly/operator workflows.
* Operator recurrence recovery stays additive through existing snapshot/gateway/Streamlit seams without creating a new endpoint, a fifth tab, or auto-executed actions.
* Current product-edge operator flows stay reproducible on Windows 11 + PowerShell 7.
* Future Fedora operator flows land as explicit host-profile/runbook paths instead of silently changing the Windows baseline.

### G3 — Automation Safe Loop

Goal:

* Maintain a traceable intent -> plan -> dry-run loop as a first-class automation layer.

Definition of Done:

* Every new `intent_type` follows checklist `M6.19`.
* `automation_plan_v1` remains backward-compatible and test-covered.
* Public rollout records exist for `open_quest_book`, `check_inventory_tool`, and `open_world_map`, proving the same intent -> plan -> dry-run contract is reusable under `M6.19`.

### G4 — KAG Quality / Latency Guardrail

Goal:

* Preserve a stable quality/latency baseline on sample+hard sets without silent regressions.

Definition of Done:

* Nightly trend snapshots reliably expose rolling-baseline status.
* Retrieval/KAG changes stay within agreed thresholds for quality and latency.

### G5 — CI Smoke Expansion and Contract Uniformity

Goal:

* Expand coverage of runnable entrypoints without introducing flaky policy or contract drift.

Definition of Done:

* New smoke entrypoints publish machine-readable summaries.
* CI, runbook, and decisions stay aligned.

### G6 — Host Profile Portability and Fedora Dev Companion

Goal:

* Introduce `fedora_local_dev` as an additive development profile that stabilizes portable core and operator-companion surfaces in the maintainer's Fedora-first workspace.

Definition of Done:

* Dependencies are split so Windows-only capture/input packages do not live in the portable core.
* Fedora dev-companion work can validate gateway/operator/dry-run surfaces without claiming full ATM10 Windows parity.
* Windows product-edge behavior remains intact, explicit, and separately validated.

## Roadmap Horizons

### 0-30 days

* Tighten `gateway_sla_summary_v1` from the signal-only baseline toward a managed stricter policy using accumulated history.
* Extend Streamlit operator UX with the next operator scenarios on top of the existing metrics/history/audit foundations.
* Harden recurrence recovery reason coverage around launcher and observer pilot evidence without widening the smoke-only action set.
* Land first-wave Fedora host-profile policy docs and split dependency files so portable core is no longer coupled to Windows-only capture packages.

### 30-60 days

* Use `pilot_runtime_readiness_v1` to harden real manual acceptance cycles for the observer pilot runtime.
* Evaluate when `combo_a` can move from additive parity profile to the operational default without weakening governance.
* Extend operator UX around pilot-specific troubleshooting and optional overlay/hotkey ergonomics.
* Fix the current Intel/OpenVINO host profile as the documented baseline while defining how future machine-specific runtime paths are introduced and validated.
* Land the first runnable `fedora_local_dev` companion path with explicit capability limits, artifacted smoke evidence, and no Windows product-edge regression.

### 60-90 days

* Evaluate moving some automation from dry-run to supervised mode after security gates are in place.
* Revisit archived R&D paths using the re-open criteria from `docs/ARCHIVED_TRACKS.md`.
* Continue tightening operator guidance and release criteria around the live observer loop.
* Pull compatible memory/evals/routing techniques from sibling repos into `ATM10-Agent` without breaking the single-repo local agent boundary or the validated `OpenVINO-first` host baseline.
* Evaluate whether Fedora companion-mode evidence is strong enough to promote from preliminary development profile to a named supported profile.

## Constraints and High-Level Risks

* Windows 11 + PowerShell 7 remains the first-class ATM10 product-edge environment.
* Fedora-first development is allowed as an explicit preliminary profile, but it is not a replacement support claim until docs, commands, and validation catch up.
* Reproducibility beats convenience: small diffs, runnable commands, and test coverage stay mandatory.
* Runtime remains `OpenVINO-first` on the current repo host until another host profile is explicitly validated and promoted; dependency and infrastructure sprawl stay constrained.
* Security posture remains conservative: dry-run by default, bounded payloads, sanitized errors, and minimal trusted surfaces.
* Risk of scope creep remains real; roadmap progress depends on milestone gates and disciplined prioritization.

## Archived / Recoverable Tracks

Archived directions and re-open criteria live in `docs/ARCHIVED_TRACKS.md`.
