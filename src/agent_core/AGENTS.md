# AGENTS.md

Local guidance for `src/agent_core/` in `ATM10-Agent`.

Read the root `AGENTS.md` first. This file only adds local rules for the shared runtime core.

## Scope

This directory includes the shared runtime and policy surface used by multiple entrypoints, including:

- `ops_policy.py`
- `service_sla.py`
- `combo_a_profile.py`
- `atm10_session_probe.py`
- `live_hud_state.py`
- `grounded_reply_openvino.py`
- `io_voice.py`
- `tts_runtime.py`
- `vlm.py`, `vlm_openai.py`, `vlm_openvino.py`, `vlm_stub.py`

## Local contract

- Keep the default path local-first and safe. Never silently turn a dry-run or safe-action path into real input behavior.
- `combo_a` stays additive. Do not move `combo_a` semantics into the baseline default by accident.
- Service wrappers and runtime probes must degrade cleanly when optional dependencies or local services are absent.
- Keep loopback and token handling env or config driven. Use patterns such as `ATM10_SERVICE_TOKEN`; do not hardcode reusable credentials.
- Make provider selection explicit. Stub, OpenVINO, and service-backed paths should remain easy to reason about in code and tests.

## Change rules

- Avoid heavy import-time work, especially model loading, service probing, or device enumeration.
- Preserve clear boundaries between policy, provider adapters, runtime clients, and presentation logic.
- When changing `service_sla.py`, `combo_a_profile.py`, or provider selection logic, update the matching tests and any affected script entrypoints in the same change.

## Validate

Run targeted core coverage before or alongside full pytest:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_service_sla.py tests/test_combo_a_profile.py tests/test_grounded_reply_openvino.py tests/test_tts_runtime.py tests/test_vlm_provider.py
```
