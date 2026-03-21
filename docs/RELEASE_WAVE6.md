# wave6: security hardening reference

## Purpose

Wave 6 captures the security-hardening baseline that was rolled into the public repository without adding new product features.
This document is a public engineering reference for the hardening scope, contract effects, rollout posture, and rollback model.

Canonical companion docs:

- `MANIFEST.md`
- `ROADMAP.md`
- `docs/RUNBOOK.md`
- `docs/SOURCE_OF_TRUTH.md`

## Scope

Wave 6 covers security-hardening and release-readiness work only:

- gateway artifact redaction and request-policy hardening
- optional HTTP service-token auth for gateway, voice, and TTS services
- TTS payload limits and sanitized internal-error handling
- workflow/action hardening for the security gate
- release rollout guidance and rollback posture

Not in scope:

- new end-user features
- breaking changes to public `gateway_request_v1` / `gateway_response_v1`
- permanent lock-down of local development flows

## Hardening Areas

| Area | Risk addressed | Durable change |
|---|---|---|
| Gateway artifacts | plaintext secrets in request artifacts | redact `request.json` before write; publish `run.json.request_redaction` metadata |
| Retrieval policy | untrusted reranker model path | allowlist `payload.reranker_model` for `reranker=qwen3`; explicit env override only |
| HTTP control plane | unauthenticated local services | optional token auth via `--service-token` / `ATM10_SERVICE_TOKEN`, requiring `X-ATM10-Token` when enabled |
| TTS HTTP path | oversized payloads and leaked internal details | payload limits, sanitized `500` envelope, redacted local `service_errors.jsonl` |
| CI / workflow governance | mutable action refs and weak security gate | critical GitHub Actions pinned to SHA; nightly dependency audit uses `fail_on_critical` |
| Script-level regression coverage | gaps around script entrypoints | direct tests for script entrypoints in addition to module-level tests |

## Public Contract Effects

1. Gateway artifacts
   - `request.json` is redacted by default.
   - `run.json` publishes `request_redaction` metadata (`applied`, `fields_redacted`, `checklist_version`).
2. Gateway retrieval policy
   - for `retrieval_query` + `reranker=qwen3`, `payload.reranker_model` is allowlisted.
   - invalid model input returns `invalid_request` (`HTTP 400` on the gateway HTTP path).
   - override remains explicit via `ATM10_ALLOW_UNTRUSTED_RERANKER_MODEL=true`.
3. Optional HTTP auth
   - gateway, voice, and TTS services support `--service-token` / `ATM10_SERVICE_TOKEN`.
   - when configured, `X-ATM10-Token` becomes mandatory.
   - unauthorized gateway requests return `error_code=unauthorized` and `HTTP 401`.
4. TTS HTTP hardening
   - payload limits are enforced (`max_request_bytes`, `max_json_depth`, `max_string_length`, `max_array_items`, `max_object_keys`).
   - internal `500` responses are sanitized.
   - diagnostic details go to redacted local service logs only.
5. CI / security governance
   - critical GitHub Actions are pinned to immutable refs.
   - nightly `dependency_audit --policy fail_on_critical` is the security-gate path.

## Validation Model

Wave 6 was validated through the normal repository regression and hardening surfaces:

- full `python -m pytest` regression baseline at rollout time
- targeted service tests for gateway, voice, and TTS auth/error paths
- dependency-audit checks for fail-on-critical behavior
- smoke validation for gateway HTTP, gateway SLA, and Streamlit operator surfaces

Representative expected outcomes:

- no plaintext secrets in gateway request artifacts
- reranker allowlist rejects untrusted model IDs unless explicit override is enabled
- gateway/voice/tts auth-required and auth-optional paths both behave as designed
- TTS payload-limit violations return `413`
- internal service failures remain sanitized on the HTTP surface
- nightly security gate fails on critical dependency/security findings

## Rollout Guidance

Recommended rollout posture:

1. Compatibility-first merge
   - merge with token auth disabled by default
   - confirm existing local clients and automation still behave compatibly
2. Staging auth enablement
   - configure `ATM10_SERVICE_TOKEN` where the service should require auth
   - validate both authorized and unauthorized behavior for gateway, voice, and TTS
   - verify health/smoke paths with `X-ATM10-Token`
3. Production enablement
   - enable service-token auth only where it is operationally justified
   - keep backward-compatible open-mode rollback available through config removal

## Monitoring

Recommended monitoring focus after rollout:

- nightly `security-nightly`
- nightly `gateway-sla-readiness-nightly`
- nightly `kag-neo4j-guardrail-nightly`
- artifact/log integrity for redaction-sensitive paths
- unexpected `401 unauthorized` spikes after auth enablement
- any sign of plaintext secret material in request artifacts or local service logs

## Rollback

Primary rollback remains config-driven:

- unset `ATM10_SERVICE_TOKEN` for affected services
- restart the corresponding runtime
- return to backward-compatible open mode without reverting API contracts

Operationally, this means Stage C can be paused or partially rolled back without undoing the broader hardening baseline.

## Related Policies

- `docs/RUNBOOK.md` contains runnable local commands, with public-safe placeholders for paths and tokens.
- `MANIFEST.md` and `ROADMAP.md` remain the public current-state and direction surfaces.
- `docs/SOURCE_OF_TRUTH.md` defines the public-doc boundary and the split between public and local-only docs.
