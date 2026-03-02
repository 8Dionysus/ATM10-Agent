## Release Handoff (Wave 6 Security Baseline)

### Что merged в этом PR

- Security hardening baseline без новых продуктовых фич.
- Backward compatibility сохранена по умолчанию (auth opt-in).
- Контракт `gateway_response_v1` не менялся.

Коммиты:

- `88328f4` gateway redaction + reranker allowlist
- `afa2d83` optional token auth (gateway/voice)
- `8c08d95` tts payload limits + sanitized errors
- `3f1c1bc` action SHA pinning + security-nightly
- `4e6e58f` tests/docs/release sync

### Контрактные изменения (для операторов и клиентов)

1. Gateway artifacts:
   `request.json` redacted-by-default; в `run.json` есть `request_redaction`.
2. Gateway request policy:
   для `retrieval_query` + `reranker=qwen3` модель ограничена allowlist;
   invalid model -> `invalid_request` (HTTP 400).
3. Optional auth для gateway/voice/tts:
   при заданном `ATM10_SERVICE_TOKEN` обязателен заголовок `X-ATM10-Token`, иначе `401`.
4. TTS hardening:
   payload limits + sanitized internal `500`; детали только в redacted `service_errors.jsonl`.
5. CI governance:
   critical actions pinned to SHA; nightly security gate включен.

### Verification evidence

- `python -m pytest` -> `324 passed`
- gateway HTTP smoke core -> `status=ok`
- gateway SLA signal-only -> `status=ok`, `sla_status=pass`
- streamlit operator panel smoke -> `status=ok`

Canonical artifacts:

- `runs/20260302_144210-wave6-release/release_summary.json`
- `runs/20260302_142741-security_audit_wave2_5/security_audit_summary.json`
- `runs/20260302_153619-wave6-pr-packaging/pr_packaging_summary.json`

### Rollout A/B/C

Stage A (merge, default open mode):

- не задавать `ATM10_SERVICE_TOKEN`;
- подтвердить обратную совместимость существующих клиентов/автоматизации.

Stage B (staging token-on):

- задать `ATM10_SERVICE_TOKEN` в staging;
- проверить gateway/voice/tts:
  - без токена -> `401`,
  - с токеном -> успешный ответ;
- прогнать health/smoke с `X-ATM10-Token`.

Stage C (production token-on):

- включить token policy в production where applicable;
- мониторить динамику `401` и стабильность smoke/SLA.

### Monitoring (7 days)

Ежедневно проверить:

- `security-nightly`
- `gateway-sla-readiness-nightly`
- `kag-neo4j-guardrail-nightly`
- integrity артефактов redaction:
  - `run.json.request_redaction` у gateway runs,
  - redacted `service_errors.jsonl`,
  - отсутствие plaintext секретов.

Escalation:

- любой plaintext secret в артефактах;
- неожиданный рост `401 unauthorized` после Stage B/C;
- fail в nightly security gate.

### Rollback (быстрый путь)

- снять `ATM10_SERVICE_TOKEN` в целевом runtime;
- перезапустить сервисы;
- сервисы вернутся в backward-compatible open mode без отката кода.

