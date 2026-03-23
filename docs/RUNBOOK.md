# RUNBOOK

Path placeholders in this document:

* Use `<repo-root>` for your local clone path.
* Use `<path-to-...>` placeholders for local files on your workstation.
* Use env vars or local secret managers for tokens/passwords; do not paste reusable literals into commands.

## M0: Instance discovery

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/discover_instance.py
```

Expected result:

* `runs/<timestamp>/instance_paths.json` is created.
* A summary of the found paths and marker folders is printed to the console.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Dependency Profiles

```powershell
# Base runtime + tests
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt

# Optional profiles
python -m pip install -r requirements-voice.txt
python -m pip install -r requirements-llm.txt
python -m pip install -r requirements-export.txt

# Dependency audit
python -m pip install -r requirements-audit.txt
python scripts/dependency_audit.py --runs-dir runs --policy report_only --with-security-scan true --security-requirements-files requirements.txt requirements-voice.txt requirements-llm.txt requirements-dev.txt

# Nightly/security gate profile
python scripts/dependency_audit.py --runs-dir runs/nightly-security-audit --policy fail_on_critical --with-security-scan true --security-requirements-files requirements.txt requirements-voice.txt requirements-llm.txt requirements-dev.txt
```

CI note:

* PR pipeline keeps `report_only` dependency audit signal.
* Nightly security workflow (`.github/workflows/security-nightly.yml`) runs `fail_on_critical` policy.
* Inventory/findings still inspect all declared requirement profiles.
* `requirements-export.txt` is intentionally isolated from `requirements-llm.txt`; it carries its own `torch`/`transformers`/`optimum*` constraints for a separate export-only environment.
* The fail/report security scan scope covers active runtime/dev profiles by default; audit `requirements-export.txt` explicitly when you need the optional export toolchain surface.

## CI smoke (runnable scripts)

```powershell
python scripts/phase_a_smoke.py --vlm-provider stub --runs-dir runs/ci-smoke-phase-a
python scripts/collect_smoke_run_summary.py --runs-dir runs/ci-smoke-phase-a --expected-mode phase_a_smoke --summary-json runs/ci-smoke-phase-a/smoke_summary.json
python scripts/retrieve_demo.py --in tests/fixtures/retrieval_docs_sample.jsonl --query "mekanism steel" --topk 3 --candidate-k 10 --reranker none --runs-dir runs/ci-smoke-retrieve
python scripts/collect_smoke_run_summary.py --runs-dir runs/ci-smoke-retrieve --expected-mode retrieve_demo --summary-json runs/ci-smoke-retrieve/smoke_summary.json
python scripts/eval_retrieval.py --docs tests/fixtures/retrieval_docs_sample.jsonl --eval tests/fixtures/retrieval_eval_sample.jsonl --topk 3 --candidate-k 10 --reranker none --runs-dir runs/ci-smoke-eval
python scripts/collect_smoke_run_summary.py --runs-dir runs/ci-smoke-eval --expected-mode eval_retrieval --summary-json runs/ci-smoke-eval/smoke_summary.json
python scripts/automation_dry_run.py --plan-json tests/fixtures/automation_plan_quest_book.json --runs-dir runs/ci-smoke-automation-dry-run
python scripts/check_automation_smoke_contract.py --mode dry_run --runs-dir runs/ci-smoke-automation-dry-run --min-action-count 3 --min-step-count 4 --summary-json runs/ci-smoke-automation-dry-run/contract_summary.json
python scripts/automation_intent_chain_smoke.py --intent-json tests/fixtures/intent_open_quest_book.json --runs-dir runs/ci-smoke-automation-chain
python scripts/check_automation_smoke_contract.py --mode intent_chain --runs-dir runs/ci-smoke-automation-chain --min-action-count 3 --min-step-count 4 --expected-intent-type open_quest_book --require-trace-id --require-intent-id --summary-json runs/ci-smoke-automation-chain/contract_summary.json
python scripts/automation_intent_chain_smoke.py --intent-json tests/fixtures/intent_check_inventory_tool.json --runs-dir runs/ci-smoke-automation-chain-inventory
python scripts/check_automation_smoke_contract.py --mode intent_chain --runs-dir runs/ci-smoke-automation-chain-inventory --min-action-count 3 --min-step-count 4 --expected-intent-type check_inventory_tool --require-trace-id --require-intent-id --summary-json runs/ci-smoke-automation-chain-inventory/contract_summary.json
python scripts/automation_intent_chain_smoke.py --intent-json tests/fixtures/intent_open_world_map.json --runs-dir runs/ci-smoke-automation-chain-open-world-map
python scripts/check_automation_smoke_contract.py --mode intent_chain --runs-dir runs/ci-smoke-automation-chain-open-world-map --min-action-count 3 --min-step-count 4 --expected-intent-type open_world_map --require-trace-id --require-intent-id --summary-json runs/ci-smoke-automation-chain-open-world-map/contract_summary.json
python scripts/gateway_v1_smoke.py --scenario core --runs-dir runs/ci-smoke-gateway-core --summary-json runs/ci-smoke-gateway-core/gateway_smoke_summary.json
python scripts/gateway_v1_smoke.py --scenario hybrid --runs-dir runs/ci-smoke-gateway-hybrid --summary-json runs/ci-smoke-gateway-hybrid/gateway_smoke_summary.json
python scripts/gateway_v1_smoke.py --scenario automation --runs-dir runs/ci-smoke-gateway-automation --summary-json runs/ci-smoke-gateway-automation/gateway_smoke_summary.json
python scripts/gateway_v1_http_smoke.py --scenario core --runs-dir runs/ci-smoke-gateway-http-core --summary-json runs/ci-smoke-gateway-http-core/gateway_http_smoke_summary.json
python scripts/gateway_v1_http_smoke.py --scenario hybrid --runs-dir runs/ci-smoke-gateway-http-hybrid --summary-json runs/ci-smoke-gateway-http-hybrid/gateway_http_smoke_summary.json
python scripts/gateway_v1_http_smoke.py --scenario automation --runs-dir runs/ci-smoke-gateway-http-automation --summary-json runs/ci-smoke-gateway-http-automation/gateway_http_smoke_summary.json
python scripts/check_gateway_sla.py --http-summary-json runs/ci-smoke-gateway-http-core/gateway_http_smoke_summary.json --summary-json runs/ci-smoke-gateway-sla/gateway_sla_summary.json --profile conservative --policy signal_only --runs-dir runs/ci-smoke-gateway-sla
python scripts/gateway_sla_trend_snapshot.py --sla-runs-dir runs/ci-smoke-gateway-sla --history-limit 10 --baseline-window 5 --critical-policy signal_only --runs-dir runs/ci-smoke-gateway-sla-trend
python scripts/cross_service_benchmark_suite.py --runs-dir runs/ci-smoke-cross-service-suite --summary-json runs/ci-smoke-cross-service-suite/cross_service_benchmark_suite.json --smoke-stub-voice-asr
python scripts/streamlit_operator_panel_smoke.py --panel-runs-dir runs --runs-dir runs/ci-smoke-streamlit --summary-json runs/ci-smoke-streamlit/streamlit_smoke_summary.json --gateway-url http://127.0.0.1:8770 --startup-timeout-sec 45 --viewport-width 390 --viewport-height 844 --compact-breakpoint-px 768
```

Expected result:

* Machine-readable summaries are created for core smoke steps:
  * `runs/ci-smoke-phase-a/smoke_summary.json`
  * `runs/ci-smoke-retrieve/smoke_summary.json`
  * `runs/ci-smoke-eval/smoke_summary.json`
* For automation smoke steps, contract summaries are created:
  * `runs/ci-smoke-automation-dry-run/contract_summary.json`
  * `runs/ci-smoke-automation-chain/contract_summary.json`
  * `runs/ci-smoke-automation-chain-inventory/contract_summary.json`
  * `runs/ci-smoke-automation-chain-open-world-map/contract_summary.json`
* Machine-readable summaries are created for gateway smoke steps:
  * `runs/ci-smoke-gateway-core/gateway_smoke_summary.json`
  * `runs/ci-smoke-gateway-hybrid/gateway_smoke_summary.json`
  * `runs/ci-smoke-gateway-automation/gateway_smoke_summary.json`
* For gateway HTTP smoke steps, machine-readable summaries are created:
  * `runs/ci-smoke-gateway-http-core/gateway_http_smoke_summary.json`
  * `runs/ci-smoke-gateway-http-hybrid/gateway_http_smoke_summary.json`
  * `runs/ci-smoke-gateway-http-automation/gateway_http_smoke_summary.json`
* For gateway SLA check, a machine-readable summary is created:
  * `runs/ci-smoke-gateway-sla/gateway_sla_summary.json`
* Machine-readable artifacts are created for gateway SLA trend snapshot:
  * `runs/ci-smoke-gateway-sla-trend/<timestamp>-gateway-sla-trend/gateway_sla_trend_snapshot.json`
  * `runs/ci-smoke-gateway-sla-trend/<timestamp>-gateway-sla-trend/summary.md`
* For the cross-service suite, machine-readable benchmark artifacts are created:
  * `runs/ci-smoke-cross-service-suite/cross_service_benchmark_suite.json`
  * `runs/ci-smoke-cross-service-suite/<timestamp>-cross-service-suite/summary.md`
  * `runs/ci-smoke-cross-service-suite/<timestamp>-cross-service-suite/child_runs/<service>/<timestamp>-.../service_sla_summary.json`
* For streamlit smoke, a machine-readable summary is created:
  * `runs/ci-smoke-streamlit/streamlit_smoke_summary.json`

## M7.0: Gateway v1 local contract runner

The local gateway path fixes the request/response contract without HTTP transport and without new dependencies.

### Single request (CLI)

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/gateway_v1_local.py --request-json "<path-to-gateway-request.json>" --runs-dir runs\gateway-local
```

Example `gateway_request.json`:

```json
{
  "schema_version": "gateway_request_v1",
  "operation": "retrieval_query",
  "payload": {
    "query": "mekanism steel",
    "docs_path": "tests/fixtures/retrieval_docs_sample.jsonl",
    "topk": 3,
    "candidate_k": 10,
    "reranker": "none"
  }
}
```

Expected result:

* `runs/<timestamp>-gateway-v1/` is created.
* Inside there are `request.json`, `run.json`, `response.json`, `child_runs/`.
* `request.json` is saved in redacted form (without plaintext secrets).
* `request_redaction` (`applied`, `fields_redacted`, checklist version) is published in `run.json`.
* `response.json.schema_version = gateway_response_v1`.
* `health.result.supported_operations` includes additive `hybrid_query`.
* `health.result.supported_profiles` includes `baseline_first` and additive `combo_a`.
* For `retrieval_query` + `reranker=qwen3` `payload.reranker_model` is limited by allowlist:
  * `Qwen/Qwen3-Reranker-0.6B`
  * `OpenVINO/Qwen3-Reranker-0.6B-fp16-ov`
  * override only via `ATM10_ALLOW_UNTRUSTED_RERANKER_MODEL=true` (trusted-only).

### Hybrid planner runner

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/hybrid_query_demo.py --docs tests/fixtures/retrieval_docs_sample.jsonl --query "steel tools" --topk 5 --candidate-k 10 --reranker none --runs-dir runs\hybrid-query
```

Expected result:

* `runs/<timestamp>-hybrid-query/` is created.
* Inside there are `run.json`, `hybrid_query_results.json`, and `kag_graph.json` when the KAG stage completes.
* `hybrid_query_results.json` contains `planner_mode`, `planner_status`, `degraded`, `retrieval_results`, `kag_results`, `merged_results`, `warnings`, and `paths`.
* If retrieval succeeds but the KAG stage fails or returns no expansion rows, the run still ends with `status=ok` and `planner_status=retrieval_only_fallback`.

Combo A profile example:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="<set-local-neo4j-password>"
python scripts/hybrid_query_demo.py --profile combo_a --query "steel tools" --topk 5 --candidate-k 10 --reranker none --collection atm10_combo_a_fixture_manual --host 127.0.0.1 --port 6333 --neo4j-url http://127.0.0.1:7474 --neo4j-database neo4j --neo4j-user neo4j --neo4j-dataset-tag atm10_combo_a_fixture_manual --runs-dir runs\hybrid-query-combo-a
```

For `profile=combo_a`, `docs_path` is optional when `retrieval_backend=qdrant` and `kag_backend=neo4j`.

### Cross-service benchmark suite

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/cross_service_benchmark_suite.py --runs-dir runs\cross-service-suite --summary-json runs\cross-service-suite\cross_service_benchmark_suite.json --smoke-stub-voice-asr
$env:NEO4J_PASSWORD="<set-local-neo4j-password>"
python scripts/cross_service_benchmark_suite.py --profile combo_a --runs-dir runs\nightly-combo-a-cross-service-suite --summary-json runs\nightly-combo-a-cross-service-suite\cross_service_benchmark_suite.json --voice-service-url http://127.0.0.1:8765 --tts-service-url http://127.0.0.1:8780 --qdrant-url http://127.0.0.1:6333 --neo4j-url http://127.0.0.1:7474 --neo4j-database neo4j --neo4j-user neo4j
```

Expected result:

* `runs/<timestamp>-cross-service-suite/` is created.
* Inside there are `run.json`, `cross_service_benchmark_suite.json`, `summary.md`, and `child_runs/`.
* Child runs execute in canonical order: `voice_asr -> voice_tts -> retrieval -> kag_file`.
* Each child run writes a normalized `service_sla_summary.json` next to its native artifacts.
* `cross_service_benchmark_suite.json` contains `schema_version = cross_service_benchmark_suite_v1`, `services`, `summary_matrix`, `degraded_services`, and `paths.child_runs`.
* `--smoke-stub-voice-asr` keeps the suite reproducible in CI and local smoke paths without a live ASR backend.
* For `profile=combo_a`, the child order becomes `voice_asr -> voice_tts -> retrieval -> kag_neo4j`, retrieval uses `Qdrant`, KAG uses `Neo4j`, and the suite writes `paths.combo_a_seed_run_dir` for the isolated fixture seeding step.
* For `profile=combo_a`, the live nightly workflow can additionally aggregate the suite output into `combo_a_operating_cycle_v1` for nightly-only promotion decisions.

### Gateway smoke scenarios

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/gateway_v1_smoke.py --scenario core --runs-dir runs\ci-smoke-gateway-core --summary-json runs\ci-smoke-gateway-core\gateway_smoke_summary.json
python scripts/gateway_v1_smoke.py --scenario hybrid --runs-dir runs\ci-smoke-gateway-hybrid --summary-json runs\ci-smoke-gateway-hybrid\gateway_smoke_summary.json
python scripts/gateway_v1_smoke.py --scenario automation --runs-dir runs\ci-smoke-gateway-automation --summary-json runs\ci-smoke-gateway-automation\gateway_smoke_summary.json
$env:NEO4J_PASSWORD="<set-local-neo4j-password>"
python scripts/gateway_v1_smoke.py --scenario combo_a --runs-dir runs\ci-smoke-gateway-combo-a --summary-json runs\ci-smoke-gateway-combo-a\gateway_smoke_summary.json --qdrant-url http://127.0.0.1:6333 --neo4j-url http://127.0.0.1:7474 --neo4j-database neo4j --neo4j-user neo4j
```

Expected result:

* The `core` script checks `health`, `retrieval_query`, `kag_query` (`backend=file`).
* The `hybrid` script checks additive `hybrid_query` (`retrieval first + file KAG expansion + RRF merge`).
* The `automation` script checks `automation_dry_run` through fixture.
* The `combo_a` script seeds isolated fixture data into `Qdrant` + `Neo4j`, then checks `health`, `retrieval_query(qdrant)`, `kag_query(neo4j)`, and `hybrid_query(profile=combo_a)`.
* `combo_a` smoke summaries additively publish `profile=combo_a` and `surface=local`.
* In each `--summary-json`, a `status=ok|error` is fixed; any `error` returns a non-zero exit code.

## M7.1/M7.2: Gateway v1 HTTP transport + hardening

The HTTP layer uses the same dispatcher `run_gateway_request`, so the body contract is the same as the CLI gateway.

### Service start (FastAPI)

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/gateway_v1_http_service.py --host 127.0.0.1 --port 8770 --runs-dir runs\gateway-http
```

Running with override policy (example):

```powershell
python scripts/gateway_v1_http_service.py --host 127.0.0.1 --port 8770 --runs-dir runs\gateway-http --max-request-bytes 262144 --max-json-depth 8 --max-string-length 8192 --max-array-items 256 --max-object-keys 256 --operation-timeout-sec 15.0 --error-log-max-bytes 1048576 --error-log-max-files 5 --artifact-retention-days 14 --enable-error-redaction true
```

Optional auth-token hardening:

```powershell
# Prefer env-driven local auth setup in public examples
$env:ATM10_SERVICE_TOKEN="<set-local-service-token>"
python scripts/gateway_v1_http_service.py --host 127.0.0.1 --port 8770 --runs-dir runs\gateway-http
```

Non-loopback bind policy:

* Loopback (`127.0.0.1`, `localhost`, `::1`) keeps backward-compatible no-token behavior.
* Non-loopback bind requires `--service-token` / `ATM10_SERVICE_TOKEN`.
* Use `--allow-insecure-no-token` only for explicit local-network testing.

Optional local API docs (debug only):

```powershell
python scripts/gateway_v1_http_service.py --host 127.0.0.1 --port 8770 --runs-dir runs\gateway-http --expose-openapi
```

Hardening defaults (`Balanced`):

* `max_request_body_bytes = 262144` (256 KB)
* `max_json_depth = 8`
* `max_string_length = 8192`
* `max_array_items = 256`
* `max_object_keys = 256`
* `operation_timeout_sec = 15.0`
* `error_log_max_bytes = 1048576` (1 MB)
* `error_log_max_files = 5`
* `artifact_retention_days = 14`
* `enable_error_redaction = true`

Transport health check:

```powershell
python -c "import requests; print(requests.get('http://127.0.0.1:8770/healthz', timeout=10).json())"
```

Expected transport health fields:

* `status = ok`
* `supported_operations` includes `health`, `retrieval_query`, `kag_query`, `hybrid_query`, `automation_dry_run`, `safe_action_smoke`
* `supported_profiles` includes `baseline_first`, `combo_a`
* `policy` reflects the effective HTTP hardening profile

Operator snapshot check:

```powershell
python -c "import requests; print(requests.get('http://127.0.0.1:8770/v1/operator/snapshot', timeout=10).json()['schema_version'])"
```

Optional downstream health aggregation for the operator product:

```powershell
python scripts/gateway_v1_http_service.py --host 127.0.0.1 --port 8770 --runs-dir runs\gateway-http --voice-service-url http://127.0.0.1:8765 --tts-service-url http://127.0.0.1:8780 --qdrant-url http://127.0.0.1:6333 --neo4j-url http://127.0.0.1:7474 --neo4j-database neo4j --neo4j-user neo4j --operator-health-timeout-sec 3.0
```

With external services configured, `/v1/operator/snapshot` additively returns `operator_context.profiles.supported_profiles`, `operator_context.profiles.combo_a`, compact `operator_context.triage`, probe rows for `qdrant` / `neo4j`, and pilot-facing `operator_context.pilot_runtime` / `operator_context.last_turn_summary` / `operator_context.pilot_readiness` when those artifacts exist.

Operator diagnostics surface (additive, schema-compatible):

* `operator_context.startup.diagnostics.overall_state = healthy|degraded|stopped|unknown|not_available`
* `operator_context.startup.diagnostics.primary_issue` uses deterministic priority:
  * launcher `error` field
  * failing `last_checkpoint`
  * failing service probe from `session_state`
* `operator_context.governance.diagnostics.top_blocker` is the first `blocking_reason_codes` item (or `none`)
* `operator_context.governance.diagnostics.next_safe_action` is the first recommended `action_key` (or `null`)
* `operator_context.triage.primary_surface` uses deterministic precedence: `startup > services > governance > combo_a > none`
* `operator_context.triage.primary_message` is the first short-form issue from the winning surface, while `next_step_code` / `next_step` stay additive UI-safe hints

### Gateway request over HTTP

```powershell
python -c "import requests; payload={'schema_version':'gateway_request_v1','operation':'health','payload':{}}; r=requests.post('http://127.0.0.1:8770/v1/gateway', json=payload, timeout=30); print(r.status_code); print(r.json())"
```

HTTP status mapping:

* `response.status=ok` -> `200`
* `error_code=unauthorized` -> `401`
* `error_code=invalid_request` -> `400`
* `error_code=payload_too_large|payload_limit_exceeded` -> `413`
* `error_code=operation_timeout` -> `504`
* `error_code=operation_failed|gateway_dispatch_failed|internal_error_sanitized` -> `500`

Sanitize policy:

* The client receives only a sanitized envelope (without traceback/internal details).
* When `service-token` is enabled, all HTTP endpoints require `X-ATM10-Token`.
* Non-loopback bind without a token is rejected unless `--allow-insecure-no-token` is passed explicitly.
* `/docs` and `/openapi.json` are disabled by default; use `--expose-openapi` only for local loopback debugging.
* Redaction checklist `gateway_error_redaction_v1` (key-based + text pattern masking) is applied before the error JSONL entry.
* The Error log is rotated according to limits (`gateway_http_errors.jsonl`, `gateway_http_errors.1.jsonl`, ...).
* At startup, a retention cleanup is performed:
  * `gateway_http_errors*.jsonl`
  * directories `runs/.../*-gateway-v1*` are older than retention window.
* Machine-readable metadata is added to each JSONL entry:
  * `redaction.checklist_version|applied|fields_redacted`
  * `retention_policy.artifact_retention_days|error_log_max_bytes|error_log_max_files`.

### HTTP smoke scenarios

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/gateway_v1_http_smoke.py --scenario core --runs-dir runs\ci-smoke-gateway-http-core --summary-json runs\ci-smoke-gateway-http-core\gateway_http_smoke_summary.json
python scripts/gateway_v1_http_smoke.py --scenario hybrid --runs-dir runs\ci-smoke-gateway-http-hybrid --summary-json runs\ci-smoke-gateway-http-hybrid\gateway_http_smoke_summary.json
python scripts/gateway_v1_http_smoke.py --scenario automation --runs-dir runs\ci-smoke-gateway-http-automation --summary-json runs\ci-smoke-gateway-http-automation\gateway_http_smoke_summary.json
$env:NEO4J_PASSWORD="<set-local-neo4j-password>"
python scripts/gateway_v1_http_smoke.py --scenario combo_a --runs-dir runs\ci-smoke-gateway-http-combo-a --summary-json runs\ci-smoke-gateway-http-combo-a\gateway_http_smoke_summary.json --qdrant-url http://127.0.0.1:6333 --neo4j-url http://127.0.0.1:7474 --neo4j-database neo4j --neo4j-user neo4j
```

Expected result:

* `core` contains operations `health`, `retrieval_query`, `kag_query(file)`.
* `hybrid` contains additive `hybrid_query`.
* `automation_dry_run` passes through `automation`.
* `combo_a` seeds isolated external fixture data and validates the same additive `combo_a` request set through HTTP transport.
* `combo_a` HTTP smoke summaries additively publish `profile=combo_a` and `surface=http`.
* Any error in the gateway body/HTTP status causes smoke `status=error` and non-zero exit code.

## M8.pre: Primary operator product startup profile

Canonical local operator launch path:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/start_operator_product.py --runs-dir runs
```

Optional runtime health wiring through the gateway operator snapshot:

```powershell
python scripts/start_operator_product.py --runs-dir runs --voice-runtime-url http://127.0.0.1:8765 --tts-runtime-url http://127.0.0.1:8780 --qdrant-url http://127.0.0.1:6333 --neo4j-url http://127.0.0.1:7474 --neo4j-database neo4j --neo4j-user neo4j
```

Optional managed local runtimes (launcher starts `voice_runtime_service` / `tts_runtime_service` / `pilot_runtime` itself):

```powershell
python scripts/start_operator_product.py --runs-dir runs --start-voice-runtime --start-tts-runtime
python scripts/start_operator_product.py --runs-dir runs --start-voice-runtime --start-tts-runtime --start-pilot-runtime --capture-monitor 0
python scripts/start_operator_product.py --runs-dir runs --start-voice-runtime --start-tts-runtime --start-pilot-runtime --capture-region 0,0,1920,1080
```

Expected result:

* A launcher run dir `runs/<timestamp>-start-operator-product/` is created.
* `startup_plan.json` stores the resolved canonical startup profile.
* `run.json` captures the canonical startup profile, effective runtime URLs, external service URLs, `managed_processes`, `external_services`, `session_state`, startup checkpoints, and artifact pointers.
* Gateway is considered ready only after `GET /v1/operator/snapshot` returns `status=ok`.
* Streamlit is started against that gateway URL as the primary operator cockpit.
* If managed runtimes are enabled, launcher waits for `GET /health` on those loopback services before starting the gateway.
* `gateway.log` and `streamlit.log` are written into the launcher run dir.
* If managed runtimes are enabled, `voice_runtime_service.log` / `tts_runtime_service.log` / `pilot_runtime.log` are also written into the launcher run dir.
* If `pilot_runtime` is enabled, the launcher also writes `artifact_roots.pilot_runtime_runs_dir` and the pilot process publishes `pilot_runtime_status_latest.json` under that root.
* The operator surface can read the latest launcher artifact back through the gateway/panel as startup-session context, including additive `combo_a` readiness/probe state for `qdrant` and `neo4j`, plus additive `pilot_runtime` / `last_turn_summary` / `pilot_readiness` blocks when pilot artifacts exist.

Notes:

* This is the primary operator product startup path.
* Manual per-service commands remain valid for recovery or focused debugging.
* The pilot runtime is local-only and does not open a new HTTP port.
* Live pilot grounding requires either `--capture-monitor <index>` or `--capture-region x,y,w,h`.
* Current pilot defaults: `models\qwen2.5-vl-7b-instruct-int4-ov` on `GPU` for vision, `models\qwen3-8b-int4-cw-ov` on `NPU` for grounded reply.

## M8.pilot: Observer pilot runtime

Pilot turn smoke (deterministic local fixtures):

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/pilot_turn_smoke.py --runs-dir runs\pilot-runtime-smoke --summary-json runs\pilot-runtime-smoke\summary.json
```

Standalone local runtime loop:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/pilot_runtime_loop.py --runs-dir runs\pilot-runtime --gateway-url http://127.0.0.1:8770 --voice-runtime-url http://127.0.0.1:8765 --tts-runtime-url http://127.0.0.1:8780 --capture-monitor 0
```

Expected result:

* `runs/<timestamp>-pilot-runtime/` is created.
* The runtime publishes `pilot_runtime_status_v1` in `pilot_runtime_status.json` and `pilot_runtime_status_latest.json`.
* Each completed turn writes `turns/<timestamp>-pilot-turn/pilot_turn.json` with schema `pilot_turn_v1`.
* Live turns follow `push-to-talk -> ASR -> vision -> hybrid_query(profile=combo_a) -> grounded reply -> TTS`.
* Degraded services and turn errors are carried into both status and turn artifacts; the runtime does not silently fall back to uncited guesses.

## M8.post: Observer pilot readiness summary

Pilot readiness helper:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/check_pilot_runtime_readiness.py --runs-dir runs --summary-json runs\pilot-runtime-readiness\readiness_summary.json --summary-md runs\pilot-runtime-readiness\summary.md
```

Manual live-acceptance flow:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/start_operator_product.py --runs-dir runs --start-voice-runtime --start-tts-runtime --start-pilot-runtime --capture-monitor 0
# complete one live F8 push-to-talk turn
python scripts/check_pilot_runtime_readiness.py --runs-dir runs --summary-json runs\pilot-runtime-readiness\readiness_summary.json --summary-md runs\pilot-runtime-readiness\summary.md
```

Readiness contract (`pilot_runtime_readiness_v1`):

* `schema_version = pilot_runtime_readiness_v1`
* `status = ok|error`
* `readiness_status = ready|attention|blocked`
* `actionable_message`
* `blocking_reason_codes`
* `next_step_code`, `next_step`
* `sources.startup|pilot_runtime_status|pilot_turn`
* `evidence.startup_fresh_within_window|pilot_runtime_configured|capture_configured|last_turn_fresh_within_window|live_turn_evidence|hybrid_profile|hybrid_planner_status|hybrid_degraded`
* `paths.summary_json`, `paths.history_summary_json`, `paths.summary_md`, `paths.history_summary_md`

Readiness policy:

* `ready` requires a fresh startup artifact, configured capture, a fresh live push-to-talk turn, and `hybrid_query(profile=combo_a)` without degraded fallback.
* `attention` means the artifacts are valid but the latest evidence is stale, degraded, fixture-only, or the pilot session stopped after a recent good turn.
* `blocked` means a required artifact or contract is missing/invalid, capture is not configured, the latest turn failed, or the turn does not prove `combo_a` grounding.

Notes:

* `pilot_turn_smoke.py` remains diagnostic only and does not produce `readiness_status=ready`.
* The operator snapshot and Streamlit `Stack Health` surface `pilot_readiness` additively when the summary artifact exists.

## M8.combo_a: Combo A live profile workflow

Workflow file:

* `.github/workflows/combo-a-profile-smoke.yml`

Purpose:

* keep `baseline_first` as the default PR path
* run additive `combo_a` parity checks on a separate nightly/manual workflow
* publish machine-readable combo_a gateway summaries, cross-service suite summary, operator probe artifacts, and the canonical `combo_a_operating_cycle_v1` decision surface

Workflow outputs:

* `runs/ci-smoke-gateway-combo-a/gateway_smoke_summary.json`
* `runs/ci-smoke-gateway-http-combo-a/gateway_http_smoke_summary.json`
* `runs/nightly-combo-a-cross-service-suite/cross_service_benchmark_suite.json`
* `runs/nightly-combo-a-cross-service-suite/<timestamp>-cross-service-suite/child_runs/<service>/<timestamp>-.../service_sla_summary.json`
* `runs/nightly-combo-a-operating-cycle/operating_cycle_summary.json`
* `runs/nightly-combo-a-operating-cycle/<timestamp>-combo-a-operating-cycle/summary.md`
* `runs/nightly-combo-a-operator-probes/operator_snapshot.json`

Combo A operating cycle command:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/run_combo_a_operating_cycle.py --runs-dir runs --policy report_only --summary-json runs\nightly-combo-a-operating-cycle\operating_cycle_summary.json --summary-md runs\nightly-combo-a-operating-cycle\summary.md
```

Operating cycle contract (`combo_a_operating_cycle_v1`):

* `schema_version = combo_a_operating_cycle_v1`
* `status = ok|error`
* `policy = report_only|fail_on_hold`
* `effective_policy = observe_only|promoted_nightly`
* `promotion_state = hold|eligible|promoted`
* `enforcement_surface = nightly_only`
* `blocking_reason_codes`
* `recommended_actions`
* `next_review_at_utc`
* `profile_scope = combo_a`
* `availability_status`
* `sources.gateway_combo_a|gateway_http_combo_a|cross_service_suite_combo_a|healthz|operator_snapshot`
  * `status = present|missing|invalid`
  * `fresh_within_window = true|false`
  * `checked_at_utc`
* `live_readiness.available`, `live_readiness.availability_status`, `live_readiness.services`
* `paths.summary_json`, `paths.history_summary_json`, `paths.summary_md`, `paths.history_summary_md`

Notes:

* `Qdrant` and `Neo4j` are treated as external services; the workflow only probes and seeds isolated fixture namespaces/collections.
* `voice_runtime_service` and `tts_runtime_service` are started as live loopback services for the suite profile.
* The workflow first writes `report_only` Combo A operating-cycle evidence, resolves `COMBO_A_EFFECTIVE_POLICY`, and only then runs the strict `fail_on_hold` pass when the live profile is already eligible.
* The workflow is additive and is not part of the default PR gate.

## M7.post: Gateway SLA/Observability baseline

At step `M7.post`, SLA and observability are built on top of the HTTP smoke summary without modification
`gateway_request_v1/gateway_response_v1`.

### SLA checker

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla.py --http-summary-json runs\ci-smoke-gateway-http-core\gateway_http_smoke_summary.json --summary-json runs\ci-smoke-gateway-sla\gateway_sla_summary.json --profile conservative --policy signal_only
```

SLA summary contract (`gateway_sla_summary_v1`):

* `schema_version = gateway_sla_summary_v1`
* `status = ok|error` (`error` only for execution/contract checker errors)
* `sla_status = pass|breach`
* `profile = conservative|moderate|aggressive`
* `policy = signal_only|fail_on_breach`
* `metrics`:
  * `request_count`
  * `failed_requests_count`
  * `error_rate`
  * `timeout_count`
  * `timeout_rate`
  * `latency_p50_ms`
  * `latency_p95_ms`
  * `latency_max_ms`
* `thresholds`:
  * `latency_p95_ms_max`
  * `error_rate_max`
  * `timeout_rate_max`
* `error_buckets`
* `breaches`
* `paths.summary_json`
* `exit_code`

Default conservative thresholds:

* `latency_p95_ms <= 1500`
* `error_rate <= 0.05`
* `timeout_rate <= 0.01`

Exit policy:

* `signal_only`: `0` even with `sla_status=breach`.
* `fail_on_breach`: `2` with `sla_status=breach`.
* Any execution/contract error checker: `2`.

History mode (`--runs-dir`):

* When `--runs-dir` is passed, checker creates `runs/<timestamp>-gateway-sla-check/`.
* In the run directory it is written:
  * `run.json`
  * `gateway_sla_summary.json` (history copy for trend scanner).
* The main `--summary-json` continues to work as the latest summary path for CI.

## M7.post: Gateway SLA trend snapshot (rolling baseline + breach drift)

The trend layer is calculated on top of history from `gateway_sla_summary_v1` without changing the base SLA of the contract.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/gateway_sla_trend_snapshot.py --sla-runs-dir runs\ci-smoke-gateway-sla --history-limit 10 --baseline-window 5 --critical-policy signal_only --runs-dir runs\ci-smoke-gateway-sla-trend
```

Trend snapshot contract (`gateway_sla_trend_snapshot_v1`):

* `status = ok|error`
* `history_limit`, `baseline_window`
* `latest` (latest valid SLA summary row)
* `rolling_baseline`:
  * `metrics_mean`
  * `delta_latest_minus_baseline`
  * `regression_flags` (`error_rate|timeout_rate|latency_p95` statuses + severities)
* `breach_drift`:
  * `latest_is_breach`
  * `baseline_breach_rate`
  * `delta_breach_rate`
  * `breach_rate_status`
  * `breach_rate_severity`
* `critical_policy`:
  * `mode = signal_only|fail_nightly`
  * `has_critical_regression`
  * `should_fail_nightly`
* `paths.run_dir`, `paths.run_json`, `paths.trend_snapshot_json`, `paths.summary_md`
* `exit_code`

Exit policy:

* `signal_only`: `0` with a valid snapshot, even with regressions.
* `fail_nightly`: `2` if `critical` severity is detected.

## G2: Gateway SLA fail_nightly readiness (staged report)

The readiness layer evaluates the readiness of the trend policy transition from `signal_only` to `fail_nightly`
without enabling hard-gate in this iteration.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla_fail_nightly_readiness.py --trend-runs-dir runs\nightly-gateway-sla-trend-history --history-limit 30 --readiness-window 14 --required-baseline-count 5 --max-warn-ratio 0.20 --policy report_only --runs-dir runs\nightly-gateway-sla-readiness --summary-json runs\nightly-gateway-sla-readiness\readiness_summary.json
```

Readiness summary contract (`gateway_sla_fail_nightly_readiness_v1`):

* `schema_version = gateway_sla_fail_nightly_readiness_v1`
* `status = ok|error`
* `readiness_status = ready|not_ready`
* `criteria`:
  * `readiness_window`
  * `required_baseline_count`
  * `max_warn_ratio`
  * `window_observed`
* `window_summary`:
  * `critical_count`
  * `warn_count`
  * `none_count`
  * `warn_ratio`
  * `insufficient_history_count`
  * `invalid_or_error_count`
* `latest`
* `recommendation.target_critical_policy` (`signal_only|fail_nightly`)
* `recommendation.reason_codes`
* `policy`
* `exit_code`
* `warnings`
* `paths.run_dir`, `paths.run_json`, `paths.summary_json`

Readiness rules (conservative bar):

* Valid trend snapshots (`gateway_sla_trend_snapshot_v1`, `status=ok`) are used.
* The last `N=14` valid snapshots after `history_limit=30` are taken.
* A transition is considered `ready` only if simultaneously:
  * `window_observed >= 14`
  * `critical_count == 0`
  * `warn_ratio <= 0.20`
  * `insufficient_history_count == 0`
  * `invalid_or_error_count == 0`
* Snapshot severity is calculated as max:
  * `rolling_baseline.regression_flags.max_regression_severity`
  * `breach_drift.breach_rate_severity`

Exit policy:

* `report_only`: `0` with `status=ok` even if `readiness_status=not_ready`; `2` only for execution/contract error.
* `fail_if_not_ready`: `2` with `status=error` or `readiness_status=not_ready`.

Nightly workflow:

* `.github/workflows/gateway-sla-readiness-nightly.yml`
* The SLA/trend/readiness/governance/progress history is saved between nightly runs via cache:
  * `runs/nightly-gateway-sla-history`
  * `runs/nightly-gateway-sla-trend-history`
  * `runs/nightly-gateway-sla-readiness`
  * `runs/nightly-gateway-sla-governance`
  * `runs/nightly-gateway-sla-progress`
* Nightly publishes:
  * `runs/nightly-gateway-sla-readiness/readiness_summary.json`
  * summary section `Gateway SLA Fail-Nightly Readiness`
  * artifacts `runs/nightly-gateway-*`.

## G2.1: Gateway SLA fail_nightly governance (go/no-go)

The Governance layer formalizes the `go|hold` solution for switching trend policy to `fail_nightly`
after accumulating nightly readiness history.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla_fail_nightly_governance.py --readiness-runs-dir runs\nightly-gateway-sla-readiness --history-limit 60 --required-ready-streak 3 --expected-readiness-window 14 --expected-required-baseline-count 5 --expected-max-warn-ratio 0.20 --policy report_only --runs-dir runs\nightly-gateway-sla-governance --summary-json runs\nightly-gateway-sla-governance\governance_summary.json
```

Governance summary contract (`gateway_sla_fail_nightly_governance_v1`):

* `schema_version = gateway_sla_fail_nightly_governance_v1`
* `status = ok|error`
* `decision_status = go|hold`
* `policy = report_only|fail_if_not_go`
* `criteria`:
  * `required_ready_streak`
  * `expected_readiness_window`
  * `expected_required_baseline_count`
  * `expected_max_warn_ratio`
  * `history_limit`
* `observed`:
  * `window_observed`
  * `valid_readiness_count`
  * `invalid_or_mismatched_count`
  * `latest_readiness_status`
  * `latest_ready_streak`
  * `ready_count_in_history`
* `recommendation`:
  * `target_critical_policy` (`signal_only|fail_nightly`)
  * `switch_surface` (`nightly_only`)
  * `reason_codes`
* `exit_code`
* `warnings`
* `paths.run_dir`, `paths.run_json`, `paths.summary_json`

Go/hold rules:

* Source-of-truth:
  * latest alias: `runs/nightly-gateway-sla-readiness/readiness_summary.json`
  * history rows: `runs/nightly-gateway-sla-readiness/<timestamp>-gateway-sla-fail-readiness/readiness_summary.json`
  * if history rows are present, top-level latest alias is excluded from history scan (so that there is no double-count);
    if there are no history rows yet, legacy fallback is used using top-level latest alias.
* Valid row requires:
  * `status=ok`
  * `readiness_status in {ready, not_ready}`
  * criteria match:
    * `readiness_window == 14`
    * `required_baseline_count == 5`
    * `max_warn_ratio == 0.20` (float epsilon check)
* After `history_limit=60` the tail of the story is taken.
* `decision_status=go` only if:
  * latest readiness = `ready`
  * latest ready streak `>= 3`
  * `invalid_or_mismatched_count == 0`
* Otherwise `decision_status=hold`.

Exit policy:

* `report_only`: `0` with `status=ok` regardless of `go|hold`; `2` only for execution/contract error.
* `fail_if_not_go`: `2` with `decision_status=hold` or `status=error`.

Nightly governance integration:

* `.github/workflows/gateway-sla-readiness-nightly.yml` adds:
  * governance step (report_only),
  * summary section `Gateway SLA Fail-Nightly Governance`,
  * artifacts `runs/nightly-gateway-sla-governance`.

## G2.2: Gateway SLA fail_nightly progress summary (nightly decision tracking)

Progress layer aggregates readiness+governance history and shows how much more
nightly signals are needed before a potential `go` solution.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla_fail_nightly_progress.py --readiness-runs-dir runs\nightly-gateway-sla-readiness --governance-runs-dir runs\nightly-gateway-sla-governance --readiness-history-limit 60 --governance-history-limit 60 --expected-readiness-window 14 --expected-required-baseline-count 5 --expected-max-warn-ratio 0.20 --required-ready-streak 3 --policy report_only --runs-dir runs\nightly-gateway-sla-progress --summary-json runs\nightly-gateway-sla-progress\progress_summary.json
```

Progress summary contract (`gateway_sla_fail_nightly_progress_v1`):

* `schema_version = gateway_sla_fail_nightly_progress_v1`
* `status = ok|error`
* `decision_status = go|hold`
* `policy = report_only|fail_if_not_go`
* `criteria`:
  * `expected_readiness_window`
  * `expected_required_baseline_count`
  * `expected_max_warn_ratio`
  * `required_ready_streak`
  * `readiness_history_limit`
  * `governance_history_limit`
* `observed.readiness`:
  * `valid_count`
  * `invalid_or_mismatched_count`
  * `latest_status`
  * `latest_window_observed`
  * `latest_ready_streak`
  * `ready_count_in_history`
  * `remaining_for_window`
  * `remaining_for_streak`
* `observed.governance`:
  * `valid_count`
  * `invalid_or_mismatched_count`
  * `latest_decision_status`
  * `latest_ready_streak`
  * `go_count_in_history`
* `latest.readiness`, `latest.governance`
* `recommendation`:
  * `target_critical_policy` (`signal_only|fail_nightly`)
  * `switch_surface` (`nightly_only`)
  * `reason_codes`
* `exit_code`
* `warnings`
* `paths.run_dir`, `paths.run_json`, `paths.summary_json`

Progress rules:

* Source-of-truth: valid readiness/governance summaries:
  * latest aliases:
    * `runs/nightly-gateway-sla-readiness/readiness_summary.json`
    * `runs/nightly-gateway-sla-governance/governance_summary.json`
  * history rows:
    * `runs/nightly-gateway-sla-readiness/<timestamp>-gateway-sla-fail-readiness/readiness_summary.json`
    * `runs/nightly-gateway-sla-governance/<timestamp>-gateway-sla-governance/governance_summary.json`
  * if history rows are present, top-level latest aliases are excluded from history scan; with legacy layout
    (history rows do not exist yet) fallback is used on top-level latest aliases.
* For valid rows, criteria must match with the expected baseline
  (`window=14`, `required_baseline_count=5`, `max_warn_ratio=0.20`, `required_ready_streak=3`).
* `decision_status=go` only if latest governance = `go`
  and `invalid_or_mismatched_count(governance)=0`.
* `remaining_for_window` and `remaining_for_streak` are considered according to latest readiness/history
  and are used as an operational indicator of progress.

Exit policy:

* `report_only`: `0` with `status=ok` regardless of `go|hold`; `2` only for execution/contract error.
* `fail_if_not_go`: `2` with `decision_status=hold` or `status=error`.

Nightly progress integration:

* `.github/workflows/gateway-sla-readiness-nightly.yml` adds:
  * progress step (report_only),
  * summary section `Gateway SLA Fail-Nightly Progress`,
  * artifacts `runs/nightly-gateway-sla-progress`.

## G2.manual: UTC preflight before manual `workflow_dispatch`

Helper checks the calendar-day guardrail before manually starting the nightly workflow.
Important: the script does not run dispatch, it only issues a decision summary.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla_manual_preflight.py --repo 8Dionysus/ATM10-Agent --workflow gateway-sla-readiness-nightly.yml --branch master --event workflow_dispatch --max-runs-per-utc-day 1 --token-env GITHUB_TOKEN --policy report_only --runs-dir runs/nightly-gateway-sla-preflight --summary-json runs/nightly-gateway-sla-preflight/preflight_summary.json
```

Preflight summary contract (`gateway_sla_manual_preflight_v1`):

* `schema_version = gateway_sla_manual_preflight_v1`
* `status = ok|error`
* `policy = report_only|fail_if_blocked`
* `inputs`:
  * `repo`, `workflow`, `branch`, `event`
  * `max_runs_per_utc_day`
  * `per_page`
  * `token_source = env`
* `observed`:
  * `workflow_runs_observed`
  * `today_dispatch_count`
  * `latest_dispatch_run`
* `decision`:
  * `accounted_dispatch_allowed`
  * `decision_status` (`allow_accounted_dispatch|block_accounted_dispatch|error`)
  * `next_accounted_dispatch_at_utc`
  * `reason_codes`
* `warnings`
* `error`
* `exit_code`
* `paths.run_dir`, `paths.run_json`, `paths.summary_json`

Decision interpretation:

* `accounted_dispatch_allowed=true` -> you can execute the next dispatch that is taken into account on the current UTC day.
* `accounted_dispatch_allowed=false` + `reason_codes=["utc_day_quota_exhausted"]` ->
  the new run taken into account is blocked until `next_accounted_dispatch_at_utc`.
* `policy=fail_if_blocked` returns `exit_code=2` when guardrail blocks startup.

## G2.manual: unified manual-cycle summary (`preflight + readiness/governance/progress/transition`)

Helper aggregates preflight and current nightly summaries into a single machine-readable snapshot for operator-loop.
The side-effect free: dispatch script does not run.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla_manual_cycle_summary.py --runs-dir runs --policy report_only --summary-json runs/nightly-gateway-sla-manual-cycle/manual_cycle_summary.json
```

Unified summary contract (`gateway_sla_manual_cycle_summary_v1`):

* `schema_version = gateway_sla_manual_cycle_summary_v1`
* `status = ok|error`
* `checked_at_utc`
* `policy = report_only|fail_if_blocked`
* `sources`:
  * `preflight|readiness|governance|progress|transition`
  * for each source: `path`, `status` (`present|missing|invalid`), schema/status metadata
  * `preflight` — required source; `readiness/governance/progress/transition` — optional sources
* `observed`:
  * `preflight.workflow_runs_observed|today_dispatch_count|latest_dispatch_run`
  * `readiness_status`
  * `governance_decision_status`
  * `progress.remaining_for_window|remaining_for_streak|decision_status`
  * `transition.allow_switch|reason_codes|decision_status`
* `decision` (from preflight):
  * `accounted_dispatch_allowed`
  * `decision_status`
  * `next_accounted_dispatch_at_utc`
  * `reason_codes`
* `warnings`
* `error`
* `exit_code`
* `paths.run_dir`, `paths.run_json`, `paths.summary_json`

Exit policy:

* `report_only`: `0`, if preflight is valid (even with block decision); `2` only with `status=error`.
* `fail_if_blocked`: `2` if `accounted_dispatch_allowed=false` or `status=error`.

Decision interpretation:

* `decision.accounted_dispatch_allowed=true` -> the following dispatch can be executed.
* `decision.accounted_dispatch_allowed=false` -> dispatch is blocked until `decision.next_accounted_dispatch_at_utc`.
* Optional source missing/invalid does not break the summary, but is reflected in `sources.*.status` and `warnings`.

## G2.manual: local manual nightly runner (solo+AI, no workflow_dispatch)

Wrapper runs local nightly-chain as a single manual entrypoint with UTC guardrail
(`max 1 accounted run/day`) and recovery-mode without progression credit.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/run_gateway_sla_manual_nightly.py --runs-dir runs --policy report_only --max-runs-per-utc-day 1 --allow-recovery-rerun true --summary-json runs/nightly-gateway-sla-manual-runner/manual_nightly_summary.json --preflight-summary-json runs/nightly-gateway-sla-preflight/local_preflight_summary.json --manual-cycle-summary-json runs/nightly-gateway-sla-manual-cycle/manual_cycle_summary.json
```

Runner summary contract (`gateway_sla_manual_nightly_runner_v1`):

* `schema_version = gateway_sla_manual_nightly_runner_v1`
* `status = ok|error`
* `policy = report_only|fail_if_blocked`
* `execution_mode = accounted|recovery|blocked|error`
* `guardrail`:
  * `decision_status`
  * `accounted_dispatch_allowed`
  * `recovery_rerun_allowed`
  * `max_runs_per_utc_day`
* `steps[]`:
  * `id`, `status`, `exit_code`, `started_at_utc`, `finished_at_utc`, `paths`, `error`
* `decision` (from local preflight `gateway_sla_manual_preflight_v1`):
  * `accounted_dispatch_allowed`
  * `recovery_rerun_allowed`
  * `decision_status` (`allow_accounted_dispatch|allow_recovery_rerun|block_accounted_dispatch|error`)
  * `next_accounted_dispatch_at_utc`
  * `reason_codes`
* `warnings`
* `error`
* `exit_code`
* `paths.run_dir`, `paths.run_json`, `paths.summary_json`, `paths.preflight_summary_json`, `paths.manual_cycle_summary_json`

Execution behavior:

* `accounted`: full chain (`gateway_http_core -> sla_signal -> trend_signal -> readiness -> governance -> progress -> transition`).
* `recovery`: only `transition` + `manual_cycle_summary` (without progression credit).
* `blocked`: chain steps are not executed, but `manual_cycle_summary` is always updated with local preflight.
* `fail-fast`: at `status=error` of any step, the wrapper stops the chain and returns `exit_code=2`.

Guardrail source-of-truth:

* Counted runs are counted according to history `runs/nightly-gateway-sla-manual-runner/*/run.json`
  only with `result.progression_credit=true`.
* Recovery is allowed only if `readiness/governance/progress` summaries are valid (`status=ok`),
  and `transition_summary.json` is missing or invalid.

## G2.manual: local cadence brief (daily operator status/ETA)

Read-only helper builds a single daily brief for a local solo+AI cycle:
Is it possible to do the next considered launch now, what is the attention-state, and the minimum ETA before go-candidate.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla_manual_cadence_brief.py --runs-dir runs --policy report_only --summary-json runs/nightly-gateway-sla-manual-cadence/cadence_brief.json
```

Cadence brief contract (`gateway_sla_manual_cadence_brief_v1`):

* `schema_version = gateway_sla_manual_cadence_brief_v1`
* `status = ok|error`
* `policy = report_only|fail_if_attention_required`
* `sources`:
  * `manual_runner|manual_cycle|readiness|governance|progress|transition`
  * status per source: `present|missing|invalid`
  * required sources: `manual_cycle`, `progress`
* `decision` (source-of-truth: `manual_cycle_summary.decision`):
  * `accounted_dispatch_allowed`
  * `decision_status`
  * `next_accounted_dispatch_at_utc`
  * `reason_codes`
* `observed`:
  * `remaining_for_window`
  * `remaining_for_streak`
  * `readiness_status`
  * `governance_decision_status`
  * `transition_allow_switch`
* `attention_state`:
  * `source_repair_required|wait_for_utc_reset|run_recovery_only|ready_for_accounted_run|unknown`
* `forecast`:
  * `min_accounted_runs_to_window`
  * `min_accounted_runs_to_streak`
  * `next_accounted_dispatch_at_utc`
  * `earliest_window_ready_at_utc`
  * `earliest_streak_ready_at_utc`
  * `earliest_go_candidate_at_utc`
* `warnings`
* `error`
* `exit_code`
* `paths.run_dir`, `paths.run_json`, `paths.summary_json`

Exit policy:

* `report_only`: `0` at `status=ok`; `2` only with `status=error`.
* `fail_if_attention_required`: `2` with `attention_state in {source_repair_required, wait_for_utc_reset, run_recovery_only, unknown}` or `status=error`.

Operator interpretation:

* `attention_state=ready_for_accounted_run` -> you can run the next cycle taken into account.
* `attention_state=wait_for_utc_reset` -> wait for `forecast.next_accounted_dispatch_at_utc`.
* `attention_state=run_recovery_only` -> only recovery-path without progression credit is allowed.
* `attention_state=source_repair_required` -> first restore required summaries (`manual_cycle`, `progress`).

## G2.3: Gateway SLA fail_nightly transition telemetry + managed nightly promotion

Transition checker preserves formal decision telemetry for readiness/governance/progress,
while the nightly strict gate remains `nightly_only` and is promoted to `fail_nightly`
only when the operating-cycle decision surface marks baseline eligible.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla_fail_nightly_transition.py --readiness-runs-dir runs/nightly-gateway-sla-readiness --governance-runs-dir runs/nightly-gateway-sla-governance --progress-runs-dir runs/nightly-gateway-sla-progress --readiness-history-limit 60 --governance-history-limit 60 --progress-history-limit 60 --expected-readiness-window 14 --expected-required-baseline-count 5 --expected-max-warn-ratio 0.20 --required-ready-streak 3 --policy report_only --runs-dir runs/nightly-gateway-sla-transition --summary-json runs/nightly-gateway-sla-transition/transition_summary.json
```

Nightly transition integration:

* `.github/workflows/gateway-sla-readiness-nightly.yml` adds:
  * step `Transition - Gateway SLA fail_nightly switch gate (report_only)`,
  * step `Operating cycle - Gateway SLA policy decision surface (report_only)`,
  * promoted strict step `gateway_sla_trend_snapshot --critical-policy fail_nightly` only when `operating_cycle_summary.json.effective_policy = fail_nightly`,
  * summary section `Gateway SLA Fail-Nightly Transition`,
  * summary section `Gateway SLA Operating Cycle`,
  * cache/artifact paths `runs/nightly-gateway-sla-transition` and `runs/nightly-gateway-sla-operating-cycle`.

Recovery rule (calendar-day guardrail compatible):

* If the successful UTC-run is missing `runs/nightly-gateway-sla-transition/transition_summary.json`,
  One recovery rerun is allowed on the same UTC day to restore the chain.
* Recovery rerun is not considered a separate progression day for switch evidence.

History consistency hotfix (`2026-03-03`):

* Each checker (`readiness/governance/progress/transition`) writes dual outputs per launch:
  * latest alias in `runs/nightly-gateway-sla-*/<summary>.json`;
  * history copy to `run_dir/<summary>.json`.
* Progress/transition collectors count `valid_count` using history rows, not including top-level latest alias
  if history copies are available.
* Backfill is not done for old runs: a valid accumulation window for `valid_count` is considered
  from the first nightly run after merge hotfix.

## G2 Managed Nightly Promotion

Operational goal: keep `pytest.yml` and local smoke on `signal_only`, while nightly promotion to
`fail_nightly` is decided by `gateway_sla_operating_cycle_v1` and remains additive to the runtime API.

Managed policy semantics:

* PR/local baseline stays `signal_only`.
* Nightly strict enforcement surface stays `nightly_only`.
* `run_gateway_sla_operating_cycle.py` is the canonical decision surface for:
  * `effective_policy`
  * `promotion_state`
  * `blocking_reason_codes`
  * `recommended_actions`
  * `next_review_at_utc`
* If `promotion_state != eligible`, nightly continues publishing `signal_only` posture and skips the promoted strict `fail_nightly` step.

### Daily loop (primary = nightly, fallback = manual)

Primary mode:

* use `.github/workflows/gateway-sla-readiness-nightly.yml` (cron `35 3 * * *`).

Fallback mode (if nightly run is skipped/unavailable):

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/run_gateway_sla_manual_nightly.py --runs-dir runs --policy report_only --summary-json runs/nightly-gateway-sla-manual-runner/manual_nightly_summary.json
python scripts/check_gateway_sla_manual_cycle_summary.py --runs-dir runs --policy report_only --summary-json runs/nightly-gateway-sla-manual-cycle/manual_cycle_summary.json
python scripts/check_gateway_sla_manual_cadence_brief.py --runs-dir runs --policy report_only --summary-json runs/nightly-gateway-sla-manual-cadence/cadence_brief.json
```

Single-cycle local operator helper:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/run_gateway_sla_operating_cycle.py --runs-dir runs --policy report_only --summary-json runs/nightly-gateway-sla-operating-cycle/operating_cycle_summary.json --brief-md runs/nightly-gateway-sla-operating-cycle/triage_brief.md
```

Operating cycle contract (`gateway_sla_operating_cycle_v1`):

* `schema_version = gateway_sla_operating_cycle_v1`
* `status = ok|error`
* `policy = report_only`
* `effective_policy = signal_only|fail_nightly`
* `promotion_state = hold|blocked|eligible`
* `enforcement_surface = nightly_only`
* `blocking_reason_codes`
* `recommended_actions`
* `next_review_at_utc`
* `profile_scope = baseline_first`
* `precheck.required_sources_fresh_current_utc_day = true|false`
* `precheck.manual_snapshot_reused = true|false`
* `cycle.source = nightly|manual|unknown`
* `cycle.operating_mode = reuse_fresh_latest|manual_fallback|error`
* `cycle.used_manual_fallback = true|false`
* `cycle.manual_execution_mode`, `cycle.manual_decision_status`, `cycle.next_accounted_dispatch_at_utc`
* `sources.readiness|governance|progress|transition|remediation|integrity|cadence`
  * `status = present|missing|invalid`
  * `fresh_for_current_utc_day = true|false`
  * `checked_at_utc`
* `triage`:
  * `readiness_status`
  * `governance_decision_status`
  * `progress_decision_status`
  * `remaining_for_window`
  * `remaining_for_streak`
  * `transition_allow_switch`
  * `candidate_item_ids`
  * `reason_codes`
  * `integrity_status`
  * `integrity_reason_codes`
  * `invalid_counts`
  * `attention_state`
  * `earliest_go_candidate_at_utc`
* `interpretation`:
  * `telemetry_repair_required`
  * `remediation_backlog_primary`
  * `blocked_manual_gate`
  * `next_action_hint`
* `paths.summary_json`, `paths.history_summary_json`, `paths.brief_md`, `paths.history_brief_md`

Behavior:

* If the required latest summaries are fresh for the current UTC day, helper reuses the existing latest aliases and does not run a new `manual_nightly`.
* If the latest latest snapshot coincides in time with the local manual cluster, helper marks `cycle.source=manual` and saves `operating_mode=reuse_fresh_latest`.
* If required sources missing/stale/invalid, helper runs fallback in a fixed order:
  * `run_gateway_sla_manual_nightly.py`
  * `check_gateway_sla_manual_cadence_brief.py`
  * `check_gateway_sla_fail_nightly_remediation.py`
  * `check_gateway_sla_fail_nightly_integrity.py`
* The fallback order is fixed: `cadence` must be updated to `remediation/integrity` in order for the optional source `manual_cadence` to be consistent in the same loop.
* Gateway safe actions additionally expose `gateway_sla_operating_cycle_smoke` as the canonical smoke-only action for refreshing the policy decision surface through the operator API.

Daily acceptance checks:

* latest summaries `status=ok`:
  * `runs/nightly-gateway-sla-readiness/readiness_summary.json`
  * `runs/nightly-gateway-sla-governance/governance_summary.json`
  * `runs/nightly-gateway-sla-progress/progress_summary.json`
  * `runs/nightly-gateway-sla-transition/transition_summary.json`
  * `runs/nightly-gateway-sla-remediation/remediation_summary.json`
  * `runs/nightly-gateway-sla-integrity/integrity_summary.json`
  * `runs/nightly-gateway-sla-manual-cadence/cadence_brief.json`
* `invalid_or_mismatched_count == 0` (governance/progress/transition).
* `integrity_status=clean` or, at a minimum, the absence of `required_sources_unhealthy`/`dual_write_invariant_broken`/`anti_double_count_invariant_broken`.
* `remaining_for_window` decreases by accounted run.
* `next_accounted_dispatch_at_utc` does not violate the guardrail of `1 accounted run / UTC day`.

### Post-promotion monitoring

* In the nightly loop the following are required:
  * promoted strict trend gate (`fail_nightly`) only when `effective_policy = fail_nightly`;
  * decision telemetry summaries (`readiness/governance/progress/transition`);
  * remediation snapshot (`runs/nightly-gateway-sla-remediation/remediation_summary.json`);
  * integrity snapshot (`runs/nightly-gateway-sla-integrity/integrity_summary.json`);
  * operating-cycle summary (`runs/nightly-gateway-sla-operating-cycle/operating_cycle_summary.json`).
* If nightly fails, source-of-truth for baseline promotion triage is the workflow-published `operating_cycle_summary.json`
  plus `remediation_summary.json`.

## G2.4: Gateway SLA fail_nightly remediation snapshot

Read-only helper collects the latest G2 summaries into a single remediation snapshot and machine-readable backlog candidates
without recalculating history and without changing runtime/API/UI surface.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla_fail_nightly_remediation.py --runs-dir runs --policy report_only --summary-json runs/nightly-gateway-sla-remediation/remediation_summary.json
```

Remediation contract (`gateway_sla_fail_nightly_remediation_v1`):

* `schema_version = gateway_sla_fail_nightly_remediation_v1`
* `status = ok|error`
* `policy = report_only|fail_if_remediation_required`
* `sources`:
  * `readiness|governance|progress|transition|manual_cadence`
  * status per source: `present|missing|invalid`
  * required sources: `readiness`, `governance`, `progress`, `transition`
  * `manual_cadence` — optional enrichment source
* `observed`:
  * `readiness_status`
  * `governance_decision_status`
  * `progress_decision_status`
  * `transition_allow_switch`
  * `remaining_for_window`
  * `remaining_for_streak`
  * optional `attention_state`
* `reason_codes`:
  * deduplicated union of latest `recommendation.reason_codes` and `manual_cadence.decision.reason_codes`
* `candidate_items`:
  * deterministic list of backlog candidates
  * element fields: `id`, `priority`, `summary`, `source_refs`
  * buckets: `telemetry_integrity`, `regression_investigation`, `window_accumulation`, `ready_streak_stabilization`, `manual_guardrail`
  * maximum `5` items per snapshot
* `warnings`
* `error`
* `exit_code`
* `paths.run_dir`, `paths.run_json`, `paths.summary_json`, `paths.history_summary_json`

Artifacts:

* latest alias: `runs/nightly-gateway-sla-remediation/remediation_summary.json`
* history copy: `runs/nightly-gateway-sla-remediation/<timestamp>-gateway-sla-fail-remediation/remediation_summary.json`
* run metadata: `runs/nightly-gateway-sla-remediation/<timestamp>-gateway-sla-fail-remediation/run.json`

Nightly integration:

* `.github/workflows/gateway-sla-readiness-nightly.yml` runs remediation helper in `report_only` mode.
* Workflow publishes summary section `Gateway SLA Fail-Nightly Remediation`.
* Cache/artifact wiring saves `runs/nightly-gateway-sla-remediation` along with the rest of the G2 nightly paths.
* G2 summary sections use `always()` semantics so that diagnostics are not lost in red nightly after strict `fail_nightly`.

Exit policy:

* `report_only`: `0`, if the remediation snapshot was collected successfully; `2` only with `status=error`.
* `fail_if_remediation_required`: `2` if broken required sources or `candidate_items` is non-empty; also `2` with `status=error`.

Operator usage:

* For nightly triage, use workflow-published `runs/nightly-gateway-sla-remediation/remediation_summary.json` as canonical draft backlog.
* Direct local launch of helper remains the fallback path for manual rechecking or skipped nightly run.
* If snapshot is green (`candidate_items=[]`), no additional remediation items are required.
* If the snapshot is not green, expand `candidate_items` to 3-5 `G2`-only points with a link to the corresponding source artifacts.

## G2.post3: Gateway SLA fail_nightly integrity snapshot

Integrity helper aggregates latest nightly summaries and checks operator-facing invariants without adding a new hard fail surface.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla_fail_nightly_integrity.py --runs-dir runs --policy report_only --summary-json runs/nightly-gateway-sla-integrity/integrity_summary.json
```

Integrity contract (`gateway_sla_fail_nightly_integrity_v1`):

* `schema_version = gateway_sla_fail_nightly_integrity_v1`
* `status = ok|error`
* `policy = report_only`
* `sources`:
  * `readiness|governance|progress|transition|remediation|manual_cadence`
  * status per source: `present|missing|invalid`
  * required sources: `readiness`, `governance`, `progress`, `transition`, `remediation`
  * `manual_cadence` remains optional source for UTC guardrail validation
* `observed`:
  * `telemetry_ok`
  * `dual_write_ok`
  * `anti_double_count_ok`
  * `utc_guardrail_status = ok|attention|not_available`
  * `utc_guardrail_ok = true|false|null`
  * `utc_guardrail` (`attention_state`, `decision_status`, `accounted_dispatch_allowed`, `next_accounted_dispatch_at_utc`, `reason_codes`)
  * `invalid_counts`:
    * `governance`
    * `progress_readiness`
    * `progress_governance`
    * `transition_aggregated`
* `decision`:
  * `integrity_status = clean|attention`
  * `reason_codes`
* `warnings`
* `error`
* `exit_code`
* `paths.run_dir`, `paths.run_json`, `paths.summary_json`, `paths.history_summary_json`

Checked invariants:

* required source schemas/statuses must be valid
* telemetry counters must stay `0`:
  * `governance.observed.invalid_or_mismatched_count`
  * `progress.observed.readiness.invalid_or_mismatched_count`
  * `progress.observed.governance.invalid_or_mismatched_count`
  * `transition.observed.aggregated.invalid_or_mismatched_count`
* dual-write invariants:
  * `paths.run_json` exists
  * `paths.history_summary_json` exists
  * history copy lives under `run_dir`
  * history copy matches latest alias by `schema_version/status`
* anti-double-count invariants:
  * `history_summary_json` differs from top-level latest alias
  * history copy remains the canonical nested summary for collectors
* UTC guardrail:
  * if `manual_cadence` is available, helper checks the consistency of `attention_state`, `decision.accounted_dispatch_allowed`, `decision.next_accounted_dispatch_at_utc` and `decision.reason_codes`
  * if `manual_cadence` is missing, `utc_guardrail_status=not_available` is set and warning without fail

Artifacts:

* latest alias: `runs/nightly-gateway-sla-integrity/integrity_summary.json`
* history copy: `runs/nightly-gateway-sla-integrity/<timestamp>-gateway-sla-fail-integrity/integrity_summary.json`
* run metadata: `runs/nightly-gateway-sla-integrity/<timestamp>-gateway-sla-fail-integrity/run.json`

Nightly integration:

* `.github/workflows/gateway-sla-readiness-nightly.yml` runs integrity helper in `report_only` mode
* workflow publishes summary section `Gateway SLA Fail-Nightly Integrity`
* cache/artifact wiring saves `runs/nightly-gateway-sla-integrity` along with the rest of the G2 nightly paths

Exit policy:

* `report_only`: `0`, if the integrity snapshot was collected successfully; `2` only with `status=error`

Operator usage:

* Use integrity snapshot as a quick machine-readable verdict for `G2 telemetry integrity` daily check.
* `integrity_status=attention` itself does not add a new hard gate, but should fall into the nightly/manual triage.
* If there are `dual_write` or `anti_double_count` reason-codes, first repair the telemetry/artifact path, then interpret the remediation backlog.

## M8.0: Streamlit IA spec (decision-complete, no implementation)

At step `M8.0` we fix the IA specification without adding Streamlit runtime code.

Source of truth:

* `docs/STREAMLIT_IA_V0.md`

Expected result:

* The document contains 4 UI zones (`Stack Health`, `Run Explorer`, `Latest Metrics`, `Safe Actions`).
* Canonical data sources (CI smoke summaries) and field mapping are fixed.
* Safe action guardrails and handoff contract for `M8.1` have been fixed.
* The dock is protected by the `tests/test_streamlit_ia_doc.py` regression test.

## M8.1: Streamlit operator panel v0 + no-crash smoke

Launching the panel:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m streamlit run scripts/streamlit_operator_panel.py -- --runs-dir runs --gateway-url http://127.0.0.1:8770
```

Launching smoke-gate:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/streamlit_operator_panel_smoke.py --panel-runs-dir runs --runs-dir runs/ci-smoke-streamlit --summary-json runs/ci-smoke-streamlit/streamlit_smoke_summary.json --gateway-url http://127.0.0.1:8770 --startup-timeout-sec 45 --viewport-width 390 --viewport-height 844 --compact-breakpoint-px 768
```

Dependency preflight:

* `scripts/streamlit_operator_panel_smoke.py` first checks the import availability of `streamlit` in the active interpreter.
* If the dependency is missing, smoke does not launch subprocess and immediately writes the usual `streamlit_smoke_summary_v1` with:
  * `status=error`
  * `startup_ok=false`
  * `exit_code=2`
  * `required_missing_sources=[]`
  * `optional_missing_sources=[]`
* `streamlit_startup.log` in this case contains a repair hint:
  * `python -m pip install -r requirements.txt`
* `run.json` receives `error_code=runtime_missing_dependency`.

Expected result contract (`streamlit_smoke_summary_v1`):

* `schema_version = streamlit_smoke_summary_v1`
* `status = ok|error`
* `startup_ok`
* `tabs_detected`
* `mobile_layout_contract_ok`
* `mobile_layout_policy` (`streamlit_mobile_layout_policy_v1`)
* `viewport_baseline` (`width/height/orientation`)
* `missing_sources` (backward-compatible alias: required sources only)
* `required_missing_sources`
* `optional_missing_sources`
* `errors`
* `exit_code`
* `paths.run_dir`, `paths.run_json`, `paths.summary_json`

Exit policy:

* `0` only if `status=ok`.
* `2` for any `status=error`.
* `status=error` only if strict conditions are violated:
  * startup fail,
  * mobile layout contract fail,
  * missing `required_missing_sources`.
* `optional_missing_sources` do not translate smoke to `error`; used as observability signal.
* The optional surface includes operator-facing G2 summaries (`progress`, `transition`, `remediation`, `integrity`, `operating_cycle`), if they are not already published in the selected `runs_dir`.

Manual operator-check:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pip show streamlit
python -m streamlit run scripts/streamlit_operator_panel.py -- --runs-dir runs --gateway-url http://127.0.0.1:8770
```

Operator procedure:

* success criterion: Streamlit banner `You can now view your Streamlit app in your browser.` and line `Local URL: ...` appear in the terminal
* if the onboarding prompt `Email:` appears at first-run, send an empty line and continue to banner
* after fixing the banner, stop the process via `Ctrl+C`
* save terminal output to `runs/ci-smoke-streamlit/<timestamp>-manual-operator-check.log`

## M8.post: Streamlit Safe Actions audit trail

`Safe Actions` remains smoke-only, but execution and audit now go through the gateway instead of direct Streamlit subprocess launch.

Audit artifact path:

* `<gateway-runs-dir>/ui-safe-actions/safe_actions_audit.jsonl`

Audit entry contract (JSON object per line):

* `timestamp_utc` (ISO8601 UTC)
* `action_key`
* `command`
* `exit_code`
* `status` (`ok|error`)
* `summary_json`
* `summary_status` (nullable)
* `error` (nullable)
* `ok` (bool)

UI behavior:

* Streamlit loads the catalog and recent audit rows through `GET /v1/operator/safe-actions`.
* The run action is executed only through `POST /v1/operator/safe-actions/run`.
* The panel requires explicit confirmation before sending the smoke action request.
* If the gateway is unavailable, `Safe Actions` is disabled instead of falling back to local subprocess execution.
* After execution, the panel refreshes the latest gateway-managed audit state and shows `Last safe action` + `Recent safe actions`.

## M8.post: Streamlit Latest Metrics history filters

In the `Latest Metrics` tab, the primary historical path is now `GET /v1/operator/history`; local canonical run directories remain a read-only fallback when the gateway history endpoint is unavailable.

History sources:

* `runs/ci-smoke-phase-a`
* `runs/ci-smoke-retrieve`
* `runs/ci-smoke-eval`
* `runs/ci-smoke-gateway-core`
* `runs/ci-smoke-gateway-automation`
* `runs/ci-smoke-gateway-http-core`
* `runs/ci-smoke-gateway-http-automation`

History controls:

* `History sources` (multiselect, default = all canonical sources)
* `History statuses` (multiselect, default = `ok,error`)
* `History limit per source` (default = `10`)

Historical row fields (`metrics_history_row_v1`, in-memory UI contract):

* `source`
* `timestamp_utc`
* `status`
* `run_dir`
* `run_json`
* `summary_json` (if available)
* `request_count`
* `failed_requests_count`
* `results_count`
* `query_count`
* `mean_mrr_at_k`
* `details`

Resilience/performance policy:

* scan cap: maximum `200` candidate run-directories on source before applying limit.
* incorrect run directories are skipped; The UI shows a warning and continues working.
* if there are no history lines, `not available yet` is shown.

## G2.post: Streamlit fail_nightly progress visibility (optional sources)

In the `Latest Metrics` tab, a separate block `Gateway fail_nightly progress` has been added, which
aggregates nightly decision-path artifacts and shows operational progress up to `go|hold`.

Optional progress sources:

* `runs/nightly-gateway-sla-readiness/readiness_summary.json`
* `runs/nightly-gateway-sla-governance/governance_summary.json`
* `runs/nightly-gateway-sla-progress/progress_summary.json`

Supported contracts:

* `gateway_sla_fail_nightly_readiness_v1`
* `gateway_sla_fail_nightly_governance_v1`
* `gateway_sla_fail_nightly_progress_v1`

Progress block field UI:

* `readiness_status`
* `latest_ready_streak`
* `decision_status`
* `remaining_for_window`
* `remaining_for_streak`
* `target_critical_policy`
* `reason_codes`

Tolerant rendering policy:

* if optional sources are missing, the panel shows `not available yet`;
* if the optional source is broken/contract-mismatch, the panel shows a warning and continues working;
* optional progress sources are not included in strict `missing_sources` smoke-policy.

## G2.post2: Streamlit fail_nightly remediation visibility (published snapshot)

In the `Latest Metrics` tab, a separate block `Gateway fail_nightly remediation` has been added, which
reads only workflow-published remediation snapshot and shows operator-facing triage backlog without
re-aggregation of upstream G2 summaries.

Optional remediation source:

* `runs/nightly-gateway-sla-remediation/remediation_summary.json`

Supported Contract:

* `gateway_sla_fail_nightly_remediation_v1`

UI of the remediation block field:

* `status`
* `policy`
* `readiness_status`
* `governance_decision_status`
* `progress_decision_status`
* `transition_allow_switch`
* `remaining_for_window`
* `remaining_for_streak`
* optional `attention_state`
* `candidate_item_count`
* `candidate_item_ids`
* `reason_codes`

UI backlog surface:

* separate compact table according to `candidate_items`
* speakers: `id`, `priority`, `summary`, `source_refs`
* artifact panel showing `checked_at_utc` and `summary_json`

Tolerant rendering policy:

* if remediation snapshot is missing, the panel shows `not available yet`;
* if the remediation snapshot is broken/contract-mismatch, the panel shows a warning and continues working;
* remediation source is included in `optional_missing_sources`, but is not included in strict `missing_sources` smoke-policy.

## G2.post3: Streamlit fail_nightly integrity visibility

In the `Latest Metrics` tab, the `Gateway fail_nightly integrity` block has been added, which shows the summary verdict
by telemetry, dual-write/anti-double-count and UTC guardrail invariants.

Optional integrity source:

* `runs/nightly-gateway-sla-integrity/integrity_summary.json`

Supported Contract:

* `gateway_sla_fail_nightly_integrity_v1`

UI field of the integrity block:

* `status`
* `integrity_status`
* `telemetry_ok`
* `dual_write_ok`
* `anti_double_count_ok`
* `utc_guardrail_status`
* `governance_invalid`
* `progress_readiness_invalid`
* `progress_governance_invalid`
* `transition_aggregated_invalid`
* `reason_codes`

Artifact panels:

* separate JSON panel by `utc_guardrail`
* compact artifact panel with `checked_at_utc` and `summary_json`

Tolerant rendering policy:

* if integrity snapshot is missing, the panel shows `not available yet`
* if the integrity snapshot is broken/contract-mismatch, the panel shows a warning and continues working
* integrity source is included in `optional_missing_sources`, but is not included in strict `missing_sources` smoke-policy

## G2.post4: Streamlit operating cycle visibility

In the `Latest Metrics` tab, the top read-only block `G2 operating cycle` has been added, which
reads a single operator snapshot from the local helper without starting a new loop from the UI.

Optional operating-cycle source:

* `runs/nightly-gateway-sla-operating-cycle/operating_cycle_summary.json`

Supported Contract:

* `gateway_sla_operating_cycle_v1`

UI field of the operating-cycle block:

* `cycle_source`
* `operating_mode`
* `used_manual_fallback`
* `manual_execution_mode`
* `manual_decision_status`
* `readiness_status`
* `governance_decision_status`
* `progress_decision_status`
* `remaining_for_window`
* `remaining_for_streak`
* `transition_allow_switch`
* `candidate_item_count`
* `integrity_status`
* `attention_state`
* `earliest_go_candidate_at_utc`
* `next_accounted_dispatch_at_utc`
* `next_action_hint`

Artifact panels:

* compact artifact panel with `checked_at_utc`, `summary_json`, `brief_md`
* the absence of `brief_md` is considered soft-info and does not convert block to warning/error
* optional JSON panel by `invalid_counts`, if they are present in triage

Guardrails:

* the block only reads the published summary and does not run `scripts/run_gateway_sla_operating_cycle.py`
* `Safe Actions` remain smoke-only and are not expanded by this helper
* operating-cycle source is included in `optional_missing_sources`, but not in strict `missing_sources` smoke-policy

## M8.post: Streamlit compact mobile layout baseline

The compact mobile layout policy is fixed in the panel without changing IA tabs and safe action guardrails.

Policy defaults:

* `compact_breakpoint_px = 768`
* baseline viewport for smoke-check: `390x844` (portrait)
* compact mode includes:
  * reduced container paddings
  * stack header controls in one column
  * horizontal scroll fallback for dataframes

Regression smoke-check:

* `scripts/streamlit_operator_panel_smoke.py` validates the mobile policy contract and baseline viewport.
* If the mobile baseline (`viewport > breakpoint` or `landscape`) is violated, smoke returns `status=error`, `exit_code=2`.

## Local OpenVINO stack (task-first)

Active stack:

* `Qwen3-8B`
* `Qwen2.5-VL-7B-Instruct`
* `Qwen3-Embedding-0.6B`
* `Qwen3-Reranker-0.6B`
* `Whisper v3 Turbo (OpenVINO GenAI runtime path for ASR)`

Deactivated:

* `Qwen3-TTS-12Hz-0.6B-CustomVoice` (archived; do not use in production runbook).
* `Qwen3-ASR-0.6B` (archived; reversible via explicit opt-in flags).
* `Qwen3-VL-4B-Instruct` custom OpenVINO export (archived for the active pilot path; current OpenVINO GenAI VLM runtime does not accept the `qwen3_vl` model type used by that export).

Detailed matrix: `docs/QWEN3_MODEL_STACK.md`.

Pilot runtime defaults:

* Vision: `models\qwen2.5-vl-7b-instruct-int4-ov` on `GPU`
* Grounded reply: `models\qwen3-8b-int4-cw-ov` on `NPU`
* ASR: `models\whisper-large-v3-turbo-ov` on `NPU`

### Qwen3-ASR self-conversion (archived reference, keep for future restore)

```powershell
# Dry-run
python scripts/export_qwen3_openvino.py --preset qwen3-asr-0.6b

# Real export
python scripts/export_qwen3_openvino.py --preset qwen3-asr-0.6b --execute

# Dry-run custom exporter
python -m scripts.export_qwen3_custom_openvino --preset qwen3-asr-0.6b

# Real custom export
python -m scripts.export_qwen3_custom_openvino --preset qwen3-asr-0.6b --execute
```

Note: `--execute` requires installed export toolchain (`transformers`, `optimum`, `optimum-intel`);
in a runtime-only environment, dry-run may return `support_probe.status=import_error`.

### Voice support probe + matrix

```powershell
# Probe current env
python scripts/probe_qwen3_voice_support.py

# Matrix dry-run / execute
python scripts/qwen3_voice_probe_matrix.py
python scripts/qwen3_voice_probe_matrix.py --execute
```

Expected result:

* `runs/<timestamp>-qwen3-voice-probe/` is created.
* We check `qwen3_asr` only for upstream-monitoring archived path.

### Isolated upstream experiment

`qwen3-tts` experimental `.venv-exp` environment has been removed from the active path.
If you need to check the upstream again, create a new isolated environment manually.

### Model cache cleanup (disk pressure)

```powershell
Remove-Item models\hf_cache -Recurse -Force
Remove-Item models\qwen3-vl-4b-instruct-ov-custom -Recurse -Force
Remove-Item models\qwen2.5-vl-7b-instruct-int4-ov -Recurse -Force
Remove-Item "$env:USERPROFILE\.cache\huggingface" -Recurse -Force
```

## OpenVINO: setup + diagnostics

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install "openvino==2026.0.0" "openvino-genai==2026.0.0.0"
python -c "import openvino as ov; core=ov.Core(); print('openvino=', ov.__version__); print('devices=', core.available_devices)"
python scripts/openvino_diag.py
```

Expected result:

* `openvino_diag_all_devices.json` was created in `runs/<timestamp>-openvino/`.

## M3.1: Text core demo (OpenVINO GenAI + Qwen3-8B profile)

Runtime deps installation:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install "openvino==2026.0.0" "openvino-genai==2026.0.0.0"
```

Run demo:

```powershell
python scripts/text_core_openvino_demo.py --model-dir models\qwen3-8b-int4-cw-ov --prompt "Give me a short ATM10 starter plan" --device NPU
```

Expected result:

* `runs/<timestamp>-text-core-openvino/` is created.
* Inside there are `run.json` and `response.json`.

## M4: HUD OCR baseline (Tesseract CLI)

Note: This baseline requires system `tesseract` to be installed in `PATH`.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/hud_ocr_baseline.py --image-in "<path-to-hud-screenshot.png>" --lang eng --psm 6 --oem 1
```

Expected result:

* `runs/<timestamp>-hud-ocr/` is created.
* Inside there are `run.json`, `ocr.json`, `ocr.txt`.

## M4: HUD mod-hook baseline

Prepare payload JSON (example):

```json
{
  "event_ts": "2026-02-22T20:00:00+00:00",
  "source": "atm10_mod_hook",
  "hud_lines": ["Quest Updated", "Collect 16 wood"],
  "quest_updates": [{"id": "quest:start", "text": "Collect logs", "status": "active"}],
  "player_state": {"dimension": "minecraft:overworld", "x": 12, "y": 70, "z": -5, "health": 18.0},
  "context_tags": ["hud", "quest", "overlay"]
}
```

Launch:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/hud_mod_hook_baseline.py --hook-json "<path-to-hud-hook-payload.json>"
```

Expected result:

* `runs/<timestamp>-hud-hook/` is created.
* Inside there are `run.json`, `hook_raw.json`, `hook_normalized.json`, `hud_text.txt`.

## M3: Voice runtime demos (active path = Whisper GenAI ASR)

Installation of runtime deps (active path):

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Note: `qwen-tts` and `qwen-asr` are removed from the active stack.
Rollback to archived `qwen-asr` is only allowed temporarily and with explicit opt-in flags.

### ASR demo (archived qwen3-asr path)

```powershell
# File -> text
python scripts/asr_demo.py --allow-archived-qwen-asr --audio-in "<path-to-sample.wav>"

# Microphone -> text (5s)
python scripts/asr_demo.py --allow-archived-qwen-asr --record-seconds 5
```

Expected result:

* `runs/<timestamp>-asr-demo/` is created.
* Inside there are `run.json` and `transcription.json`.

### ASR demo (OpenVINO GenAI + Whisper v3 Turbo, NPU path)

Runtime deps installation:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pip install "openvino==2026.0.0" "openvino-genai==2026.0.0.0"
```

Preparing OpenVINO model Whisper v3 Turbo:

```powershell
optimum-cli export openvino --model openai/whisper-large-v3-turbo models\whisper-large-v3-turbo-ov
```

Run demo:

```powershell
# File -> text on NPU
python scripts/asr_demo_whisper_genai.py --model-dir models\whisper-large-v3-turbo-ov --audio-in "<path-to-sample.wav>" --device NPU

# Optional timestamps
python scripts/asr_demo_whisper_genai.py --model-dir models\whisper-large-v3-turbo-ov --audio-in "<path-to-sample.wav>" --device NPU --return-timestamps --word-timestamps
```

Expected result:

* `runs/<timestamp>-asr-whisper-genai/` is created.
* Inside there are `run.json` and `transcription.json`.

### Long-lived voice runtime service (ASR only)

```powershell
# Service start (default backend = whisper_genai)
python scripts/voice_runtime_service.py --host 127.0.0.1 --port 8765 --asr-model models\whisper-large-v3-turbo-ov

# Optional auth token hardening
$env:ATM10_SERVICE_TOKEN="<set-local-service-token>"
python scripts/voice_runtime_service.py --host 127.0.0.1 --port 8765 --asr-model models\whisper-large-v3-turbo-ov

# Health
python scripts/voice_runtime_client.py --service-url http://127.0.0.1:8765 health

# ASR request
python scripts/voice_runtime_client.py --service-url http://127.0.0.1:8765 asr --audio-in "<path-to-sample.wav>"
```

HTTP hardening defaults (voice service):

* `max_request_body_bytes = 262144`
* `max_json_depth = 8`
* `max_string_length = 8192`
* `max_array_items = 256`
* `max_object_keys = 256`
* optional `service_token` (`--service-token` or `ATM10_SERVICE_TOKEN`) -> require `X-ATM10-Token`
* non-loopback bind requires `--service-token` / `ATM10_SERVICE_TOKEN` unless `--allow-insecure-no-token` is passed explicitly

Payload-limit behavior:

* `payload_too_large` -> HTTP `413`
* `payload_limit_exceeded` -> HTTP `413`
* normal validation errors payload -> HTTP `400`

Note (security): in HTTP payload for `/tts` and `/tts_stream`, the `out_wav_path` field should only be the file name (without absolute path and directories). The service always writes TTS WAV to its `runs/<timestamp>-voice-service/tts_outputs/`.
Voice service error artifacts are sanitized by default; use `--unsafe-log-internal-errors` only for deliberate local debugging when raw traceback persistence is acceptable.

### Long-lived voice runtime service (Whisper GenAI + NPU ASR)

```powershell
# Service start with Whisper v3 Turbo OpenVINO model
python scripts/voice_runtime_service.py --host 127.0.0.1 --port 8765 --asr-backend whisper_genai --asr-model models\whisper-large-v3-turbo-ov --asr-device NPU --asr-task transcribe --asr-warmup-request --asr-warmup-language en --no-preload-asr --no-preload-tts

# Same profile with explicit HTTP limits
python scripts/voice_runtime_service.py --host 127.0.0.1 --port 8765 --asr-backend whisper_genai --asr-model models\whisper-large-v3-turbo-ov --asr-device NPU --asr-task transcribe --max-request-bytes 262144 --max-json-depth 8 --max-string-length 8192 --max-array-items 256 --max-object-keys 256

# Same profile via helper start script
pwsh -File scripts\start_voice_whisper_npu.ps1 -BindHost 127.0.0.1 -Port 8765 -AsrModelDir "models\whisper-large-v3-turbo-ov" -WarmupLanguage en

# Health
python scripts/voice_runtime_client.py --service-url http://127.0.0.1:8765 health

# ASR request
python scripts/voice_runtime_client.py --service-url http://127.0.0.1:8765 asr --audio-in "<path-to-sample.wav>" --language en
```

Note: `--asr-warmup-request` makes one ASR inference at the start (by default on the generated silence WAV, or through `--asr-warmup-audio`) and reduces the cold-start impact in the game loop.
While warmup is running, `/health` may be temporarily unavailable; this is normal for the startup phase.

### Optional rollback: archived qwen_asr service profile

```powershell
python scripts/voice_runtime_service.py --host 127.0.0.1 --port 8765 --asr-backend qwen_asr --allow-archived-qwen-asr --asr-model Qwen/Qwen3-ASR-0.6B
```

### ASR backend benchmark (active default = `whisper_genai`)

```powershell
# Example on the same WAV set
python scripts/benchmark_asr_backends.py `
  --inputs `
    runs\20260222_151611-voice-client\input_recorded.wav `
    runs\20260220_175616-asr-demo\input_recorded.wav `
    runs\20260220_211505-voice-latency-bench\asr_input.wav `
    runs\20260220_211708-voice-latency-oneshot-bench\asr_input.wav `
    runs\20260220_211505-voice-latency-bench\20260220_181617-voice-client\input_from_file.wav `
  --backends whisper_genai `
  --whisper-model-dir models\whisper-large-v3-turbo-ov `
  --whisper-device NPU

# Optional archived backend compare
python scripts/benchmark_asr_backends.py `
  --inputs runs\20260222_151611-voice-client\input_recorded.wav `
  --backends whisper_genai `
  --include-archived-qwen-asr `
  --whisper-model-dir models\whisper-large-v3-turbo-ov `
  --whisper-device NPU
```

Expected result:

* `runs/<timestamp>-asr-backend-bench/` is created.
* Inside there are `summary.json`, `summary.md`, `per_sample_results.jsonl`, `service_sla_summary.json`.
* `summary.json` uses `schema_version = asr_backend_benchmark_summary_v1`.
* `service_sla_summary.json` publishes the normalized `voice_asr` SLA row for the selected `--primary-backend`.

### TTS runtime service (separate process/container)

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pip install fastapi uvicorn
python scripts/tts_runtime_service.py --host 127.0.0.1 --port 8780 --runs-dir runs\tts-runtime
```

Optional local API docs (debug only):

```powershell
python scripts/tts_runtime_service.py --host 127.0.0.1 --port 8780 --runs-dir runs\tts-runtime --expose-openapi
```

Accepted runtime design:

* Router: FastAPI
* Main engine: XTTS v2
* Fallback engines: Piper, Silero (for `ru` service voice)
* Techniques: prewarm, queue, chunking, phrase cache, true streaming for `/tts_stream`
* HTTP hardening: payload limits (`max_request_bytes/json_depth/string/array/object`) + sanitized internal errors
* Optional auth hardening: `--service-token` or `ATM10_SERVICE_TOKEN` -> require `X-ATM10-Token`
* Non-loopback bind requires `--service-token` / `ATM10_SERVICE_TOKEN` unless `--allow-insecure-no-token` is passed explicitly
* `/docs` and `/openapi.json` are disabled by default; use `--expose-openapi` only for local loopback debugging

Minimum configuration of adapters (env):

```powershell
# XTTS v2
$env:XTTS_MODEL_NAME="tts_models/multilingual/multi-dataset/xtts_v2"
$env:XTTS_USE_GPU="false"
# optional cloning wav for XTTS
# $env:XTTS_DEFAULT_SPEAKER_WAV="<path-to-speaker.wav>"

# Piper fallback
$env:PIPER_EXECUTABLE="piper"
$env:PIPER_MODEL_PATH="<path-to-piper-model.onnx>"
# optional
# $env:PIPER_SPEAKER="0"

# Silero (ru service voice)
$env:SILERO_REPO_OR_DIR="snakers4/silero-models"
$env:SILERO_ALLOW_REMOTE_HUB="false"
# required only when using remote hub source with explicit opt-in
# $env:SILERO_REPO_REF="v4.1.0"
$env:SILERO_MODEL_LANGUAGE="ru"
$env:SILERO_MODEL_ID="v4_ru"
$env:SILERO_SAMPLE_RATE="24000"
$env:SILERO_SPEAKER="xenia"
```

Security policy for Silero source:

* Default mode expects local source (`SILERO_REPO_OR_DIR` as local path) and keeps remote hub disabled.
* Remote hub source requires explicit opt-in (`SILERO_ALLOW_REMOTE_HUB=true`) and pinned revision (`SILERO_REPO_REF` or `owner/repo:ref` in `SILERO_REPO_OR_DIR`).
* If secure Silero configuration is missing, `tts_runtime_service` still starts, but the `ru` service-voice fallback stays disabled until Silero is configured correctly.

Example TTS request:

```powershell
python scripts/tts_runtime_client.py --service-url http://127.0.0.1:8780 health
python scripts/tts_runtime_client.py --service-url http://127.0.0.1:8780 tts --text "crafting started" --language en
python scripts/tts_runtime_client.py --service-url http://127.0.0.1:8780 tts-stream --text "service message" --language ru --service-voice
```

### TTS runtime benchmark (in-process baseline)

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/benchmark_tts_runtime.py --manifest tests/fixtures/tts_benchmark_sample.jsonl --runs-dir runs\tts-runtime-bench
```

Expected result:

* `runs/<timestamp>-tts-runtime-bench/` is created.
* Inside there are `benchmark_plan.json`, `per_sample_results.jsonl`, `summary.json`, and `service_sla_summary.json`.
* `service_sla_summary.json` uses `service_sla_summary_v1` and publishes `voice_tts` baseline metrics including `non_empty_audio_rate`, `chunk_count_mean`, and `cache_hit_rate`.

Streaming behavior:

* `/tts_stream` sends NDJSON incrementally (`started -> audio_chunk -> completed`) without a full pre-buffer.
* `/tts` remains non-streaming and uses the same request/response contract.
* Internal 500 responses are always sanitized; details are written locally in `runs/<timestamp>-tts-service/service_errors.jsonl`.

### Voice latency benchmark (historical)

Historical artifacts of `Qwen3-TTS` are left for reference in `runs/*qwen3-tts*`.
For production game-loop this path is deactivated.

## M1: Phase A smoke

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/phase_a_smoke.py
# Strict mode (no fallback to stub)
python scripts/phase_a_smoke.py --vlm-provider openai --strict-vlm
```

Expected result:

* `runs/<timestamp>/` is created.
* Inside there are `screenshot.png`, `run.json`, `response.json`.
* In strict-mode, if VLM fails, `run.json` and `response.json` are still saved before non-zero exit.

## M2: FTB Quests normalization

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/normalize_ftbquests.py
```

Optional:

```powershell
python scripts/normalize_ftbquests.py --quests-dir "<path-to-ftbquests-quests-dir>"
```

## M2: Retrieval demo (in-memory)

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/retrieve_demo.py --profile baseline --in data/ftbquests_norm --query "steel tools"
```

Optionally, OV production profile:

```powershell
python scripts/retrieve_demo.py --profile ov_production --in data/ftbquests_norm --query "steel tools"
```

Optionally, manual override over profile:

```powershell
python scripts/retrieve_demo.py --profile ov_production --in data/ftbquests_norm --query "steel tools" --reranker-device NPU
```

## M2: Retrieval eval benchmark

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/eval_retrieval.py --profile baseline --docs tests/fixtures/retrieval_docs_sample.jsonl --eval tests/fixtures/retrieval_eval_sample.jsonl --topk 3 --candidate-k 50 --reranker none
```

Optionally, OV production profile:

```powershell
python scripts/eval_retrieval.py --profile ov_production --docs tests/fixtures/retrieval_docs_sample.jsonl --eval tests/fixtures/retrieval_eval_sample.jsonl
```

Expected result:

* `runs/<timestamp>/service_sla_summary.json` is written next to `eval_results.json`.
* `service_sla_summary.json` uses `service_sla_summary_v1` and normalizes `status`, latency, and quality fields (`mean_recall_at_k`, `mean_mrr_at_k`, `hit_rate_at_k`).

## M2: Qdrant ingest (optional backend)

```powershell
docker run --name atm10-qdrant -p 6333:6333 qdrant/qdrant
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/ingest_qdrant.py --in data/ftbquests_norm --collection atm10
```

## M2: Retrieval demo (qdrant backend)

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/retrieve_demo.py --backend qdrant --collection atm10 --query "steel tools" --topk 5
```

## M5: KAG baseline (file-based, no Neo4j)

### Build graph

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/kag_build_baseline.py --in data/ftbquests_norm/quests.jsonl
```

Expected result:

* `runs/<timestamp>-kag-build/` is created.
* Inside there are `run.json` and `kag_graph.json`.

### Query graph

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/kag_query_demo.py --graph runs\YYYYMMDD_HHMMSS-kag-build\kag_graph.json --query "steel tools"
```

Expected result:

* `runs/<timestamp>-kag-query/` is created.
* Inside there are `run.json` and `kag_query_results.json`.

## M5.1: KAG via Neo4j (approved transition)

### Start Neo4j locally

```powershell
$env:NEO4J_PASSWORD="<set-local-neo4j-password>"
docker run --name atm10-neo4j -p 7474:7474 -p 7687:7687 `
  -e "NEO4J_AUTH=neo4j/$($env:NEO4J_PASSWORD)" `
  neo4j:5
```

### Sync `kag_graph.json` to Neo4j

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="<set-local-neo4j-password>"
python scripts/kag_sync_neo4j.py `
  --graph runs\YYYYMMDD_HHMMSS-kag-build\kag_graph.json `
  --neo4j-url http://127.0.0.1:7474 `
  --neo4j-database neo4j `
  --neo4j-user neo4j `
  --reset-graph
```

Expected result:

* `runs/<timestamp>-kag-sync-neo4j/` is created.
* Inside there are `run.json` and `neo4j_sync_summary.json`.

### Query KAG directly from Neo4j

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="<set-local-neo4j-password>"
python scripts/kag_query_neo4j.py `
  --query "steel tools" `
  --topk 5 `
  --neo4j-url http://127.0.0.1:7474 `
  --neo4j-database neo4j `
  --neo4j-user neo4j
```

Expected result:

* `runs/<timestamp>-kag-query-neo4j/` is created.
* Inside there are `run.json` and `kag_query_results.json`.

## M5.2: KAG Neo4j benchmark (quality + latency)

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="<set-local-neo4j-password>"
python scripts/eval_kag_neo4j.py `
  --eval tests/fixtures/kag_neo4j_eval_sample.jsonl `
  --topk 5 `
  --warmup-runs 1 `
  --neo4j-url http://127.0.0.1:7474 `
  --neo4j-database neo4j `
  --neo4j-user neo4j
```

Expected result:

* `runs/<timestamp>-kag-neo4j-eval/` is created.
* Inside there are `run.json`, `eval_results.json`, `summary.md`, `service_sla_summary.json`.
* `eval_results.json` has:
  * `mean_recall_at_k`
  * `mean_mrr_at_k`
  * `hit_rate_at_k`
  * `latency_mean_ms`, `latency_p50_ms`, `latency_p95_ms`, `latency_max_ms`
* `service_sla_summary.json` uses the same normalized `service_sla_summary_v1` contract as the file-backed KAG baseline and cross-service suite.
* `--warmup-runs` makes N full warmup passes through the eval set before the measured run.
  Warmup requests are not included in per-case latency and final metrics, but are recorded in `run.json.warmup`.

### KAG file eval baseline

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/eval_kag_file.py --docs tests/fixtures/kag_neo4j_docs_sample.jsonl --eval tests/fixtures/kag_neo4j_eval_sample.jsonl --topk 5 --runs-dir runs\kag-file-eval
```

Expected result:

* `runs/<timestamp>-kag-file-eval/` is created.
* Inside there are `run.json`, `kag_graph.json`, `eval_results.json`, `summary.md`, and `service_sla_summary.json`.
* `eval_results.json` uses the same metric shape as `eval_kag_neo4j.py`, but with `backend = file`.
* `service_sla_summary.json` publishes the normalized `kag_file` row used by the cross-service benchmark suite.

### Hard-cases benchmark

Nightly hard profile (recommended): use `--warmup-runs 1` as default.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="<set-local-neo4j-password>"
python scripts/eval_kag_neo4j.py `
  --eval tests/fixtures/kag_neo4j_eval_hard.jsonl `
  --topk 5 `
  --warmup-runs 1 `
  --neo4j-url http://127.0.0.1:7474 `
  --neo4j-database neo4j `
  --neo4j-user neo4j
```

### Canonical guardrail thresholds (sample + hard)

Threshold profiles:

* `sample`: `recall@k >= 1.0`, `mrr@k >= 0.80`, `hit-rate@k >= 1.0`, `latency_p95_ms <= 120`
* `hard`: `recall@k >= 1.0`, `mrr@k >= 0.90`, `hit-rate@k >= 1.0`, `latency_p95_ms <= 130`

Checking sample-run:

```powershell
python scripts/check_kag_neo4j_guardrail.py --profile sample --eval-results-json "runs\YYYYMMDD_HHMMSS-kag-neo4j-eval\eval_results.json"
```

Hard-run check:

```powershell
python scripts/check_kag_neo4j_guardrail.py --profile hard --eval-results-json "runs\YYYYMMDD_HHMMSS-kag-neo4j-eval\eval_results.json"
```

## M5.3: KAG guardrail nightly workflow

Nightly workflow file:

* `.github/workflows/kag-neo4j-guardrail-nightly.yml`

Workflow steps:

* `kag_build_baseline` on fixture docs `tests/fixtures/kag_neo4j_docs_sample.jsonl`
* `kag_sync_neo4j` to local Neo4j service
* `eval_kag_neo4j` for `sample` + `hard` (both with `--warmup-runs 1`)
* `check_kag_neo4j_guardrail.py` for `sample` + `hard`
* `kag_guardrail_trend_snapshot.py` for latest/history trend (`sample` vs `hard`)
* upload run artifacts + step summary (guardrail table + trend snapshot)

Trend snapshot manual run (optional):

```powershell
python scripts/kag_guardrail_trend_snapshot.py --sample-runs-dir runs/nightly-kag-eval-sample --hard-runs-dir runs/nightly-kag-eval-hard --history-limit 10 --baseline-window 5 --critical-policy signal_only --runs-dir runs/nightly-kag-trend
```

Trend snapshot with explicit severity thresholds (optional):

```powershell
python scripts/kag_guardrail_trend_snapshot.py --sample-runs-dir runs/nightly-kag-eval-sample --hard-runs-dir runs/nightly-kag-eval-hard --history-limit 10 --baseline-window 5 --mrr-warn-delta 0.005 --mrr-critical-delta 0.02 --latency-warn-delta-ms 5.0 --latency-critical-delta-ms 15.0 --runs-dir runs/nightly-kag-trend
```

Trend snapshot with fail-nightly policy on critical severity (opt-in):

```powershell
python scripts/kag_guardrail_trend_snapshot.py --sample-runs-dir runs/nightly-kag-eval-sample --hard-runs-dir runs/nightly-kag-eval-hard --history-limit 10 --baseline-window 5 --critical-policy fail_nightly --runs-dir runs/nightly-kag-trend
```

Expected result:

* `runs/<timestamp>-kag-guardrail-trend/` is created.
* Inside there are `run.json`, `trend_snapshot.json`, `summary.md`.
* In `trend_snapshot.json` there is `rolling_baseline` by `sample`/`hard` (latest vs mean previous N runs).
* `rolling_baseline.regression_flags` records the `mrr`/`latency_p95` (`improved|stable|regressed|insufficient_history`) and severity (`none|warn|critical`) statuses with the `max_regression_severity` aggregate.
* The accepted policy (`signal_only|fail_nightly`) and `critical_profiles` are recorded in `trend_snapshot.json.critical_policy`.
* Nightly baseline policy: `signal_only` (critical severity is signaled in summary/artifacts and does not fail jobs).
* The optional `fail_nightly` mode is only available as an explicit opt-in to tighten the guardrail.

### Warmup A/B compare (mini benchmark)

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="<set-local-neo4j-password>"
python scripts/compare_kag_neo4j_warmup.py `
  --eval tests/fixtures/kag_neo4j_eval_hard.jsonl `
  --repeats 3 `
  --baseline-warmup-runs 0 `
  --candidate-warmup-runs 1 `
  --topk 5 `
  --neo4j-url http://127.0.0.1:7474 `
  --neo4j-database neo4j `
  --neo4j-user neo4j
```

Expected result:

* `runs/<timestamp>-kag-neo4j-warmup-compare/` is created.
* Inside there are `run.json`, `summary.json`, `summary.md`.
* `summary.json.delta.p95_improvement_ms > 0` means that the candidate profile is faster than the baseline according to p95.

## M6: Automation scaffold (dry-run only)

Important: this entrypoint does not execute real keyboard/mouse events. It only validates the plan and writes dry-run artifacts.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/automation_dry_run.py --plan-json "<path-to-automation-plan.json>"
```

Example `automation_plan.json`:

```json
{
  "schema_version": "automation_plan_v1",
  "intent": {
    "goal": "open quest book and inspect active objective",
    "priority": "normal",
    "tags": ["quests", "ui"],
    "constraints": ["dry_run_only"]
  },
  "context": {
    "source": "manual_hotkey",
    "note": "open quest book and wait"
  },
  "planning": {
    "intent_type": "open_quest_book",
    "intent_id": "intent-123",
    "trace_id": "trace-xyz",
    "intent_schema_version": "automation_intent_v1",
    "adapter_name": "intent_to_automation_plan",
    "adapter_version": "v1"
  },
  "actions": [
    {"type": "key_tap", "key": "l"},
    {"type": "wait", "duration_ms": 250, "repeats": 2},
    {"type": "mouse_click", "button": "left", "x": 1200, "y": 640}
  ]
}
```

Canonical demo scenarios (fixtures):

* `tests/fixtures/automation_plan_quest_book.json`
* `tests/fixtures/automation_plan_inventory_check.json`

Example of running fixture scripts:

```powershell
python scripts/automation_dry_run.py --plan-json "tests/fixtures/automation_plan_quest_book.json"
python scripts/automation_dry_run.py --plan-json "tests/fixtures/automation_plan_inventory_check.json"
```

Expected result:

* `runs/<timestamp>-automation-dry-run/` is created.
* Inside there are `run.json`, `actions_normalized.json`, `execution_plan.json`.
* `run.json.result.dry_run=true`, no system input events are sent.

## M6.3: Intent -> automation_plan adapter (dry-run only)

Important: adapter only builds `automation_plan_v1` from intent payload and saves artifacts. There are no real input events.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/intent_to_automation_plan.py --intent-json "tests/fixtures/intent_open_quest_book.json"
```

Expected result:

* `runs/<timestamp>-intent-to-automation-plan/` is created.
* Inside there are `run.json` and `automation_plan.json`.
* `run.json.result.dry_run_only=true`.
* `automation_plan.json` has `planning` metadata (`intent_type`, `intent_schema_version`, `adapter_name`, `adapter_version`; optional `intent_id/trace_id`).

End-to-end check via existing dry-run runner:

```powershell
python scripts/intent_to_automation_plan.py --intent-json "tests/fixtures/intent_open_quest_book.json" --plan-out "runs\m6_3_intent_plan.json"
python scripts/automation_dry_run.py --plan-json "runs\m6_3_intent_plan.json"
```

## M6.4: Unified smoke chain (`intent -> plan -> automation_dry_run`)

Single smoke entrypoint for dry-run chain.

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python scripts/automation_intent_chain_smoke.py --intent-json "tests/fixtures/intent_open_quest_book.json"
python scripts/automation_intent_chain_smoke.py --intent-json "tests/fixtures/intent_check_inventory_tool.json"
python scripts/automation_intent_chain_smoke.py --intent-json "tests/fixtures/intent_open_world_map.json"
```

Expected result:

* `runs/<timestamp>-automation-intent-chain-smoke/` is created.
* Inside there is:
  * `run.json`
  * `chain_summary.json`
  * `automation_plan.json`
  * `child_runs/` (adapter + dry-run child artifacts)
* `run.json.result.dry_run_only=true`.

## M6.6: CI acceptance thresholds for automation smoke

Dry-run smoke contract:

```powershell
python scripts/check_automation_smoke_contract.py --mode dry_run --runs-dir runs/ci-smoke-automation-dry-run --min-action-count 3 --min-step-count 4
```

Intent-chain smoke contract:

```powershell
python scripts/check_automation_smoke_contract.py --mode intent_chain --runs-dir runs/ci-smoke-automation-chain --min-action-count 3 --min-step-count 4 --expected-intent-type open_quest_book --require-trace-id --require-intent-id
python scripts/check_automation_smoke_contract.py --mode intent_chain --runs-dir runs/ci-smoke-automation-chain-inventory --min-action-count 3 --min-step-count 4 --expected-intent-type check_inventory_tool --require-trace-id --require-intent-id
python scripts/check_automation_smoke_contract.py --mode intent_chain --runs-dir runs/ci-smoke-automation-chain-open-world-map --min-action-count 3 --min-step-count 4 --expected-intent-type open_world_map --require-trace-id --require-intent-id
```

Machine-readable summary output:

```powershell
python scripts/check_automation_smoke_contract.py --mode dry_run --runs-dir runs/ci-smoke-automation-dry-run --min-action-count 3 --min-step-count 4 --summary-json runs/ci-smoke-automation-dry-run/contract_summary.json
python scripts/check_automation_smoke_contract.py --mode intent_chain --runs-dir runs/ci-smoke-automation-chain --min-action-count 3 --min-step-count 4 --expected-intent-type open_quest_book --require-trace-id --require-intent-id --summary-json runs/ci-smoke-automation-chain/contract_summary.json
python scripts/check_automation_smoke_contract.py --mode intent_chain --runs-dir runs/ci-smoke-automation-chain-inventory --min-action-count 3 --min-step-count 4 --expected-intent-type check_inventory_tool --require-trace-id --require-intent-id --summary-json runs/ci-smoke-automation-chain-inventory/contract_summary.json
python scripts/check_automation_smoke_contract.py --mode intent_chain --runs-dir runs/ci-smoke-automation-chain-open-world-map --min-action-count 3 --min-step-count 4 --expected-intent-type open_world_map --require-trace-id --require-intent-id --summary-json runs/ci-smoke-automation-chain-open-world-map/contract_summary.json
```

Expected result:

* Both check scripts end with `status=ok`.
* In `--summary-json`, the `observed` field includes optional trace-correlation metadata:
  * `trace_id`, `intent_id` (if they are in `planning` action-plan metadata).
* For intent-chain canonical fixtures, `--require-trace-id` and `--require-intent-id` are used; the absence of any of the id is considered a contract violation.
* In CI, these ids stay in the machine-readable contract summaries; the public `Automation Smoke Contracts` step summary remains coarse and does not display `trace_id/intent_id`.
* Any violation of the contract (missing artifact/metrics below the threshold/intent mismatch) gives a non-zero exit code.

## M6.19: New intent template rollout policy (CI)

Policy checklist for each new `intent_type`:

1. Add canonical fixture:
   * `tests/fixtures/intent_<new_intent_type>.json`
   * fixture must include `intent_id` and `trace_id`.
2. Add smoke run step:
   * `python scripts/automation_intent_chain_smoke.py --intent-json tests/fixtures/intent_<new_intent_type>.json --runs-dir runs/ci-smoke-automation-chain-<new_intent_type>`
3. Add contract-check step:
   * `python scripts/check_automation_smoke_contract.py --mode intent_chain --runs-dir runs/ci-smoke-automation-chain-<new_intent_type> --min-action-count 3 --min-step-count 4 --expected-intent-type <new_intent_type> --require-trace-id --require-intent-id --summary-json runs/ci-smoke-automation-chain-<new_intent_type>/contract_summary.json`
4. Add summary/artifact wiring:
   * new line in `Automation Smoke Contracts` summary table;
   * new `contract_summary.json` in upload artifact path.
5. Add regression test:
   * at least 1 pytest on e2e dry-run chain for a new fixture.

## M6.19 rollout records

The public intent -> plan -> dry-run chain has now been exercised on three canonical fixtures:

* `open_quest_book`
* `check_inventory_tool`
* `open_world_map`

`open_world_map` is the latest added template and the clearest example of the checklist-complete rollout path. Each record uses the same public-safe sequence: canonical fixture -> smoke run -> contract check.

## M6.8: Troubleshooting automation smoke contract failures (CI)

Quick checklist when `check_automation_smoke_contract` crashes:

1. Check summary artifacts:
   * `runs/ci-smoke-automation-dry-run/contract_summary.json`
   * `runs/ci-smoke-automation-chain/contract_summary.json`
2. Check field `violations` and `error` in summary JSON:
   * `error != null` usually points to a missing artifact path.
   * `violations` contains a specific contract that has failed.
3. Check minimum thresholds in workflow:
   * `min_action_count=3`, `min_step_count=4`
   * for chain additionally `expected_intent_type` for the corresponding fixture (`open_quest_book`, `check_inventory_tool`, `open_world_map`)
4. Rerun locally the same CI commands:
   * `automation_dry_run` + `check_automation_smoke_contract --mode dry_run`
   * `automation_intent_chain_smoke` + `check_automation_smoke_contract --mode intent_chain`
5. If the problem is in artifacts:
   * make sure the smoke script has completed `status=ok` to `run.json`
   * check that the paths in `--runs-dir` match between smoke step and check step
6. If the problem is `intent_type`:
   * check fixture (`tests/fixtures/intent_open_quest_book.json`, `tests/fixtures/intent_check_inventory_tool.json`, `tests/fixtures/intent_open_world_map.json`)
   * check `automation_plan.json.context.intent_type` in chain run artifacts
