# ATM10-Agent

[![Pytest](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/pytest.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/pytest.yml)
[![Gateway SLA Readiness Nightly](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/gateway-sla-readiness-nightly.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/gateway-sla-readiness-nightly.yml)
[![KAG Neo4j Guardrail Nightly](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/kag-neo4j-guardrail-nightly.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/kag-neo4j-guardrail-nightly.yml)
[![Security Nightly](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/security-nightly.yml/badge.svg)](https://github.com/8Dionysus/ATM10-Agent/actions/workflows/security-nightly.yml)

Local-first game companion for ATM10 on Windows 11 + PowerShell 7.

`ATM10-Agent` combines perception (screen/HUD), memory (RAG + KAG), safe automation (dry-run by default), voice, and a gateway-backed operator panel into one reproducible local stack.

## What is working now

- Phase A vision smoke path with artifacted runs via `scripts/phase_a_smoke.py`
- Retrieval and evaluation loops for local docs and fixtures
- KAG file baseline plus Neo4j path, with nightly guardrail and trend snapshots
- Gateway v1 local + HTTP paths, Streamlit operator panel, and the primary launcher `scripts/start_operator_product.py`
- Safe automation intent -> plan -> dry-run chain with public rollout records under `M6.19` for `open_quest_book`, `check_inventory_tool`, and `open_world_map`

For the full current public snapshot, use `MANIFEST.md`. For runnable command depth, use `docs/RUNBOOK.md`.

## Safety posture

- Local-first, Windows-first workflow
- Dry-run by default for automation
- No real input events by default
- Public docs are sanitized and use placeholders instead of workstation-specific paths or secrets
- Optional service auth uses env/config patterns such as `ATM10_SERVICE_TOKEN`, not hardcoded tokens

## Quickstart

```powershell
cd <repo-root>
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
python -m pytest
python scripts/phase_a_smoke.py
```

Expected result:

- tests pass
- a timestamped run directory is created under `runs/`
- smoke artifacts such as `run.json` and `response.json` are written

## Common launch paths

### Primary operator product

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/start_operator_product.py --runs-dir runs
```

This is the canonical local launch path for `gateway + Streamlit`.

### Gateway local contract runner

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/gateway_v1_local.py --request-json "<path-to-gateway-request.json>" --runs-dir runs\gateway-local
```

### Optional service auth hardening

```powershell
$env:ATM10_SERVICE_TOKEN="<set-local-service-token>"
python scripts/gateway_v1_http_service.py --host 127.0.0.1 --port 8770 --runs-dir runs\gateway-http
```

Loopback mode keeps the local developer path simple. Non-loopback binds should use `ATM10_SERVICE_TOKEN` or `--service-token`.

## Dependency profiles

```powershell
# Base runtime + tests
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Voice profile
pip install -r requirements-voice.txt

# LLM profile
pip install -r requirements-llm.txt

# Export profile
pip install -r requirements-export.txt

# Dependency audit
pip install -r requirements-audit.txt
python scripts/dependency_audit.py --runs-dir runs --policy report_only --with-security-scan true
```

## Repo map

- `scripts/` - runnable entrypoints and operator tooling
- `src/agent_core/` - shared core runtime pieces
- `src/rag/` - retrieval stack
- `src/kag/` - graph and KAG stack
- `tests/` - regression, smoke, workflow, and contract coverage
- `docs/` - runbook, roadmap, source-of-truth, archived tracks, release notes

## Canonical documents

`README.md` stays intentionally short. These documents carry the detailed contract:

- `MANIFEST.md` - current public status and active capabilities
- `ROADMAP.md` - direction, milestones, horizons, and risks
- `docs/RUNBOOK.md` - runnable commands and operational profiles
- `docs/SOURCE_OF_TRUTH.md` - document roles and update rules
- `docs/ARCHIVED_TRACKS.md` - recoverable paths and re-open criteria
- `docs/RELEASE_WAVE6.md` - security hardening reference
- `docs/QWEN3_MODEL_STACK.md` - active and archived model-stack posture

## License

Released under the [MIT License](LICENSE).
