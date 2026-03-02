# wave6: security hardening baseline + release rollout package

## Context

Wave 6 собирает уже реализованный security hardening в release-ready пакет без новых продуктовых фич.
Контекст и evidence берутся из канонических источников:

- `docs/RUNBOOK.md`
- `docs/DECISIONS.md`
- `runs/20260302_144210-wave6-release/release_summary.json`
- `runs/20260302_142741-security_audit_wave2_5/security_audit_summary.json`

## Scope

Что входит в PR:

- только изменения security hardening baseline и release handoff;
- без новых API-фич и без breaking changes публичного `gateway_response_v1`;
- staged rollout и monitoring на 7 дней.

Коммиты в PR:

- `88328f4` gateway redaction + reranker allowlist
- `afa2d83` optional token auth (gateway/voice)
- `8c08d95` tts payload limits + sanitized errors
- `3f1c1bc` action SHA pinning + security-nightly
- `4e6e58f` tests/docs/release sync

Reviewer guide:

- Reviewer 1: gateway/security contract (`gateway_v1_local`, `gateway_v1_http_service`, tests)
- Reviewer 2: tts/voice runtime hardening (`tts_runtime_service`, `voice_runtime_service`, tests)
- Reviewer 3: CI governance/workflows (`.github/workflows/*`, `dependency_audit`)

## Findings -> Fixes Mapping

| Finding ID | Risk | Fix | Files | Tests |
|---|---|---|---|---|
| `high_secret_leak_gateway_request_artifacts` | plaintext secrets in gateway artifacts | redaction before writing `request.json` + `run.json.request_redaction` metadata | `scripts/gateway_v1_local.py`, `scripts/gateway_artifact_policy.py` | `tests/test_gateway_v1_local.py`, `tests/test_gateway_v1_http_service.py` |
| `high_untrusted_reranker_model_path` | untrusted model-id path | allowlist for `payload.reranker_model` (`reranker=qwen3`) + explicit opt-in override | `scripts/gateway_v1_local.py` | `tests/test_gateway_v1_local.py`, `tests/test_gateway_v1_http_service.py` |
| `medium_missing_optional_service_auth` | unauthenticated HTTP control plane | optional token auth (`--service-token` / `ATM10_SERVICE_TOKEN`) requiring `X-ATM10-Token` | `scripts/gateway_v1_http_service.py`, `scripts/voice_runtime_service.py`, `scripts/tts_runtime_service.py` | `tests/test_gateway_v1_http_service.py`, `tests/test_voice_runtime_service.py`, `tests/test_tts_runtime_service.py` |
| `medium_tts_http_hardening_gap` | oversized payloads and leaked internal error details | payload policy limits + sanitized `500` envelope + redacted local error log | `scripts/tts_runtime_service.py` | `tests/test_tts_runtime_service.py` |
| `low_workflow_supply_chain_pinning` | mutable CI action refs | critical GitHub Actions pinned to SHA | `.github/workflows/pytest.yml`, `.github/workflows/gateway-sla-readiness-nightly.yml`, `.github/workflows/kag-neo4j-guardrail-nightly.yml`, `.github/workflows/security-nightly.yml` | workflow review |
| `low_security_gate_strength` | weak fail policy in security scan | nightly `dependency_audit --policy fail_on_critical`; fail on `security_scan status != ok|skipped` | `scripts/dependency_audit.py`, `.github/workflows/security-nightly.yml` | `tests/test_dependency_audit.py` |
| `low_script_level_coverage_gap` | missing script-level tests | direct tests for script entrypoints | `scripts/normalize_ftbquests.py`, `scripts/ingest_qdrant.py` | `tests/test_normalize_ftbquests_script.py`, `tests/test_ingest_qdrant_script.py` |

## Public Contract Changes

1. Gateway artifacts:
   `request.json` now redacted-by-default; `run.json` includes `request_redaction` (`applied`, `fields_redacted`, `checklist_version`).
2. Gateway request policy:
   for `retrieval_query` + `reranker=qwen3`, `payload.reranker_model` is allowlisted; invalid model returns `invalid_request` (HTTP 400 on gateway HTTP path); override only via `ATM10_ALLOW_UNTRUSTED_RERANKER_MODEL=true`.
3. Optional HTTP auth:
   gateway/voice/tts support `--service-token` and `ATM10_SERVICE_TOKEN`; when token is configured, `X-ATM10-Token` is mandatory; gateway unauthorized path returns `error_code=unauthorized` and HTTP 401.
4. TTS HTTP hardening:
   payload limits are enforced (`max_request_bytes`, `max_json_depth`, `max_string_length`, `max_array_items`, `max_object_keys`); internal `500` is sanitized; details go to redacted local `service_errors.jsonl`.
5. CI/security governance:
   critical actions pinned to SHA; nightly `security-gate` uses `dependency_audit --policy fail_on_critical`; `fail_on_critical` fails when `security_scan status != ok|skipped`.

## Verification Evidence

Canonical evidence artifacts:

- `runs/20260302_144210-wave6-release/release_summary.json`
- `runs/20260302_142741-security_audit_wave2_5/security_audit_summary.json`

Regression baseline:

- `python -m pytest` -> passed (`324 passed`)

Security-specific checks:

- redaction test (`neo4j_password` is not plaintext in gateway artifacts): passed
- reranker allowlist reject + env override allow: passed
- auth required/allowed paths for gateway/voice/tts: passed
- TTS payload limit `413`: passed
- TTS sanitized internal `500`: passed
- dependency audit fail-on-critical behavior: passed

Operational smoke:

- `python scripts/gateway_v1_http_smoke.py --scenario core ...` -> `status=ok`
- `python scripts/check_gateway_sla.py --policy signal_only ...` -> `status=ok`, `sla_status=pass`
- `python scripts/streamlit_operator_panel_smoke.py ...` -> `status=ok`

## Rollout Plan (A/B/C)

Stage A (merge, auth disabled by default):

- merge PR with no token env set;
- confirm backward compatibility of existing clients/automation.

Stage B (staging):

- configure `ATM10_SERVICE_TOKEN` in staging runtime;
- validate unauthorized/authorized behavior for gateway + voice + tts;
- validate smoke/health with `X-ATM10-Token`.

Stage C (production):

- enable token in production where applicable;
- keep rollback path available: unset token env to restore open mode.

## Monitoring (7 days)

Daily checks:

- `security-nightly` workflow
- `gateway-sla-readiness-nightly` workflow
- `kag-neo4j-guardrail-nightly` workflow
- artifact integrity:
  - `request_redaction` consistency in gateway `run.json`
  - redacted `service_errors.jsonl`
  - no plaintext secrets in run artifacts

Escalation triggers:

- any plaintext secret in artifacts/logs
- unexpected `401 unauthorized` spike after Stage B/C
- failed nightly security gate

## Rollback

Primary rollback (auth rollout):

- unset `ATM10_SERVICE_TOKEN` for affected services;
- restart runtime to return to backward-compatible open mode.

Operational rollback policy:

- rollback is config-driven and does not require reverting API contracts;
- if needed, pause Stage C and keep Stage A behavior until follow-up PR (`Hardening+`) is ready.

## Checklist

- [ ] PR title is exactly: `wave6: security hardening baseline + release rollout package`
- [ ] scope confirmed: release packaging only, no new feature behavior
- [ ] commit list in PR body matches: `88328f4`, `afa2d83`, `8c08d95`, `3f1c1bc`, `4e6e58f`
- [ ] findings-to-fixes mapping present for all audit risks
- [ ] public contract changes documented (artifacts, reranker policy, auth, TTS, CI security gate)
- [ ] verification evidence attached (`324 passed`, security tests, smoke tests)
- [ ] rollout plan includes Stage A/B/C with token enablement procedure
- [ ] monitoring plan includes all three nightly workflows + artifact integrity checks
- [ ] rollback steps are config-driven and validated with operators
