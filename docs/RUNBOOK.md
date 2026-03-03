# RUNBOOK

## M0: Instance discovery

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/discover_instance.py
```

Ожидаемый результат:

* Создается `runs/<timestamp>/instance_paths.json`.
* В консоль печатается summary по найденным путям и marker-папкам.

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
python scripts/dependency_audit.py --runs-dir runs --policy report_only --with-security-scan true

# Nightly/security gate profile
python scripts/dependency_audit.py --runs-dir runs/nightly-security-audit --policy fail_on_critical --with-security-scan true
```

CI note:

* PR pipeline keeps `report_only` dependency audit signal.
* Nightly security workflow (`.github/workflows/security-nightly.yml`) runs `fail_on_critical` policy.

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
python scripts/gateway_v1_smoke.py --scenario automation --runs-dir runs/ci-smoke-gateway-automation --summary-json runs/ci-smoke-gateway-automation/gateway_smoke_summary.json
python scripts/gateway_v1_http_smoke.py --scenario core --runs-dir runs/ci-smoke-gateway-http-core --summary-json runs/ci-smoke-gateway-http-core/gateway_http_smoke_summary.json
python scripts/gateway_v1_http_smoke.py --scenario automation --runs-dir runs/ci-smoke-gateway-http-automation --summary-json runs/ci-smoke-gateway-http-automation/gateway_http_smoke_summary.json
python scripts/check_gateway_sla.py --http-summary-json runs/ci-smoke-gateway-http-core/gateway_http_smoke_summary.json --summary-json runs/ci-smoke-gateway-sla/gateway_sla_summary.json --profile conservative --policy signal_only --runs-dir runs/ci-smoke-gateway-sla
python scripts/gateway_sla_trend_snapshot.py --sla-runs-dir runs/ci-smoke-gateway-sla --history-limit 10 --baseline-window 5 --critical-policy signal_only --runs-dir runs/ci-smoke-gateway-sla-trend
python scripts/streamlit_operator_panel_smoke.py --panel-runs-dir runs --runs-dir runs/ci-smoke-streamlit --summary-json runs/ci-smoke-streamlit/streamlit_smoke_summary.json --gateway-url http://127.0.0.1:8770 --startup-timeout-sec 45 --viewport-width 390 --viewport-height 844 --compact-breakpoint-px 768
```

Ожидаемый результат:

* Для core smoke шагов создаются machine-readable summaries:
  * `runs/ci-smoke-phase-a/smoke_summary.json`
  * `runs/ci-smoke-retrieve/smoke_summary.json`
  * `runs/ci-smoke-eval/smoke_summary.json`
* Для automation smoke шагов создаются contract summaries:
  * `runs/ci-smoke-automation-dry-run/contract_summary.json`
  * `runs/ci-smoke-automation-chain/contract_summary.json`
  * `runs/ci-smoke-automation-chain-inventory/contract_summary.json`
  * `runs/ci-smoke-automation-chain-open-world-map/contract_summary.json`
* Для gateway smoke шагов создаются machine-readable summaries:
  * `runs/ci-smoke-gateway-core/gateway_smoke_summary.json`
  * `runs/ci-smoke-gateway-automation/gateway_smoke_summary.json`
* Для gateway HTTP smoke шагов создаются machine-readable summaries:
  * `runs/ci-smoke-gateway-http-core/gateway_http_smoke_summary.json`
  * `runs/ci-smoke-gateway-http-automation/gateway_http_smoke_summary.json`
* Для gateway SLA check создается machine-readable summary:
  * `runs/ci-smoke-gateway-sla/gateway_sla_summary.json`
* Для gateway SLA trend snapshot создаются machine-readable artifacts:
  * `runs/ci-smoke-gateway-sla-trend/<timestamp>-gateway-sla-trend/gateway_sla_trend_snapshot.json`
  * `runs/ci-smoke-gateway-sla-trend/<timestamp>-gateway-sla-trend/summary.md`
* Для streamlit smoke создается machine-readable summary:
  * `runs/ci-smoke-streamlit/streamlit_smoke_summary.json`

## M7.0: Gateway v1 local contract runner

Локальный gateway path фиксирует request/response contract без HTTP-транспорта и без новых dependencies.

### Single request (CLI)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/gateway_v1_local.py --request-json "C:\path\to\gateway_request.json" --runs-dir runs\gateway-local
```

Пример `gateway_request.json`:

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

Ожидаемый результат:

* Создается `runs/<timestamp>-gateway-v1/`.
* Внутри есть `request.json`, `run.json`, `response.json`, `child_runs/`.
* `request.json` сохраняется в redacted-виде (без plaintext секретов).
* В `run.json` публикуется `request_redaction` (`applied`, `fields_redacted`, checklist version).
* `response.json.schema_version = gateway_response_v1`.
* Для `retrieval_query` + `reranker=qwen3` `payload.reranker_model` ограничен allowlist:
  * `Qwen/Qwen3-Reranker-0.6B`
  * `OpenVINO/Qwen3-Reranker-0.6B-fp16-ov`
  * override только через `ATM10_ALLOW_UNTRUSTED_RERANKER_MODEL=true` (trusted-only).

### Gateway smoke scenarios

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/gateway_v1_smoke.py --scenario core --runs-dir runs\ci-smoke-gateway-core --summary-json runs\ci-smoke-gateway-core\gateway_smoke_summary.json
python scripts/gateway_v1_smoke.py --scenario automation --runs-dir runs\ci-smoke-gateway-automation --summary-json runs\ci-smoke-gateway-automation\gateway_smoke_summary.json
```

Ожидаемый результат:

* `core` сценарий проверяет `health`, `retrieval_query`, `kag_query` (`backend=file`).
* `automation` сценарий проверяет `automation_dry_run` через fixture.
* В каждом `--summary-json` фиксируется `status=ok|error`; любой `error` возвращает non-zero exit code.

## M7.1/M7.2: Gateway v1 HTTP transport + hardening

HTTP слой использует тот же dispatcher `run_gateway_request`, поэтому body-контракт совпадает с CLI gateway.

### Service start (FastAPI)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/gateway_v1_http_service.py --host 127.0.0.1 --port 8770 --runs-dir runs\gateway-http
```

Запуск с override policy (пример):

```powershell
python scripts/gateway_v1_http_service.py --host 127.0.0.1 --port 8770 --runs-dir runs\gateway-http --max-request-bytes 262144 --max-json-depth 8 --max-string-length 8192 --max-array-items 256 --max-object-keys 256 --operation-timeout-sec 15.0 --error-log-max-bytes 1048576 --error-log-max-files 5 --artifact-retention-days 14 --enable-error-redaction true
```

Опциональный auth-token hardening:

```powershell
# Token может быть передан флагом или через env ATM10_SERVICE_TOKEN
python scripts/gateway_v1_http_service.py --host 127.0.0.1 --port 8770 --runs-dir runs\gateway-http --service-token "change-me"
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

Проверка transport health:

```powershell
python -c "import requests; print(requests.get('http://127.0.0.1:8770/healthz', timeout=10).json())"
```

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

* Клиент получает только sanitized envelope (без traceback/внутренних деталей).
* При включенном `service-token` все HTTP endpoints требуют `X-ATM10-Token`.
* Перед записью error JSONL применяется redaction checklist `gateway_error_redaction_v1` (key-based + text pattern masking).
* Error лог ротируется по лимитам (`gateway_http_errors.jsonl`, `gateway_http_errors.1.jsonl`, ...).
* На startup выполняется retention cleanup:
  * `gateway_http_errors*.jsonl`
  * директории `runs/.../*-gateway-v1*` старше retention window.
* В каждой JSONL записи добавляются machine-readable metadata:
  * `redaction.checklist_version|applied|fields_redacted`
  * `retention_policy.artifact_retention_days|error_log_max_bytes|error_log_max_files`.

### HTTP smoke scenarios

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/gateway_v1_http_smoke.py --scenario core --runs-dir runs\ci-smoke-gateway-http-core --summary-json runs\ci-smoke-gateway-http-core\gateway_http_smoke_summary.json
python scripts/gateway_v1_http_smoke.py --scenario automation --runs-dir runs\ci-smoke-gateway-http-automation --summary-json runs\ci-smoke-gateway-http-automation\gateway_http_smoke_summary.json
```

Ожидаемый результат:

* В `core` проходят операции `health`, `retrieval_query`, `kag_query(file)`.
* В `automation` проходит `automation_dry_run`.
* Любой error в gateway body/HTTP статусе делает smoke `status=error` и non-zero exit code.

## M7.post: Gateway SLA/Observability baseline

На шаге `M7.post` SLA и observability строятся поверх HTTP smoke summary без изменения
`gateway_request_v1/gateway_response_v1`.

### SLA checker

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla.py --http-summary-json runs\ci-smoke-gateway-http-core\gateway_http_smoke_summary.json --summary-json runs\ci-smoke-gateway-sla\gateway_sla_summary.json --profile conservative --policy signal_only
```

SLA summary contract (`gateway_sla_summary_v1`):

* `schema_version = gateway_sla_summary_v1`
* `status = ok|error` (`error` только для execution/contract ошибок checker)
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

* `signal_only`: `0` даже при `sla_status=breach`.
* `fail_on_breach`: `2` при `sla_status=breach`.
* Любая execution/contract ошибка checker: `2`.

History mode (`--runs-dir`):

* При передаче `--runs-dir` checker создает `runs/<timestamp>-gateway-sla-check/`.
* В run-директории пишутся:
  * `run.json`
  * `gateway_sla_summary.json` (history copy для trend scanner).
* Основной `--summary-json` продолжает работать как latest summary path для CI.

## M7.post: Gateway SLA trend snapshot (rolling baseline + breach drift)

Trend layer рассчитывается поверх history из `gateway_sla_summary_v1` без изменения базового SLA контракта.

```powershell
cd D:\atm10-agent
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

* `signal_only`: `0` при валидном snapshot, даже при регрессиях.
* `fail_nightly`: `2`, если обнаружена `critical` severity.

## G2: Gateway SLA fail_nightly readiness (staged report)

Readiness слой оценивает готовность перехода trend policy с `signal_only` на `fail_nightly`
без включения hard-gate в этой итерации.

```powershell
cd D:\atm10-agent
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

* Используются валидные trend snapshots (`gateway_sla_trend_snapshot_v1`, `status=ok`).
* Берутся последние `N=14` валидных snapshots после `history_limit=30`.
* Переход считается `ready`, только если одновременно:
  * `window_observed >= 14`
  * `critical_count == 0`
  * `warn_ratio <= 0.20`
  * `insufficient_history_count == 0`
  * `invalid_or_error_count == 0`
* Snapshot severity считается как max:
  * `rolling_baseline.regression_flags.max_regression_severity`
  * `breach_drift.breach_rate_severity`

Exit policy:

* `report_only`: `0` при `status=ok` даже если `readiness_status=not_ready`; `2` только на execution/contract error.
* `fail_if_not_ready`: `2` при `status=error` или `readiness_status=not_ready`.

Nightly workflow:

* `.github/workflows/gateway-sla-readiness-nightly.yml`
* История SLA/trend/readiness/governance/progress сохраняется между nightly запусками через cache:
  * `runs/nightly-gateway-sla-history`
  * `runs/nightly-gateway-sla-trend-history`
  * `runs/nightly-gateway-sla-readiness`
  * `runs/nightly-gateway-sla-governance`
  * `runs/nightly-gateway-sla-progress`
* Nightly публикует:
  * `runs/nightly-gateway-sla-readiness/readiness_summary.json`
  * summary section `Gateway SLA Fail-Nightly Readiness`
  * artifacts `runs/nightly-gateway-*`.

## G2.1: Gateway SLA fail_nightly governance (go/no-go)

Governance слой формализует решение `go|hold` для переключения trend policy на `fail_nightly`
после накопления nightly readiness history.

```powershell
cd D:\atm10-agent
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
  * при наличии history rows top-level latest alias исключается из history scan (чтобы не было double-count);
    если history rows еще нет, используется legacy fallback по top-level latest alias.
* Для valid row требуется:
  * `status=ok`
  * `readiness_status in {ready, not_ready}`
  * criteria match:
    * `readiness_window == 14`
    * `required_baseline_count == 5`
    * `max_warn_ratio == 0.20` (float epsilon check)
* После `history_limit=60` берется хвост истории.
* `decision_status=go` только если:
  * latest readiness = `ready`
  * latest ready streak `>= 3`
  * `invalid_or_mismatched_count == 0`
* Иначе `decision_status=hold`.

Exit policy:

* `report_only`: `0` при `status=ok` независимо от `go|hold`; `2` только на execution/contract error.
* `fail_if_not_go`: `2` при `decision_status=hold` или `status=error`.

Nightly governance integration:

* `.github/workflows/gateway-sla-readiness-nightly.yml` добавляет:
  * governance step (report_only),
  * summary section `Gateway SLA Fail-Nightly Governance`,
  * artifacts `runs/nightly-gateway-sla-governance`.

## G2.2: Gateway SLA fail_nightly progress summary (nightly decision tracking)

Progress слой агрегирует readiness+governance историю и показывает, сколько еще
nightly сигналов нужно до потенциального `go` решения.

```powershell
cd D:\atm10-agent
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

* Source-of-truth: валидные readiness/governance summaries:
  * latest aliases:
    * `runs/nightly-gateway-sla-readiness/readiness_summary.json`
    * `runs/nightly-gateway-sla-governance/governance_summary.json`
  * history rows:
    * `runs/nightly-gateway-sla-readiness/<timestamp>-gateway-sla-fail-readiness/readiness_summary.json`
    * `runs/nightly-gateway-sla-governance/<timestamp>-gateway-sla-governance/governance_summary.json`
  * при наличии history rows top-level latest aliases исключаются из history scan; при legacy layout
    (history rows еще нет) используется fallback на top-level latest aliases.
* Для valid rows обязательно criteria match с ожидаемым baseline
  (`window=14`, `required_baseline_count=5`, `max_warn_ratio=0.20`, `required_ready_streak=3`).
* `decision_status=go` только если latest governance = `go`
  и `invalid_or_mismatched_count(governance)=0`.
* `remaining_for_window` и `remaining_for_streak` считаются по latest readiness/history
  и используются как операционный индикатор прогресса.

Exit policy:

* `report_only`: `0` при `status=ok` независимо от `go|hold`; `2` только на execution/contract error.
* `fail_if_not_go`: `2` при `decision_status=hold` или `status=error`.

Nightly progress integration:

* `.github/workflows/gateway-sla-readiness-nightly.yml` добавляет:
  * progress step (report_only),
  * summary section `Gateway SLA Fail-Nightly Progress`,
  * artifacts `runs/nightly-gateway-sla-progress`.

## G2.manual: UTC preflight перед manual `workflow_dispatch`

Helper проверяет calendar-day guardrail до ручного запуска nightly workflow.
Важно: скрипт не запускает dispatch, только выдает decision summary.

```powershell
cd D:\atm10-agent
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
  * `token_env`
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

* `accounted_dispatch_allowed=true` -> можно выполнять следующий учитываемый dispatch в текущие UTC-сутки.
* `accounted_dispatch_allowed=false` + `reason_codes=["utc_day_quota_exhausted"]` ->
  новый учитываемый run блокируется до `next_accounted_dispatch_at_utc`.
* `policy=fail_if_blocked` возвращает `exit_code=2`, когда guardrail блокирует запуск.

## G2.3: Gateway SLA fail_nightly transition gate (strict switch control)

Transition checker восстанавливает формальный switch-gate для nightly strict path
без изменения PR/CI `signal_only` policy.

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/check_gateway_sla_fail_nightly_transition.py --readiness-runs-dir runs/nightly-gateway-sla-readiness --governance-runs-dir runs/nightly-gateway-sla-governance --progress-runs-dir runs/nightly-gateway-sla-progress --readiness-history-limit 60 --governance-history-limit 60 --progress-history-limit 60 --expected-readiness-window 14 --expected-required-baseline-count 5 --expected-max-warn-ratio 0.20 --required-ready-streak 3 --policy report_only --runs-dir runs/nightly-gateway-sla-transition --summary-json runs/nightly-gateway-sla-transition/transition_summary.json
```

Nightly transition integration:

* `.github/workflows/gateway-sla-readiness-nightly.yml` добавляет:
  * step `Transition - Gateway SLA fail_nightly switch gate (report_only)`,
  * step `Resolve - Gateway SLA transition gate`,
  * conditional strict step `gateway_sla_trend_snapshot --critical-policy fail_nightly` только при `allow_switch=true`,
  * summary section `Gateway SLA Fail-Nightly Transition`,
  * cache/artifact path `runs/nightly-gateway-sla-transition`.

Recovery rule (calendar-day guardrail compatible):

* Если в успешном UTC-run отсутствует `runs/nightly-gateway-sla-transition/transition_summary.json`,
  разрешен один recovery rerun в те же UTC-сутки для восстановления chain.
* Recovery rerun не считается отдельным progression-днем для switch evidence.

History consistency hotfix (`2026-03-03`):

* Каждый checker (`readiness/governance/progress/transition`) пишет dual outputs за запуск:
  * latest alias в `runs/nightly-gateway-sla-*/<summary>.json`;
  * history copy в `run_dir/<summary>.json`.
* Progress/transition collectors считают `valid_count` по history rows, не включая top-level latest alias
  при наличии history copies.
* Backfill для старых запусков не делается: валидное accumulation окно для `valid_count` считается
  с первого nightly run после merge hotfix.

## M8.0: Streamlit IA spec (decision-complete, no implementation)

На шаге `M8.0` фиксируем IA-спецификацию без добавления Streamlit runtime-кода.

Source of truth:

* `docs/STREAMLIT_IA_V0.md`

Ожидаемый результат:

* В документе зафиксированы 4 зоны UI (`Stack Health`, `Run Explorer`, `Latest Metrics`, `Safe Actions`).
* Зафиксированы canonical data sources (CI smoke summaries) и field mapping.
* Зафиксированы safe action guardrails и handoff-контракт для `M8.1`.
* Док защищен regression-тестом `tests/test_streamlit_ia_doc.py`.

## M8.1: Streamlit operator panel v0 + no-crash smoke

Запуск панели:

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python -m streamlit run scripts/streamlit_operator_panel.py -- --runs-dir runs --gateway-url http://127.0.0.1:8770
```

Запуск smoke-gate:

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/streamlit_operator_panel_smoke.py --panel-runs-dir runs --runs-dir runs/ci-smoke-streamlit --summary-json runs/ci-smoke-streamlit/streamlit_smoke_summary.json --gateway-url http://127.0.0.1:8770 --startup-timeout-sec 45 --viewport-width 390 --viewport-height 844 --compact-breakpoint-px 768
```

Ожидаемый result contract (`streamlit_smoke_summary_v1`):

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

* `0` только если `status=ok`.
* `2` для любого `status=error`.
* `status=error` только если нарушены strict условия:
  * startup fail,
  * mobile layout contract fail,
  * отсутствуют `required_missing_sources`.
* `optional_missing_sources` не переводят smoke в `error`; используются как observability signal.

## M8.post: Streamlit Safe Actions audit trail

`Safe Actions` в панели ведет append-only audit log с traceable результатами запусков.

Audit artifact path:

* `runs/<runs_dir>/ui-safe-actions/safe_actions_audit.jsonl`

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

* В `Safe Actions` после выполнения команды показывается блок `Last safe action`.
* Ниже показывается таблица `Recent safe actions` (default: последние 10 записей, newest-first).
* Если лог отсутствует, UI показывает `not available yet` и не падает.
* При битой JSONL строке UI не падает: показывается error-row `invalid audit entry`.

## M8.post: Streamlit Latest Metrics history filters

Во вкладке `Latest Metrics` добавлен historical view без внешней БД: история строится из уже существующих timestamp run-директорий в canonical smoke roots.

History sources:

* `runs/ci-smoke-phase-a`
* `runs/ci-smoke-retrieve`
* `runs/ci-smoke-eval`
* `runs/ci-smoke-gateway-core`
* `runs/ci-smoke-gateway-automation`
* `runs/ci-smoke-gateway-http-core`
* `runs/ci-smoke-gateway-http-automation`

History controls:

* `History sources` (multiselect, default = все canonical sources)
* `History statuses` (multiselect, default = `ok,error`)
* `History limit per source` (default = `10`)

Historical row fields (`metrics_history_row_v1`, in-memory UI contract):

* `source`
* `timestamp_utc`
* `status`
* `run_dir`
* `run_json`
* `summary_json` (если доступен)
* `request_count`
* `failed_requests_count`
* `results_count`
* `query_count`
* `mean_mrr_at_k`
* `details`

Resilience/performance policy:

* scan cap: максимум `200` candidate run-директорий на source перед применением limit.
* некорректные run-директории пропускаются; UI показывает warning и продолжает работу.
* при отсутствии history строк показывается `not available yet`.

## G2.post: Streamlit fail_nightly progress visibility (optional sources)

Во вкладке `Latest Metrics` добавлен отдельный блок `Gateway fail_nightly progress`, который
агрегирует nightly decision-path артефакты и показывает операционный прогресс до `go|hold`.

Optional progress sources:

* `runs/nightly-gateway-sla-readiness/readiness_summary.json`
* `runs/nightly-gateway-sla-governance/governance_summary.json`
* `runs/nightly-gateway-sla-progress/progress_summary.json`

Поддерживаемые контракты:

* `gateway_sla_fail_nightly_readiness_v1`
* `gateway_sla_fail_nightly_governance_v1`
* `gateway_sla_fail_nightly_progress_v1`

UI поля progress-блока:

* `readiness_status`
* `latest_ready_streak`
* `decision_status`
* `remaining_for_window`
* `remaining_for_streak`
* `target_critical_policy`
* `reason_codes`

Tolerant rendering policy:

* если optional sources отсутствуют, панель показывает `not available yet`;
* если optional source битый/contract-mismatch, панель показывает warning и продолжает работу;
* optional progress sources не входят в strict `missing_sources` smoke-policy.

## M8.post: Streamlit compact mobile layout baseline

В панели закреплен compact mobile layout policy без изменения IA-табов и safe action guardrails.

Policy defaults:

* `compact_breakpoint_px = 768`
* baseline viewport для smoke-check: `390x844` (portrait)
* compact-режим включает:
  * уменьшенные paddings контейнера
  * stack header controls в одну колонку
  * horizontal scroll fallback для dataframes

Regression smoke-check:

* `scripts/streamlit_operator_panel_smoke.py` валидирует mobile policy контракт и baseline viewport.
* При нарушении mobile baseline (`viewport > breakpoint` или `landscape`) smoke возвращает `status=error`, `exit_code=2`.

## Qwen3 stack (OpenVINO-first)

Активный стек:

* `Qwen3-8B`
* `Qwen3-VL-4B-Instruct`
* `Qwen3-Embedding-0.6B`
* `Qwen3-Reranker-0.6B`
* `Whisper v3 Turbo (OpenVINO GenAI runtime path for ASR)`

Деактивировано:

* `Qwen3-TTS-12Hz-0.6B-CustomVoice` (archived; не использовать в production runbook).
* `Qwen3-ASR-0.6B` (archived; reversible via explicit opt-in flags).

Подробная матрица: `docs/QWEN3_MODEL_STACK.md`.

### Qwen3-VL self-conversion (OpenVINO IR)

```powershell
# Dry-run
python scripts/export_qwen3_openvino.py --preset qwen3-vl-4b

# Real export (standard path may still be blocked upstream)
python scripts/export_qwen3_openvino.py --preset qwen3-vl-4b --execute

# Working custom path
python -m scripts.export_qwen3_custom_openvino --preset qwen3-vl-4b --model-source models\hf_raw\qwen3-vl-4b
python -m scripts.export_qwen3_custom_openvino --preset qwen3-vl-4b --execute --model-source models\hf_raw\qwen3-vl-4b
```

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

Примечание: для `--execute` требуется установленный export toolchain (`transformers`, `optimum`, `optimum-intel`);
в runtime-only окружении dry-run может вернуть `support_probe.status=import_error`.

### Voice support probe + matrix

```powershell
# Probe current env
python scripts/probe_qwen3_voice_support.py

# Matrix dry-run / execute
python scripts/qwen3_voice_probe_matrix.py
python scripts/qwen3_voice_probe_matrix.py --execute
```

Ожидаемый результат:

* Создается `runs/<timestamp>-qwen3-voice-probe/`.
* `qwen3_asr` проверяем только для upstream-monitoring archived path.

### Isolated upstream experiment

`qwen3-tts` экспериментальное `.venv-exp` окружение удалено из active path.
Если понадобится повторная проверка upstream, создавай новое изолированное окружение вручную.

### Qwen3 cache cleanup (disk pressure)

```powershell
Remove-Item models\hf_cache -Recurse -Force
Remove-Item models\hf_raw\qwen3-vl-4b\.cache -Recurse -Force
Remove-Item models\hf_raw\qwen3-vl-4b -Recurse -Force
Remove-Item "$env:USERPROFILE\.cache\huggingface" -Recurse -Force
```

## OpenVINO: setup + diagnostics

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -c "import openvino as ov; core=ov.Core(); print('openvino=', ov.__version__); print('devices=', core.available_devices)"
python scripts/openvino_diag.py
```

Ожидаемый результат:

* В `runs/<timestamp>-openvino/` создан `openvino_diag_all_devices.json`.

## M3.1: Text core demo (OpenVINO GenAI + Qwen3-8B profile)

Установка runtime deps:

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install "openvino-genai>=2025.4.0"
```

Запуск demo:

```powershell
python scripts/text_core_openvino_demo.py --model-dir models\qwen3-8b-int4-cw-ov --prompt "Give me a short ATM10 starter plan" --device NPU
```

Ожидаемый результат:

* Создается `runs/<timestamp>-text-core-openvino/`.
* Внутри есть `run.json` и `response.json`.

## M4: HUD OCR baseline (Tesseract CLI)

Примечание: для этого baseline нужен установленный системный `tesseract` в `PATH`.

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/hud_ocr_baseline.py --image-in "C:\path\to\hud_screenshot.png" --lang eng --psm 6 --oem 1
```

Ожидаемый результат:

* Создается `runs/<timestamp>-hud-ocr/`.
* Внутри есть `run.json`, `ocr.json`, `ocr.txt`.

## M4: HUD mod-hook baseline

Подготовь payload JSON (пример):

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

Запуск:

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/hud_mod_hook_baseline.py --hook-json "C:\path\to\hud_hook_payload.json"
```

Ожидаемый результат:

* Создается `runs/<timestamp>-hud-hook/`.
* Внутри есть `run.json`, `hook_raw.json`, `hook_normalized.json`, `hud_text.txt`.

## M3: Voice runtime demos (active path = Whisper GenAI ASR)

Установка runtime deps (active path):

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Примечание: `qwen-tts` и `qwen-asr` выведены из active stack.
Rollback к archived `qwen-asr` допускается только временно и с explicit opt-in флагами.

### ASR demo (archived qwen3-asr path)

```powershell
# File -> text
python scripts/asr_demo.py --allow-archived-qwen-asr --audio-in "C:\path\to\sample.wav"

# Microphone -> text (5s)
python scripts/asr_demo.py --allow-archived-qwen-asr --record-seconds 5
```

Ожидаемый результат:

* Создается `runs/<timestamp>-asr-demo/`.
* Внутри есть `run.json` и `transcription.json`.

### ASR demo (OpenVINO GenAI + Whisper v3 Turbo, NPU path)

Установка runtime deps:

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python -m pip install "openvino-genai>=2025.4.0"
```

Подготовка OpenVINO модели Whisper v3 Turbo:

```powershell
optimum-cli export openvino --model openai/whisper-large-v3-turbo models\whisper-large-v3-turbo-ov
```

Запуск demo:

```powershell
# File -> text on NPU
python scripts/asr_demo_whisper_genai.py --model-dir models\whisper-large-v3-turbo-ov --audio-in "C:\path\to\sample.wav" --device NPU

# Optional timestamps
python scripts/asr_demo_whisper_genai.py --model-dir models\whisper-large-v3-turbo-ov --audio-in "C:\path\to\sample.wav" --device NPU --return-timestamps --word-timestamps
```

Ожидаемый результат:

* Создается `runs/<timestamp>-asr-whisper-genai/`.
* Внутри есть `run.json` и `transcription.json`.

### Long-lived voice runtime service (ASR only)

```powershell
# Service start (default backend = whisper_genai)
python scripts/voice_runtime_service.py --host 127.0.0.1 --port 8765 --asr-model models\whisper-large-v3-turbo-ov

# Optional auth token hardening
python scripts/voice_runtime_service.py --host 127.0.0.1 --port 8765 --asr-model models\whisper-large-v3-turbo-ov --service-token "change-me"

# Health
python scripts/voice_runtime_client.py --service-url http://127.0.0.1:8765 health

# ASR request
python scripts/voice_runtime_client.py --service-url http://127.0.0.1:8765 asr --audio-in "C:\path\to\sample.wav"
```

HTTP hardening defaults (voice service):

* `max_request_body_bytes = 262144`
* `max_json_depth = 8`
* `max_string_length = 8192`
* `max_array_items = 256`
* `max_object_keys = 256`
* optional `service_token` (`--service-token` или `ATM10_SERVICE_TOKEN`) -> require `X-ATM10-Token`

Payload-limit behavior:

* `payload_too_large` -> HTTP `413`
* `payload_limit_exceeded` -> HTTP `413`
* обычные валидационные ошибки payload -> HTTP `400`

Примечание (security): в HTTP payload для `/tts` и `/tts_stream` поле `out_wav_path` должно быть только именем файла (без absolute path и директорий). Сервис всегда пишет TTS WAV в свой `runs/<timestamp>-voice-service/tts_outputs/`.

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
python scripts/voice_runtime_client.py --service-url http://127.0.0.1:8765 asr --audio-in "C:\path\to\sample.wav" --language en
```

Примечание: `--asr-warmup-request` делает один ASR inference на старте (по умолчанию на сгенерированном silence WAV, либо через `--asr-warmup-audio`) и снижает cold-start impact в игровом цикле.
Пока warmup выполняется, `/health` может быть временно недоступен; это нормально для startup-фазы.

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

Ожидаемый результат:

* Создается `runs/<timestamp>-asr-backend-bench/`.
* Внутри есть `summary.json`, `summary.md`, `per_sample_results.jsonl`.

### TTS runtime service (separate process/container)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python -m pip install fastapi uvicorn
python scripts/tts_runtime_service.py --host 127.0.0.1 --port 8780 --runs-dir runs\tts-runtime
```

Принятый runtime design:

* Router: FastAPI
* Main engine: XTTS v2
* Fallback engines: Piper, Silero (для `ru` service voice)
* Techniques: prewarm, queue, chunking, phrase cache, true streaming for `/tts_stream`
* HTTP hardening: payload limits (`max_request_bytes/json_depth/string/array/object`) + sanitized internal errors
* Optional auth hardening: `--service-token` или `ATM10_SERVICE_TOKEN` -> require `X-ATM10-Token`

Минимальная конфигурация adapters (env):

```powershell
# XTTS v2
$env:XTTS_MODEL_NAME="tts_models/multilingual/multi-dataset/xtts_v2"
$env:XTTS_USE_GPU="false"
# optional cloning wav for XTTS
# $env:XTTS_DEFAULT_SPEAKER_WAV="C:\path\to\speaker.wav"

# Piper fallback
$env:PIPER_EXECUTABLE="piper"
$env:PIPER_MODEL_PATH="C:\path\to\piper\en_US-model.onnx"
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

Пример запроса TTS:

```powershell
python scripts/tts_runtime_client.py --service-url http://127.0.0.1:8780 health
python scripts/tts_runtime_client.py --service-url http://127.0.0.1:8780 tts --text "crafting started" --language en
python scripts/tts_runtime_client.py --service-url http://127.0.0.1:8780 tts-stream --text "служебное сообщение" --language ru --service-voice
```

Streaming behavior:

* `/tts_stream` отдает NDJSON инкрементально (`started -> audio_chunk -> completed`) без полного pre-buffer.
* `/tts` остается non-streaming и использует прежний request/response контракт.
* Internal 500 ответы всегда sanitized; подробности пишутся локально в `runs/<timestamp>-tts-service/service_errors.jsonl`.

### Voice latency benchmark (historical)

Исторические артефакты `Qwen3-TTS` оставлены для reference в `runs/*qwen3-tts*`.
Для production game-loop этот путь деактивирован.

## M1: Phase A smoke

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/phase_a_smoke.py
# Strict mode (no fallback to stub)
python scripts/phase_a_smoke.py --vlm-provider openai --strict-vlm
```

Ожидаемый результат:

* Создается `runs/<timestamp>/`.
* Внутри есть `screenshot.png`, `run.json`, `response.json`.
* В strict-mode при ошибке VLM `run.json` и `response.json` все равно сохраняются перед non-zero exit.

## M2: FTB Quests normalization

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/normalize_ftbquests.py
```

Опционально:

```powershell
python scripts/normalize_ftbquests.py --quests-dir "C:\path\to\config\ftbquests\quests"
```

## M2: Retrieval demo (in-memory)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/retrieve_demo.py --profile baseline --in data/ftbquests_norm --query "steel tools"
```

Опционально, OV production profile:

```powershell
python scripts/retrieve_demo.py --profile ov_production --in data/ftbquests_norm --query "steel tools"
```

Опционально, ручной override поверх profile:

```powershell
python scripts/retrieve_demo.py --profile ov_production --in data/ftbquests_norm --query "steel tools" --reranker-device NPU
```

## M2: Retrieval eval benchmark

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/eval_retrieval.py --profile baseline --docs tests/fixtures/retrieval_docs_sample.jsonl --eval tests/fixtures/retrieval_eval_sample.jsonl --topk 3 --candidate-k 50 --reranker none
```

Опционально, OV production profile:

```powershell
python scripts/eval_retrieval.py --profile ov_production --docs tests/fixtures/retrieval_docs_sample.jsonl --eval tests/fixtures/retrieval_eval_sample.jsonl
```

## M2: Qdrant ingest (optional backend)

```powershell
docker run --name atm10-qdrant -p 6333:6333 qdrant/qdrant
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/ingest_qdrant.py --in data/ftbquests_norm --collection atm10
```

## M2: Retrieval demo (qdrant backend)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/retrieve_demo.py --backend qdrant --collection atm10 --query "steel tools" --topk 5
```

## M5: KAG baseline (file-based, no Neo4j)

### Build graph

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/kag_build_baseline.py --in data/ftbquests_norm/quests.jsonl
```

Ожидаемый результат:

* Создается `runs/<timestamp>-kag-build/`.
* Внутри есть `run.json` и `kag_graph.json`.

### Query graph

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/kag_query_demo.py --graph runs\YYYYMMDD_HHMMSS-kag-build\kag_graph.json --query "steel tools"
```

Ожидаемый результат:

* Создается `runs/<timestamp>-kag-query/`.
* Внутри есть `run.json` и `kag_query_results.json`.

## M5.1: KAG via Neo4j (approved transition)

### Start Neo4j locally

```powershell
docker run --name atm10-neo4j -p 7474:7474 -p 7687:7687 `
  -e NEO4J_AUTH=neo4j/neo4jpass `
  neo4j:5
```

### Sync `kag_graph.json` to Neo4j

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="neo4jpass"
python scripts/kag_sync_neo4j.py `
  --graph runs\YYYYMMDD_HHMMSS-kag-build\kag_graph.json `
  --neo4j-url http://127.0.0.1:7474 `
  --neo4j-database neo4j `
  --neo4j-user neo4j `
  --reset-graph
```

Ожидаемый результат:

* Создается `runs/<timestamp>-kag-sync-neo4j/`.
* Внутри есть `run.json` и `neo4j_sync_summary.json`.

### Query KAG directly from Neo4j

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="neo4jpass"
python scripts/kag_query_neo4j.py `
  --query "steel tools" `
  --topk 5 `
  --neo4j-url http://127.0.0.1:7474 `
  --neo4j-database neo4j `
  --neo4j-user neo4j
```

Ожидаемый результат:

* Создается `runs/<timestamp>-kag-query-neo4j/`.
* Внутри есть `run.json` и `kag_query_results.json`.

## M5.2: KAG Neo4j benchmark (quality + latency)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="neo4jpass"
python scripts/eval_kag_neo4j.py `
  --eval tests/fixtures/kag_neo4j_eval_sample.jsonl `
  --topk 5 `
  --warmup-runs 1 `
  --neo4j-url http://127.0.0.1:7474 `
  --neo4j-database neo4j `
  --neo4j-user neo4j
```

Ожидаемый результат:

* Создается `runs/<timestamp>-kag-neo4j-eval/`.
* Внутри есть `run.json`, `eval_results.json`, `summary.md`.
* В `eval_results.json` есть:
  * `mean_recall_at_k`
  * `mean_mrr_at_k`
  * `hit_rate_at_k`
  * `latency_mean_ms`, `latency_p95_ms`, `latency_max_ms`
* `--warmup-runs` делает N полноценных warmup-проходов по eval-набору до измеряемого прогона.
  Warmup-запросы не входят в per-case latency и итоговые метрики, но фиксируются в `run.json.warmup`.

### Hard-cases benchmark

Nightly hard profile (recommended): использовать `--warmup-runs 1` как default.

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="neo4jpass"
python scripts/eval_kag_neo4j.py `
  --eval tests/fixtures/kag_neo4j_eval_hard.jsonl `
  --topk 5 `
  --warmup-runs 1 `
  --neo4j-url http://127.0.0.1:7474 `
  --neo4j-database neo4j `
  --neo4j-user neo4j
```

### Canonical guardrail thresholds (sample + hard)

Пороговые профили:

* `sample`: `recall@k >= 1.0`, `mrr@k >= 0.80`, `hit-rate@k >= 1.0`, `latency_p95_ms <= 120`
* `hard`: `recall@k >= 1.0`, `mrr@k >= 0.90`, `hit-rate@k >= 1.0`, `latency_p95_ms <= 130`

Проверка sample-run:

```powershell
python scripts/check_kag_neo4j_guardrail.py --profile sample --eval-results-json "runs\YYYYMMDD_HHMMSS-kag-neo4j-eval\eval_results.json"
```

Проверка hard-run:

```powershell
python scripts/check_kag_neo4j_guardrail.py --profile hard --eval-results-json "runs\YYYYMMDD_HHMMSS-kag-neo4j-eval\eval_results.json"
```

## M5.3: KAG guardrail nightly workflow

Nightly workflow file:

* `.github/workflows/kag-neo4j-guardrail-nightly.yml`

Workflow steps:

* `kag_build_baseline` на fixture docs `tests/fixtures/kag_neo4j_docs_sample.jsonl`
* `kag_sync_neo4j` в локальный Neo4j service
* `eval_kag_neo4j` для `sample` + `hard` (оба с `--warmup-runs 1`)
* `check_kag_neo4j_guardrail.py` для `sample` + `hard`
* `kag_guardrail_trend_snapshot.py` для latest/history trend (`sample` vs `hard`)
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

Ожидаемый результат:

* Создается `runs/<timestamp>-kag-guardrail-trend/`.
* Внутри есть `run.json`, `trend_snapshot.json`, `summary.md`.
* В `trend_snapshot.json` есть `rolling_baseline` по `sample`/`hard` (latest vs mean previous N runs).
* В `rolling_baseline.regression_flags` фиксируются статусы `mrr`/`latency_p95` (`improved|stable|regressed|insufficient_history`) и severity (`none|warn|critical`) с агрегатом `max_regression_severity`.
* В `trend_snapshot.json.critical_policy` фиксируется принятый policy (`signal_only|fail_nightly`) и `critical_profiles`.
* Nightly baseline policy: `signal_only` (critical severity сигнализируется в summary/artifacts и не фейлит job).
* Опциональный `fail_nightly` режим доступен только как explicit opt-in для ужесточения guardrail.

### Warmup A/B compare (mini benchmark)

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
$env:NEO4J_PASSWORD="neo4jpass"
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

Ожидаемый результат:

* Создается `runs/<timestamp>-kag-neo4j-warmup-compare/`.
* Внутри есть `run.json`, `summary.json`, `summary.md`.
* `summary.json.delta.p95_improvement_ms > 0` означает, что candidate профиль быстрее baseline по p95.

## M6: Automation scaffold (dry-run only)

Важно: этот entrypoint не выполняет реальные keyboard/mouse события. Он только валидирует план и пишет dry-run artifacts.

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/automation_dry_run.py --plan-json "C:\path\to\automation_plan.json"
```

Пример `automation_plan.json`:

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

Пример запуска fixture-сценариев:

```powershell
python scripts/automation_dry_run.py --plan-json "tests/fixtures/automation_plan_quest_book.json"
python scripts/automation_dry_run.py --plan-json "tests/fixtures/automation_plan_inventory_check.json"
```

Ожидаемый результат:

* Создается `runs/<timestamp>-automation-dry-run/`.
* Внутри есть `run.json`, `actions_normalized.json`, `execution_plan.json`.
* `run.json.result.dry_run=true`, никаких системных input events не отправляется.

## M6.3: Intent -> automation_plan adapter (dry-run only)

Важно: adapter только строит `automation_plan_v1` из intent payload и сохраняет artifacts. Реальных input events нет.

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/intent_to_automation_plan.py --intent-json "tests/fixtures/intent_open_quest_book.json"
```

Ожидаемый результат:

* Создается `runs/<timestamp>-intent-to-automation-plan/`.
* Внутри есть `run.json` и `automation_plan.json`.
* `run.json.result.dry_run_only=true`.
* В `automation_plan.json` есть `planning` metadata (`intent_type`, `intent_schema_version`, `adapter_name`, `adapter_version`; optional `intent_id/trace_id`).

Проверка end-to-end через existing dry-run runner:

```powershell
python scripts/intent_to_automation_plan.py --intent-json "tests/fixtures/intent_open_quest_book.json" --plan-out "runs\m6_3_intent_plan.json"
python scripts/automation_dry_run.py --plan-json "runs\m6_3_intent_plan.json"
```

## M6.4: Unified smoke chain (`intent -> plan -> automation_dry_run`)

Единый smoke entrypoint для dry-run цепочки.

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
python scripts/automation_intent_chain_smoke.py --intent-json "tests/fixtures/intent_open_quest_book.json"
python scripts/automation_intent_chain_smoke.py --intent-json "tests/fixtures/intent_check_inventory_tool.json"
python scripts/automation_intent_chain_smoke.py --intent-json "tests/fixtures/intent_open_world_map.json"
```

Ожидаемый результат:

* Создается `runs/<timestamp>-automation-intent-chain-smoke/`.
* Внутри есть:
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

Ожидаемый результат:

* Оба check-скрипта завершаются с `status=ok`.
* В `--summary-json` поле `observed` включает optional trace-correlation metadata:
  * `trace_id`, `intent_id` (если они есть в `planning` action-plan metadata).
* Для intent-chain canonical fixtures используются `--require-trace-id` и `--require-intent-id`; отсутствие любого из id считается contract violation.
* В CI step summary (`Automation Smoke Contracts`) эти поля выводятся отдельными колонками `trace_id/intent_id` для быстрого triage.
* Любое нарушение контракта (missing artifact/метрики ниже порога/несовпадение intent) даёт non-zero exit code.

## M6.19: New intent template rollout policy (CI)

Policy checklist для каждого нового `intent_type`:

1. Добавить canonical fixture:
   * `tests/fixtures/intent_<new_intent_type>.json`
   * fixture должен включать `intent_id` и `trace_id`.
2. Добавить smoke run step:
   * `python scripts/automation_intent_chain_smoke.py --intent-json tests/fixtures/intent_<new_intent_type>.json --runs-dir runs/ci-smoke-automation-chain-<new_intent_type>`
3. Добавить contract-check step:
   * `python scripts/check_automation_smoke_contract.py --mode intent_chain --runs-dir runs/ci-smoke-automation-chain-<new_intent_type> --min-action-count 3 --min-step-count 4 --expected-intent-type <new_intent_type> --require-trace-id --require-intent-id --summary-json runs/ci-smoke-automation-chain-<new_intent_type>/contract_summary.json`
4. Добавить summary/artifact wiring:
   * новая строка в `Automation Smoke Contracts` summary table;
   * новый `contract_summary.json` в upload artifact path.
5. Добавить regression test:
   * минимум 1 pytest на e2e dry-run chain для нового fixture.

## M6.8: Troubleshooting automation smoke contract failures (CI)

Быстрый чек-лист при падении `check_automation_smoke_contract`:

1. Проверить summary artifacts:
   * `runs/ci-smoke-automation-dry-run/contract_summary.json`
   * `runs/ci-smoke-automation-chain/contract_summary.json`
2. Проверить поле `violations` и `error` в summary JSON:
   * `error != null` обычно указывает на missing artifact path.
   * `violations` содержит конкретный контракт, который не выполнен.
3. Сверить минимальные пороги в workflow:
   * `min_action_count=3`, `min_step_count=4`
   * для chain дополнительно `expected_intent_type` для соответствующего fixture (`open_quest_book`, `check_inventory_tool`, `open_world_map`)
4. Перезапустить локально те же команды CI:
   * `automation_dry_run` + `check_automation_smoke_contract --mode dry_run`
   * `automation_intent_chain_smoke` + `check_automation_smoke_contract --mode intent_chain`
5. Если проблема в артефактах:
   * убедиться, что smoke script завершился `status=ok` в `run.json`
   * проверить, что пути в `--runs-dir` совпадают между smoke step и check step
6. Если проблема в `intent_type`:
   * проверить fixture (`tests/fixtures/intent_open_quest_book.json`, `tests/fixtures/intent_check_inventory_tool.json`, `tests/fixtures/intent_open_world_map.json`)
   * проверить `automation_plan.json.context.intent_type` в chain run artifacts
