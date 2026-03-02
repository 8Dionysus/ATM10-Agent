# RELEASE WAVE 6 — Security Hardening Baseline

## Scope

Release-only wave (no new product features):

- finalize security hardening changes,
- keep backward compatibility by default,
- provide staged rollout and monitoring playbook.

## Findings -> Fixes Mapping

| Finding ID | Risk | Fix | Evidence (files/tests) |
|---|---|---|---|
| `high_secret_leak_gateway_request_artifacts` | Secrets could be written in plaintext to `request.json` | Gateway request artifact is redacted before write; `run.json` includes `request_redaction` metadata | `scripts/gateway_v1_local.py`, `scripts/gateway_artifact_policy.py`, `tests/test_gateway_v1_local.py`, `tests/test_gateway_v1_http_service.py` |
| `high_untrusted_reranker_model_path` | Untrusted model id path for qwen3 reranker | `payload.reranker_model` allowlist + explicit trusted override (`ATM10_ALLOW_UNTRUSTED_RERANKER_MODEL=true`) | `scripts/gateway_v1_local.py`, `tests/test_gateway_v1_local.py`, `tests/test_gateway_v1_http_service.py` |
| `medium_missing_optional_service_auth` | No auth when service bound outside localhost | Optional token auth for gateway/voice/tts (`--service-token` or `ATM10_SERVICE_TOKEN`) requiring `X-ATM10-Token` | `scripts/gateway_v1_http_service.py`, `scripts/voice_runtime_service.py`, `scripts/tts_runtime_service.py`, related auth tests |
| `medium_tts_http_hardening_gap` | No payload limits and raw internal errors | TTS payload hard limits + sanitized `500` + local redacted `service_errors.jsonl` | `scripts/tts_runtime_service.py`, `tests/test_tts_runtime_service.py` |
| `low_workflow_supply_chain_pinning` | Mutable action tags in CI | Critical GitHub Actions pinned to commit SHA | `.github/workflows/*.yml` |
| `low_security_gate_strength` | Nightly security not strictly enforced | Added nightly security workflow + `fail_on_critical` now fails if security scan status is not `ok/skipped` | `.github/workflows/security-nightly.yml`, `scripts/dependency_audit.py`, `tests/test_dependency_audit.py` |
| `low_script_level_coverage_gap` | Script entrypoints not directly tested | Added script-level tests for `normalize_ftbquests.py` and `ingest_qdrant.py` | `tests/test_normalize_ftbquests_script.py`, `tests/test_ingest_qdrant_script.py` |

## Release Verification

Mandatory pre-merge checks:

```powershell
python -m pytest
python scripts/gateway_v1_http_smoke.py --scenario core --runs-dir runs/ci-release-gateway-http-core --summary-json runs/ci-release-gateway-http-core/gateway_http_smoke_summary.json
python scripts/check_gateway_sla.py --http-summary-json runs/ci-release-gateway-http-core/gateway_http_smoke_summary.json --summary-json runs/ci-release-gateway-sla/gateway_sla_summary.json --profile conservative --policy signal_only --runs-dir runs/ci-release-gateway-sla
python scripts/streamlit_operator_panel_smoke.py --panel-runs-dir runs --runs-dir runs/ci-release-streamlit --summary-json runs/ci-release-streamlit/streamlit_smoke_summary.json --gateway-url http://127.0.0.1:8770 --startup-timeout-sec 45
```

Expected:

- pytest green,
- gateway http smoke `status=ok`,
- gateway sla checker `status=ok` and `sla_status=pass`,
- streamlit smoke `status=ok`.

## Staged Rollout (Auth)

### Stage A — Merge with default behavior

- Merge with service token disabled (default).
- Ensure all existing automation/clients continue to work unchanged.

### Stage B — Staging token enablement

1. Configure token in staging runtime:

```powershell
$env:ATM10_SERVICE_TOKEN="<staging-token>"
```

2. Start services with same runtime profile.
3. Validate:
   - `GET /healthz` / `GET /health` with and without `X-ATM10-Token`.
   - one positive and one negative gateway request.
   - voice/tts endpoints with authorized and unauthorized requests.

### Stage C — Production token enablement

- Roll token to production runtime where applicable.
- Ensure operators know required header contract (`X-ATM10-Token`).
- Keep rollback path: unset token env -> backward-compatible open mode.

## Post-merge Monitoring (7 days)

Daily checks:

1. `security-nightly` workflow status and artifacts (`runs/nightly-security-audit`).
2. `gateway-sla-readiness-nightly` workflow status and trend drift.
3. `kag-neo4j-guardrail-nightly` workflow status and trend snapshot.
4. Error logs consistency:
   - gateway redaction metadata present,
   - `service_errors.jsonl` in voice/tts contain redacted entries,
   - no plaintext secrets in run artifacts.

Escalate if:

- nightly security gate fails,
- unauthorized errors spike unexpectedly in staging/production,
- any plaintext secret appears in artifacts.
