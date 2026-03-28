# ATM10-Agent

[![Pytest](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/pytest.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/pytest.yml)
[![Gateway SLA Readiness Nightly](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/gateway-sla-readiness-nightly.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/gateway-sla-readiness-nightly.yml)
[![KAG Neo4j Guardrail Nightly](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/kag-neo4j-guardrail-nightly.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/kag-neo4j-guardrail-nightly.yml)
[![Security Nightly](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/security-nightly.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/security-nightly.yml)

Local-first ATM10 companion with an active operator loop and an internal agent stack for Windows 11 + PowerShell 7.

`ATM10-Agent` combines perception (screen/HUD), memory (RAG + KAG), safe automation (dry-run by default), voice, routing/evals, and gateway-backed operator surfaces into one reproducible local companion stack.

## Current Highlights

- Gateway + Streamlit operator surfaces, pilot runtime, and the primary local launcher remain the active public operator entrypoints.
- Retrieval, KAG, hybrid grounding, and cross-service benchmark/governance flows remain part of the current public stack.
- Safe automation remains dry-run by default, with public `M6.19` rollout records for `open_quest_book`, `check_inventory_tool`, and `open_world_map`.
- The validated repo-host baseline is the Intel-machine `OpenVINO-first` path; future host profiles stay additive instead of silently replacing it.

## Canonical Docs

- [`MANIFEST.md`](MANIFEST.md) - current public status and active capabilities
- [`ROADMAP.md`](ROADMAP.md) - direction, milestones, horizons, and risks
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) - active runnable commands and operational paths
- [`docs/RECURRENCE_OPERATOR_RECOVERY.md`](docs/RECURRENCE_OPERATOR_RECOVERY.md) - operator-facing recurrence and recovery surface
- [`docs/QWEN3_MODEL_STACK.md`](docs/QWEN3_MODEL_STACK.md) - host/runtime posture and validated model-stack baseline
- [`docs/ARCHIVED_TRACKS.md`](docs/ARCHIVED_TRACKS.md) - archived, recoverable, and historical reference tracks
- [`docs/SOURCE_OF_TRUTH.md`](docs/SOURCE_OF_TRUTH.md) - document roles and public-surface boundaries

## Project Links

- [`CONTRIBUTING.md`](CONTRIBUTING.md) - contribution guidance
- [`SECURITY.md`](SECURITY.md) - private reporting and public-safe disclosure rules
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) - community expectations
- [`LICENSE`](LICENSE) - Apache License 2.0
