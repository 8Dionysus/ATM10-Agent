# Fedora local development companion runbook

This runbook is an additive path for `host_profile=fedora_local_dev`.
It is for portable-core and operator-companion stabilization in a Fedora-first workspace.
It is not a public Windows ATM10 product-edge replacement claim.

## Install

```bash
cd <repo-root>
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-linux-dev.txt
```

The Linux/Fedora dependency profile keeps the portable core away from Windows-only capture packages.
Windows ATM10 product-edge installs continue to use the default Windows-oriented runtime profile.

## Local validation seed

```bash
python -m pytest \
  tests/test_host_profiles.py \
  tests/test_atm10_session_probe_adapters.py \
  tests/test_readiness_scopes.py \
  tests/test_start_operator_fedora_dev.py
```

Expected result:

- `fedora_local_dev` exists as a preliminary host profile.
- Linux manual session probe returns `status=attention`, not `platform_not_supported`.
- `dev_companion` readiness accepts manual region capture without requiring Win32 ATM10 window identity.
- The Fedora launcher wrapper prints a command that delegates to `scripts/start_operator_product.py`.

## Print the resolved Fedora companion command

```bash
ATM10_CAPTURE_REGION=0,0,1920,1080 \
python scripts/start_operator_fedora_dev.py --print-only
```

The command payload has `schema_version=fedora_local_dev_start_command_v1`, `host_profile=fedora_local_dev`, and `readiness_scope=dev_companion`.

## Launch the managed companion surface

```bash
python scripts/start_operator_fedora_dev.py \
  --runs-dir runs/fedora-local-dev \
  --capture-region 0,0,1920,1080
```

The wrapper intentionally delegates to the canonical startup engine:

```bash
python scripts/start_operator_product.py \
  --runs-dir runs/fedora-local-dev \
  --host-profile fedora_local_dev \
  --start-voice-runtime \
  --start-tts-runtime \
  --start-pilot-runtime \
  --capture-region 0,0,1920,1080
```

Use `--print-only` first when changing capture geometry or passthrough flags.

## Pass through debug overrides

Arguments after `--` are forwarded to `scripts/start_operator_product.py`.

```bash
python scripts/start_operator_fedora_dev.py --print-only -- \
  --pilot-vlm-provider stub \
  --pilot-text-provider stub
```

This preserves the same diagnostics-only provider override available in the main runbook, without changing the host-profile policy.

## Companion readiness receipt

A minimal local readiness receipt can be produced without Win32 window identity:

```bash
python - <<'PY'
from datetime import datetime, timezone
from src.agent_core.atm10_session_probe import probe_atm10_session
from src.agent_core.readiness_scopes import evaluate_host_profile_session_readiness

probe = probe_atm10_session(
    capture_target_kind="region",
    capture_bbox=[0, 0, 1920, 1080],
    now=datetime.now(timezone.utc),
    platform_name="linux",
)
print(probe)
print(evaluate_host_profile_session_readiness(
    host_profile="fedora_local_dev",
    session_probe=probe,
))
PY
```

Expected readiness posture:

- `session_probe.status=attention` because Linux manual mode has no Win32 ATM10 window identity.
- `host_readiness_evaluation_v1.status=ok` under `readiness_scope=dev_companion` when a capture target is configured.
- `window_identity_unavailable` and `manual_capture_source_required` remain warnings, not product-edge parity claims.

## Promotion boundary

Do not update `MANIFEST.md` or README to claim Fedora public support from this runbook alone.
Promotion requires artifacted smoke evidence and an explicit support-tier update in `docs/PRODUCT_EDGE_POSTURE.md`.
