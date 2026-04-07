# ATM10-Agent

[![Pytest](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/pytest.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/pytest.yml)
[![Gateway SLA Readiness Nightly](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/gateway-sla-readiness-nightly.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/gateway-sla-readiness-nightly.yml)
[![KAG Neo4j Guardrail Nightly](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/kag-neo4j-guardrail-nightly.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/kag-neo4j-guardrail-nightly.yml)
[![Security Nightly](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/security-nightly.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/security-nightly.yml)

Local-first ATM10 companion with an active operator loop and an internal agent stack for Windows 11 + PowerShell 7.

`ATM10-Agent` combines perception (screen and HUD), memory (RAG + KAG), safe automation (dry-run by default), voice, routing and evals, and gateway-backed operator surfaces into one reproducible local companion stack.

## Start here

- current public status and active capabilities: `MANIFEST.md`
- direction, milestones, and risks: `ROADMAP.md`
- active runnable commands and operator paths: `docs/RUNBOOK.md`
- recurrence and operator recovery: `docs/RECURRENCE_OPERATOR_RECOVERY.md`
- validated host and runtime baseline: `docs/QWEN3_MODEL_STACK.md`
- public release cadence, supported profiles, and test tiers: `docs/PRODUCT_EDGE_POSTURE.md`
- first-wave antifragility contract surfaces: `docs/ANTIFRAGILITY_FIRST_WAVE.md`
- document roles and public-surface boundaries: `docs/SOURCE_OF_TRUTH.md`
- archived and recoverable reference tracks: `docs/ARCHIVED_TRACKS.md`

## Route by need

- operator command and recovery path: `docs/RUNBOOK.md` and `docs/RECURRENCE_OPERATOR_RECOVERY.md`
- public status, milestones, release cadence, test tiers, and supported profiles: `MANIFEST.md`, `ROADMAP.md`, and `docs/PRODUCT_EDGE_POSTURE.md`
- current hardening release reference: `docs/RELEASE_WAVE6.md`
- first-wave degraded hybrid-query receipts and companion contracts: `docs/ANTIFRAGILITY_FIRST_WAVE.md`, `schemas/stressor_receipt_v1.json`, and `schemas/adaptation_delta_v1.json`
- source-of-truth and ecosystem placement: `docs/SOURCE_OF_TRUTH.md` and `docs/ECOSYSTEM_CONTEXT.md`
- validated host/model baseline and UI pilot surfaces: `docs/QWEN3_MODEL_STACK.md` and `docs/STREAMLIT_IA_V0.md`
- operator return examples and archived reference tracks: `examples/gateway_operator_return_event.example.json`, `examples/gateway_operator_return_summary.example.json`, `examples/operator_return_reason_catalog.example.json`, and `docs/ARCHIVED_TRACKS.md`

## Current highlights

- Gateway + Streamlit operator surfaces, pilot runtime, and the primary local launcher remain the active public operator entrypoints.
- Retrieval, KAG, hybrid grounding, and cross-service benchmark and governance flows remain part of the current public stack.
- The hybrid-query runner now exposes a first-wave source-owned `stressor_receipt_v1` when the run lands in bounded `planner_status=retrieval_only_fallback`, without widening runtime authority or adding auto-repair.
- Safe automation remains dry-run by default, with public `M6.19` rollout records for `open_quest_book`, `check_inventory_tool`, and `open_world_map`.
- The validated repo-host baseline is the Intel-machine `OpenVINO-first` path. Future host profiles stay additive instead of silently replacing it.

## Public document topology

- `README.md` stays the short human entrypoint
- `MANIFEST.md` carries current public status
- `ROADMAP.md` carries direction and milestone posture
- `docs/PRODUCT_EDGE_POSTURE.md` carries public release cadence, supported profiles, CI/test tiers, and the `ATM10-Agent` x `abyss-stack` boundary
- `docs/RUNBOOK.md` carries runnable commands and setup paths
- `docs/SOURCE_OF_TRUTH.md` defines document roles and boundary discipline

## Project links

- `CONTRIBUTING.md`
- `SECURITY.md`
- `CODE_OF_CONDUCT.md`
- `LICENSE`
