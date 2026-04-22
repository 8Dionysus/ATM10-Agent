# Windows product-edge boundary

Windows remains the first-class ATM10 product-edge acceptance path while Fedora develops as an additive companion workspace.

## Contract

The Windows edge is intentionally explicit:

- default host profile: `ov_intel_core_ultra_local`
- readiness scope: `product_edge`
- window identity mode: `win32_atm10_window`
- session probe backend: `windows_win32`
- preferred capture backend: `dxcam_dxgi`
- Windows dependency pack: `requirements-win-edge.txt`
- portable core dependency pack: `requirements-core.txt`

The contract is represented by `src/agent_core/windows_product_edge_contract.py` and covered by `tests/test_windows_product_edge_contract.py`.

## Why this exists

Fedora-first development should improve the portable core without quietly weakening the ATM10/Minecraft Windows edge.
A Linux/Fedora companion receipt can prove manual capture, dev-companion readiness, and local operator ergonomics.
It does not prove Win32 window discovery, DXGI capture, or Windows ATM10 acceptance.

## Validation

Run the pure contract tests:

```bash
python -m pytest -q tests/test_windows_product_edge_contract.py
```

The dependency boundary must stay shaped like this:

```text
requirements.txt -> requirements-win-edge.txt -> requirements-core.txt
requirements-win-edge.txt contains dxcam
requirements-core.txt does not contain dxcam
```

## Promotion boundary

Do not promote Fedora or any future host profile by editing the default profile in place.
Additive profiles must keep their own profile id, readiness scope, workflow evidence, and support language.
