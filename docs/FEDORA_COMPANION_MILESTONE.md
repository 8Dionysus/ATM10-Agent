# Fedora companion milestone

This document defines the first bounded milestone for `host_profile=fedora_local_dev`.
It is a development-companion checkpoint, not a Fedora ATM10 product-edge support claim.

## Scope

The milestone proves that the portable companion core can be exercised from a Fedora-first workspace with explicit limits:

- `fedora_local_dev` is selected deliberately.
- Readiness is evaluated under `dev_companion`, not `product_edge`.
- Capture is manual region or monitor based.
- The Linux session probe may report unavailable window identity without becoming an error.
- Startup delegates to `scripts/start_operator_product.py` rather than creating a second engine.
- Managed voice, TTS, and pilot runtime flags are declared in the resolved command payload.
- Automation remains dry-run bounded; unsafe execution flags are not part of the receipt.
- `ATM10_DIR` or launcher discovery yields a known ATM10 instance path for a real local milestone receipt.

## Receipt

Generate a real local receipt:

```bash
ATM10_DIR=/path/to/ATM10 \
python scripts/write_fedora_companion_receipt.py \
  --runs-dir runs/fedora-companion-receipt \
  --capture-region 0,0,1920,1080
```

The artifact is written as:

```text
runs/fedora-companion-receipt/<timestamp>/fedora_companion_milestone_receipt.json
```

The receipt contains:

- `startup_payload`
- `session_probe`
- `readiness_evaluation`
- `instance_discovery_report`
- `milestone_evaluation`

A real local milestone receipt should have:

```text
milestone_evaluation.status=ok
milestone_evaluation.blocking_reason_codes=[]
```

## CI mechanics smoke

CI can validate the receipt machinery without depending on a local ATM10 installation:

```bash
python scripts/write_fedora_companion_receipt.py \
  --runs-dir runs/ci-fedora-companion-receipt \
  --capture-region 0,0,1920,1080 \
  --allow-missing-atm10-dir \
  -- \
  --pilot-vlm-provider stub \
  --pilot-text-provider stub
```

`--allow-missing-atm10-dir` skips the `atm10_instance_path_known` criterion and must not be used as promotion evidence for a real local companion milestone.

## Promotion boundary

Do not update README or `MANIFEST.md` to claim Fedora product-edge support from this milestone alone.
Promotion requires explicit support-tier language in `docs/PRODUCT_EDGE_POSTURE.md`, green validation for the named tier, and a separate decision about whether Linux ATM10/Minecraft parity is actually supported.
