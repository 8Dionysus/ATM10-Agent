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
- Hybrid planner baseline (`retrieval first + KAG expansion/citations`) plus additive `combo_a` profile (`qdrant + neo4j`) via CLI runner and gateway flow
- Cross-service benchmark suite with normalized `service_sla_summary_v1` artifacts for `voice_asr`, `voice_tts`, `retrieval`, and `kag`, with `baseline_first` as default and additive `combo_a` profile support
- Combo A nightly promotion surface via `combo_a_operating_cycle_v1`, keeping live `combo_a` parity governed on a separate nightly/manual path
- Gateway v1 local + HTTP paths, Streamlit operator panel, and the primary launcher `scripts/start_operator_product.py`
- Operator startup/snapshot readiness for external `Qdrant` + `Neo4j`, plus profile-aware `combo_a` smoke/safe-action surfaces
- Observer pilot runtime slice: local `F8` push-to-talk (`scripts/pilot_runtime_loop.py`) with Windows screen capture, `Whisper GenAI -> Qwen2.5-VL-7B -> hybrid_query(profile=combo_a) -> Qwen3-8B -> tts_runtime_service`, plus `pilot_runtime_status_v1` / `pilot_turn_v1` artifacts surfaced in the operator snapshot and Streamlit panel
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

Observer pilot example:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/start_operator_product.py --runs-dir runs --start-voice-runtime --start-tts-runtime --start-pilot-runtime --capture-monitor 0
```

For the local observer pilot, `--capture-monitor <index>` or `--capture-region x,y,w,h` is required for live screen grounding. The default pilot model stack is `Qwen2.5-VL-7B` on `GPU` plus `Qwen3-8B` on `NPU`.

### Gateway local contract runner

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/gateway_v1_local.py --request-json "<path-to-gateway-request.json>" --runs-dir runs\gateway-local
```

### Cross-service benchmark suite

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/cross_service_benchmark_suite.py --runs-dir runs\cross-service-suite --smoke-stub-voice-asr
```

This baseline-first suite runs `voice_asr -> voice_tts -> retrieval -> kag_file`, writes normalized `service_sla_summary.json` artifacts per service, and aggregates them into `cross_service_benchmark_suite.json`.

### Combo A parity profile

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="<set-local-neo4j-password>"
python scripts/cross_service_benchmark_suite.py --profile combo_a --runs-dir runs\nightly-combo-a-cross-service-suite --summary-json runs\nightly-combo-a-cross-service-suite\cross_service_benchmark_suite.json --voice-service-url http://127.0.0.1:8765 --tts-service-url http://127.0.0.1:8780 --qdrant-url http://127.0.0.1:6333 --neo4j-url http://127.0.0.1:7474 --neo4j-database neo4j --neo4j-user neo4j
```

`combo_a` stays additive: baseline remains the default, while `combo_a` switches retrieval to `Qdrant`, KAG to `Neo4j`, and the suite child order to `voice_asr -> voice_tts -> retrieval -> kag_neo4j`.

### Combo A operating cycle

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/run_combo_a_operating_cycle.py --runs-dir runs --policy report_only --summary-json runs\nightly-combo-a-operating-cycle\operating_cycle_summary.json --summary-md runs\nightly-combo-a-operating-cycle\summary.md
```

This evaluates the latest live `combo_a` artifacts and writes the canonical nightly decision surface with `effective_policy`, `promotion_state`, `blocking_reason_codes`, and `next_review_at_utc`.

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

# Export profile (isolated from the active LLM stack)
pip install -r requirements-export.txt

# Dependency audit
pip install -r requirements-audit.txt
python scripts/dependency_audit.py --runs-dir runs --policy report_only --with-security-scan true --security-requirements-files requirements.txt requirements-voice.txt requirements-llm.txt requirements-dev.txt
```

`requirements-export.txt` intentionally carries its own `torch`/`transformers`/`optimum*` window so the optional export toolchain can live in a separate environment without inheriting the active runtime LLM profile.

Default dependency audit still inspects all declared requirement profiles for inventory/findings, but the fail/report security scan itself is scoped to the active runtime/dev profiles. Audit the optional export toolchain explicitly with `--security-requirements-files requirements-export.txt` when you need that surface.

## Repo map

- `scripts/` - runnable entrypoints and operator tooling
- `src/agent_core/` - shared core runtime pieces
- `src/rag/` - retrieval stack
- `src/kag/` - graph and KAG stack
- `src/hybrid/` - hybrid planner merge/orchestration layer
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
- `docs/QWEN3_MODEL_STACK.md` - local OpenVINO model-stack posture (file name retained for continuity)

## License

Released under the [MIT License](LICENSE).
