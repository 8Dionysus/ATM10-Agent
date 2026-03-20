## Release Handoff (Wave 6 Security Baseline)

### What was merged in this PR

- Security hardening baseline without new product features.
- Backward compatibility preserved by default (auth opt-in).
- Contract `gateway_response_v1` unchanged.

Commits:

- `88328f4` gateway redaction + reranker allowlist
- `afa2d83` optional token auth (gateway/voice)
- `8c08d95` tts payload limits + sanitized errors
- `3f1c1bc` action SHA pinning + security-nightly
- `4e6e58f` tests/docs/release sync

### Contract changes (for operators and clients)

1. Gateway artifacts:
   `request.json` is redacted by default; `run.json` includes `request_redaction`.
2. Gateway request policy:
   for `retrieval_query` + `reranker=qwen3`, the model is constrained by an allowlist;
   invalid model -> `invalid_request` (HTTP 400).
3. Optional auth for gateway/voice/tts:
   when `ATM10_SERVICE_TOKEN` is set, header `X-ATM10-Token` is required, otherwise `401`.
4. TTS hardening:
   payload limits + sanitized internal `500`; details only in redacted `service_errors.jsonl`.
5. CI governance:
   critical actions pinned to SHA; nightly security gate enabled.

### Verification evidence

- `python -m pytest` -> `324 passed`
- gateway HTTP smoke core -> `status=ok`
- gateway SLA signal-only -> `status=ok`, `sla_status=pass`
- Streamlit operator panel smoke -> `status=ok`

Canonical artifacts:

- `runs/20260302_144210-wave6-release/release_summary.json`
- `runs/20260302_142741-security_audit_wave2_5/security_audit_summary.json`
- `runs/20260302_153619-wave6-pr-packaging/pr_packaging_summary.json`

### Rollout A/B/C

Stage A (merge, default open mode):

- do not set `ATM10_SERVICE_TOKEN`;
- confirm backward compatibility for existing clients/automation.

Stage B (staging token-on):

- set `ATM10_SERVICE_TOKEN` in staging;
- verify gateway/voice/tts:
  - without token -> `401`,
  - with token -> successful response;
- run health/smoke with `X-ATM10-Token`.

Stage C (production token-on):

- enable token policy in production where applicable;
- monitor `401` dynamics and smoke/SLA stability.

### Monitoring (7 days)

Check daily:

- `security-nightly`
- `gateway-sla-readiness-nightly`
- `kag-neo4j-guardrail-nightly`
- artifact redaction integrity:
  - `run.json.request_redaction` in gateway runs,
  - redacted `service_errors.jsonl`,
  - no plaintext secrets.

Escalation:

- any plaintext secret in artifacts;
- unexpected growth of `401 unauthorized` after Stage B/C;
- failure in the nightly security gate.

### Rollback (fast path)

- unset `ATM10_SERVICE_TOKEN` in the target runtime;
- restart services;
- services return to backward-compatible open mode without code rollback.
