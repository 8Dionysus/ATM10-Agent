# ROADMAP.md — atm10-agent

Public roadmap for `atm10-agent`.

This document is the public planning surface of the repository. It describes direction, milestones, horizons, and high-level risks without exposing maintainer-local execution notes.

## Strategic Baseline

Selected strategic baseline:

* Production baseline: **Combo A**.
* Frontend path: **Streamlit** operator panel + CLI fallback.
* Backend path: FastAPI gateway + workers + Qdrant + Neo4j + file artifacts (`runs/...`).
* Runtime policy: `OpenVINO-first` with `CPU/GPU/NPU` fallback.
* Model policy: pragmatic hybrid by task:
  * text/retrieval/rerank: Qwen3 stack,
  * vision active pilot path: Qwen2.5-VL-7B,
  * ASR active path: Whisper GenAI,
  * archived paths remain recoverable via explicit opt-in.

## North Star

Build a local-first game companion for ATM10 with a production-ready operator loop:

* Phase A: vision loop (screenshot -> VLM interface -> structured output + artifacts).
* Phase B: memory (retrieval + KAG + citations + guardrails).
* Phase C: voice (active ASR path + resilient TTS service/fallback).
* Phase D: operator control plane (Streamlit) on top of a unified local API.
* Automation: safe assistive path, dry-run by default, no real input events by default.

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
* Operator flows stay reproducible on Windows 11 + PowerShell 7.

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

## Roadmap Horizons

### 0-30 days

* Tighten `gateway_sla_summary_v1` from the signal-only baseline toward a managed stricter policy using accumulated history.
* Extend Streamlit operator UX with the next operator scenarios on top of the existing metrics/history/audit foundations.

### 30-60 days

* Introduce a default hybrid query planner (`retrieval first + KAG expansion/citations`).
* Formalize SLA at the API/summary-contract level across voice, retrieval, and KAG.
* Add a cross-service benchmark suite for Combo A.

### 60-90 days

* Complete live-readiness/manual acceptance for the observer pilot runtime and tighten optional overlay/hotkey UX on top of the stabilized local API.
* Evaluate moving some automation from dry-run to supervised mode after security gates are in place.
* Revisit archived R&D paths using the re-open criteria from `docs/ARCHIVED_TRACKS.md`.

## Constraints and High-Level Risks

* Windows 11 + PowerShell 7 is the first-class environment.
* Reproducibility beats convenience: small diffs, runnable commands, and test coverage stay mandatory.
* Runtime remains `OpenVINO-first`; dependency and infrastructure sprawl stay constrained.
* Security posture remains conservative: dry-run by default, bounded payloads, sanitized errors, and minimal trusted surfaces.
* Risk of scope creep remains real; roadmap progress depends on milestone gates and disciplined prioritization.

## Archived / Recoverable Tracks

Archived directions and re-open criteria live in `docs/ARCHIVED_TRACKS.md`.
