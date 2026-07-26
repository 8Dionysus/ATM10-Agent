# Windows product-edge boundary

Windows 11 + PowerShell 7 remains the first ATM10 product-edge acceptance
path. Linux proves only the portable deterministic core.

## Contract

- ATM10 window/session identity uses the package-owned Win32 probe;
- explicit monitor or region capture prefers DXcam/DXGI;
- window-handle and fallback capture use Pillow;
- selected backend, target geometry, raw dimensions, resize, and DXcam errors
  are recorded in the capture result;
- capture dependencies live in the `windows` optional extra;
- deterministic core import and execution do not load those dependencies;
- absent push-to-talk evidence is recorded as an explicit degraded no-audio
  posture rather than silently omitted;
- action acceptance remains dry-run with `executed=false`.

The implementation anchors are:

- `src/atm10_agent/agent_core/atm10_session_probe.py`;
- `src/atm10_agent/perception/windows_capture.py`;
- `src/atm10_agent/windows_acceptance.py`;
- `schemas/windows_live_acceptance_v2.json`;
- `schemas/windows_live_acceptance_verification_v1.json`;
- `tests/test_atm10_session_probe_adapters.py`;
- `tests/test_windows_capture.py`;
- `tests/test_windows_product_edge_contract.py`;
- `tests/test_windows_live_acceptance.py`.

## Dependency boundary

`pyproject.toml` declares no core runtime dependency. The `windows` extra owns
DXcam, NumPy, and Pillow. `pylock.toml` records the dependency-free core
resolution; no parallel requirements-file graph exists.

## Claim limit

Deterministic tests prove selection, normalization, fallback, and trace shape;
they do not prove a current physical ATM10 window or DXGI device. A release
checkpoint needs separate Windows 11 + PowerShell 7 evidence for:

1. selected ATM10 window and foreground/session posture;
2. selected capture backend and target;
3. successful screenshot artifact or explicit degraded fallback;
4. push-to-talk evidence or explicit degraded no-audio posture;
5. companion turn trace;
6. correlated dry-run action with no input emission.

No Linux run, provider smoke, or document statement substitutes for that live
evidence.

The executable route is `atm10 windows-acceptance`. It returns non-zero and
writes a typed blocked/fail receipt when any required fact is absent. The
receipt and screenshot are local evidence under ignored `runs/`; they are not
committed release fixtures. `atm10 verify-windows-acceptance` independently
recomputes receipt semantics, source revision, freshness, safe relative
artifact paths, hashes, trace correlation, and the dry-run fence. That offline
check proves bundle consistency, not physical hardware authenticity.
