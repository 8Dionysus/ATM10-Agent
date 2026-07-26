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
- action acceptance remains dry-run with `executed=false`.

The implementation anchors are:

- `src/atm10_agent/agent_core/atm10_session_probe.py`;
- `src/atm10_agent/perception/windows_capture.py`;
- `tests/test_atm10_session_probe_adapters.py`;
- `tests/test_windows_capture.py`;
- `tests/test_windows_product_edge_contract.py`.

## Dependency boundary

`pyproject.toml` declares no core runtime dependency. The `windows` extra owns
DXcam, NumPy, and Pillow. Compatibility requirements files must preserve the
same direction until they are replaced by reproducible resolution artifacts.

## Claim limit

Deterministic tests prove selection, normalization, fallback, and trace shape;
they do not prove a current physical ATM10 window or DXGI device. A release
checkpoint needs separate Windows 11 + PowerShell 7 evidence for:

1. selected ATM10 window and foreground/session posture;
2. selected capture backend and target;
3. successful screenshot artifact or explicit degraded fallback;
4. companion turn trace;
5. correlated dry-run action with no input emission.

No Linux run, provider smoke, or document statement substitutes for that live
evidence.
