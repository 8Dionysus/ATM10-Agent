# RELEASE_WAVE7_TURBO

Дата: 2026-03-02

Статус ветки: `release_only` (не развернуто полностью в `master`, ожидается `planned_resync`).

## Scope

Wave 7 Turbo закрывает ускоренную 3-недельную волну `Stability & Ops` для solo+AI исполнения:

* centralized ops policy (`src/agent_core/ops_policy.py`);
* CI smoke report-layer (`validation_summary_v1`, `ops_contract_index_v1`);
* nightly transition gate (`gateway_sla_fail_nightly_transition_v1`) + conditional strict trend step;
* Streamlit `Ops Readiness` visibility (transition + freshness) без ломки текущих контрактов.

## Included Changes

1. Новые скрипты:
   * `scripts/validate_ops_contracts.py`
   * `scripts/build_ops_contract_index.py`
   * `scripts/check_gateway_sla_fail_nightly_transition.py`
2. Новый shared profile layer:
   * `scripts/ops_contract_profiles.py`
3. Новый policy layer:
   * `src/agent_core/ops_policy.py`
4. Workflow updates:
   * `.github/workflows/pytest.yml`
   * `.github/workflows/gateway-sla-readiness-nightly.yml`
5. Streamlit updates:
   * `scripts/streamlit_operator_panel.py`
   * `scripts/streamlit_operator_panel_smoke.py`

## Release Checklist

1. Local targeted tests:
   * `python -m pytest tests/test_ops_policy_consistency.py tests/test_validate_ops_contracts.py tests/test_build_ops_contract_index.py tests/test_check_gateway_sla_fail_nightly_transition.py tests/test_streamlit_operator_panel.py tests/test_streamlit_operator_panel_smoke.py tests/test_gateway_sla_readiness_nightly_workflow.py tests/test_pytest_workflow_ops_contracts.py`
2. Full regression:
   * `python -m pytest`
3. CI verification:
   * `pytest.yml` публикует `runs/ci-ops/validation_summary.json` и `runs/ci-ops/ops_contract_index.json`.
4. Nightly verification:
   * readiness workflow публикует `runs/nightly-gateway-sla-transition/transition_summary.json`;
   * strict trend step запускается только при `allow_switch=true`.

## Rollback

Если обнаружен шум/нестабильность:

1. Отключить strict branch в nightly:
   * временно убрать/закомментировать step `Smoke - Gateway SLA trend snapshot (fail_nightly strict gate)`.
2. Сохранить transition отчетность:
   * `Transition - Gateway SLA fail_nightly switch gate (report_only)` остается активным.
3. При необходимости временно убрать CI report-layer:
   * отключить только шаги `validate_ops_contracts`/`build_ops_contract_index`, не меняя core smoke.

## Known Limits

1. `allow_switch=true` зависит от накопленной истории nightly; на короткой истории ожидаем `hold`.
2. Freshness в Streamlit основан на timestamp полях summary-артефактов; при их отсутствии состояние `unknown`.
3. Wave 7 Turbo не включает breaking migration и не меняет `gateway_request_v1/gateway_response_v1`.
