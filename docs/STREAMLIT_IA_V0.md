# STREAMLIT_IA_V0

Decision-complete IA-спецификация для `M8.0` (без реализации Streamlit-кода в этой итерации).

## Goals / Non-goals

Goals:

* Зафиксировать структуру Streamlit operator panel v0 как single source для `M8.1`.
* Определить обязательные зоны UI: `Stack Health`, `Run Explorer`, `Latest Metrics`, `Safe Actions`.
* Зафиксировать data contracts, field mapping, artifact links и operator flows.
* Снять продуктовые и архитектурные двусмысленности для implementer.

Non-goals:

* Не пишем `scripts/streamlit_operator_panel.py`.
* Не добавляем `streamlit` в `requirements.txt`.
* Не меняем `gateway_request_v1` / `gateway_response_v1`.
* Не добавляем CI smoke для Streamlit (это `M8.1`).

## Personas & primary tasks

1. Operator (ежедневный runtime-контроль):
* Проверить, что gateway transport доступен и smoke summaries в норме.
* Быстро открыть артефакты последнего запуска при деградации.
* Запустить safe smoke-trigger и получить traceable path на результат.

2. Engineer (диагностика regressions):
* Сопоставить `status/error_code/request_count/failed_requests_count` между smoke контуром и gateway health.
* Перейти из UI в конкретный `run.json/response.json` для root-cause.

## IA map

Top-level layout (single page, tabs):

* Tab 1: `Stack Health`
* Tab 2: `Run Explorer`
* Tab 3: `Latest Metrics`
* Tab 4: `Safe Actions`

Global controls (header):

* `runs_dir` (text input, default `runs`)
* `gateway_url` (text input, default `http://127.0.0.1:8770`)
* `Refresh` button (manual refresh only)
* `Last refreshed at` (UTC timestamp)

Future entrypoint (`M8.1`):

* `python -m streamlit run scripts/streamlit_operator_panel.py -- --runs-dir runs --gateway-url http://127.0.0.1:8770`

## Screen specs (4 зоны)

### Stack Health

Required widgets:

* Service status card (`gateway transport`)
* HTTP endpoint card (`GET /healthz`)
* Quick diagnostics table по gateway policy snapshot

Inputs:

* `GET /healthz` from gateway URL

Displayed fields:

* `status`
* `service`
* `timestamp_utc`
* `runs_dir`
* `policy.max_request_body_bytes`
* `policy.max_json_depth`
* `policy.max_string_length`
* `policy.max_array_items`
* `policy.max_object_keys`
* `policy.operation_timeout_sec`

Artifact link rules:

* Для health transport-check ссылки на artifact не требуются.
* При ошибке запроса показывается troubleshooting hint на `docs/RUNBOOK.md`.

Refresh policy:

* Только manual (`Refresh` button), без background polling.

### Run Explorer

Required widgets:

* Directory root indicator (`runs_dir`)
* Scenario selector (`gateway-core`, `gateway-automation`, `gateway-http-core`, `gateway-http-automation`, `phase-a`, `retrieve`, `eval`)
* Latest run card
* Artifact links panel

Inputs:

* Filesystem under `runs/...`
* `run.json` и summary JSON соответствующего сценария

Displayed fields:

* `paths.run_dir`
* `paths.run_json`
* `paths.summary_json`
* `status`
* `request_count`
* `failed_requests_count` (если доступно)
* Per-request rows (`operation`, `status`, `error_code`, `http_status`, `expected_http_status`, `run_json`)

Artifact link rules:

* Link строится только из реального существующего пути.
* Если файла нет, показывается `missing`.
* Путь выводится как абсолютный/resolve-only label (без попытки auto-open внешними toolchain).

Refresh policy:

* Только manual (`Refresh` button).

### Latest Metrics

Required widgets:

* Summary matrix table по canonical smoke sources
* Status badge per source (`ok|error|missing`)
* Compact trend snapshot (latest only, без historical charts в v0)

Inputs (canonical sources):

* `runs/ci-smoke-phase-a/smoke_summary.json`
* `runs/ci-smoke-retrieve/smoke_summary.json`
* `runs/ci-smoke-eval/smoke_summary.json`
* `runs/ci-smoke-gateway-core/gateway_smoke_summary.json`
* `runs/ci-smoke-gateway-automation/gateway_smoke_summary.json`
* `runs/ci-smoke-gateway-http-core/gateway_http_smoke_summary.json`
* `runs/ci-smoke-gateway-http-automation/gateway_http_smoke_summary.json`

Displayed fields:

* Core: `status`, `observed.results_count`, `observed.query_count`, `observed.mean_mrr_at_k`
* Gateway local: `status`, `request_count`
* Gateway HTTP: `status`, `request_count`, `failed_requests_count`

Artifact link rules:

* Для каждой строки должен быть link на исходный summary JSON.

Refresh policy:

* Только manual (`Refresh` button).

### Safe Actions

Required widgets:

* Action selector:
  * `Gateway HTTP smoke core`
  * `Gateway HTTP smoke automation`
  * `Gateway local smoke core`
  * `Gateway local smoke automation`
* Optional `runs_dir override` input
* `Execute safe action` button
* Result panel (`exit_code`, `status`, `summary_json`, `run_dir`)

Inputs:

* Local script entrypoints:
  * `scripts/gateway_v1_http_smoke.py`
  * `scripts/gateway_v1_smoke.py`

Displayed fields:

* Executed command (string)
* Exit code
* Parsed summary status (`ok|error`)
* Artifact paths

Artifact link rules:

* Каждый action обязан возвращать ссылку на summary JSON.
* Если summary отсутствует, action считается failed даже при `exit_code=0`.

Refresh policy:

* После action UI не auto-refresh; оператор нажимает `Refresh`.

## Data contracts & field mapping

Summary contract mapping (минимальный обязательный набор):

1. `smoke_summary.json` (`phase_a_smoke|retrieve_demo|eval_retrieval`):
* `status`
* `observed.mode`
* `observed.*` metrics по mode

2. `gateway_smoke_summary.json`:
* `status`
* `scenario`
* `request_count`
* `requests[].operation`
* `requests[].status`
* `requests[].error_code`
* `requests[].run_json`

3. `gateway_http_smoke_summary.json`:
* `status`
* `scenario`
* `request_count`
* `failed_requests_count`
* `requests[].operation`
* `requests[].status`
* `requests[].http_status`
* `requests[].expected_http_status`
* `requests[].error_code`
* `requests[].run_json`

4. Gateway transport dependency:
* `GET /healthz` for service diagnostics
* `POST /v1/gateway` for future interactive panel actions

## Error/empty/loading states

1. Loading:
* Пока идет чтение файлов/health-request, показывается `loading` indicator.

2. Empty:
* Если summary файл отсутствует, статус источника `missing`.
* UI не падает; вместо данных показывается `not available yet`.

3. Error:
* Parse error JSON -> status `error`, текст `invalid summary format`.
* HTTP error/timeout на `GET /healthz` -> status `error`, показать `gateway unavailable`.
* Для `Safe Actions` ошибкой считается любое из:
  * non-zero exit code
  * summary `status=error`
  * отсутствие summary file

## Operator flows (happy + failure)

Flow A (happy): daily check

1. Operator открывает panel.
2. Нажимает `Refresh`.
3. В `Stack Health` видит `status=ok`.
4. В `Latest Metrics` видит `ok` по gateway/core sources.
5. При необходимости открывает `Run Explorer` и переходит по link в `run.json`.

Flow B (failure): gateway HTTP regression

1. В `Latest Metrics` источник `gateway-http-core` показывает `error`.
2. Operator идет в `Run Explorer`, открывает `gateway_http_smoke_summary.json`.
3. Смотрит `failed_requests_count` и request rows.
4. Переходит по `run_json` в проблемный run.
5. Проверяет `Stack Health` для `GET /healthz` и policy snapshot.

Flow C (safe action rerun)

1. В `Safe Actions` выбирает `Gateway HTTP smoke core`.
2. Нажимает `Execute safe action`.
3. Получает `exit_code/status/summary_json`.
4. Нажимает `Refresh` и проверяет обновленный статус в `Latest Metrics`.

## Safe actions guardrails

* Разрешены только safe smoke-trigger commands.
* Запрещены любые real keyboard/mouse/game-state mutation действия.
* Любой action должен быть traceable через artifacts в `runs/...`.
* UI не должен скрывать команду запуска; operator должен видеть exact command string.
* При любой неопределенности действие трактуется как `deny by default`.

## M8.1 handoff checklist

Implementation contract для `scripts/streamlit_operator_panel.py`:

* Поддержка CLI args:
  * `--runs-dir` (default `runs`)
  * `--gateway-url` (default `http://127.0.0.1:8770`)
* Обязательные UI зоны: `Stack Health`, `Run Explorer`, `Latest Metrics`, `Safe Actions`.
* Загрузка данных только из canonical sources, перечисленных в этом документе.
* Manual refresh по кнопке как default policy.

No-crash startup criterion (`M8.1`):

* Команда старта UI должна завершать bootstrap без exception в headless smoke окружении.

Machine-readable summary contract (`M8.1` target):

* Path: `runs/<timestamp>-streamlit-smoke/streamlit_smoke_summary.json`
* Required fields:
  * `schema_version = "streamlit_smoke_summary_v1"`
  * `status = "ok" | "error"`
  * `startup_ok` (bool)
  * `tabs_detected` (list[str])
  * `missing_sources` (list[str])
  * `errors` (list[str])
  * `paths.run_dir`
  * `paths.summary_json`

Exit policy (`M8.1` target):

* `0` only when `status=ok`.
* `2` for any `status=error`.
