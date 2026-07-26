# ATM10-Agent runbook

Active runnable commands only. Historical experiments and recoverable provider
tracks belong in `docs/ARCHIVED_TRACKS.md`.

## Prerequisites

- Python 3.11 or newer;
- Git;
- Windows 11 + PowerShell 7 for product-edge acceptance.

The deterministic core does not need a model, service, game window, database,
network connection, or sibling repository.

## Install

From PowerShell:

```powershell
cd <repo-root>
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install . --no-deps
```

For repository development:

```powershell
python -m pip install -e ".[dev]"
```

For Windows capture:

```powershell
python -m pip install -e ".[windows]"
```

OpenVINO and voice providers are explicit extras:

```powershell
python -m pip install -e ".[openvino]"
python -m pip install -e ".[voice]"
```

## Verify the core posture

```powershell
atm10 doctor
```

Expected invariants include an empty core dependency list, deterministic stub
provider, and `dry_run_only` action default.

## Run one complete deterministic turn

```powershell
atm10 run `
  --prompt "Describe actionable ATM10 context." `
  --query "steel tools" `
  --action-intent open_quest_book `
  --runs-dir runs\local `
  --state-dir .atm10-state `
  --memory-dir .atm10-memory
```

The command traverses every product stage and prints an
`atm10_companion_turn_v1` result. It writes:

- `runs/local/<turn>/turn.json`;
- `runs/local/<turn>/action.json`;
- append-only trace records under `runs/local/`;
- mutable state under `.atm10-state/`;
- append-only memory objects and mutable working context under
  `.atm10-memory/`.

Use `--world-docs <path-to-world-jsonl>` for a different file-backed world,
`--image <path-to-image>` for an existing image, or `--voice` to exercise the
explicit no-provider degradation path.

## Replay without providers

```powershell
atm10 replay <path-to-turn-json> `
  --runs-dir runs\replay `
  --state-dir .atm10-state `
  --memory-dir .atm10-memory
```

Replay checks the saved turn schema and writes new trace evidence with
`replay_of` pointing to the source turn. It does not rerun perception, stores,
models, voice, or action providers.

## Run the product eval

```powershell
atm10 eval `
  --suite companion-core `
  --runs-dir runs\eval `
  --state-dir .atm10-state\eval `
  --reports-dir eval-results `
  --memory-dir .atm10-memory\eval
```

The seven deterministic cases cover stub execution, cited file world/KAG,
canonical actions, voice degradation, state/trace separation, useful
negatives, and replay. The v2 report records a bounded claim, categorical
verdict, scope, provenance, blind spots, portability limits, and
measurement-only metrics. The command returns non-zero unless the suite
supports its full bounded claim.

## Consolidate captured memory candidates

```powershell
atm10 consolidate-memory `
  --memory-dir .atm10-memory
```

Online turns append observed world state and player episodes while replacing
only `working-context.json`. Consolidation is a separate offline step: it
derives idempotent `proposed` semantic-game-knowledge and procedural-gameplay
candidates. It never confirms, freezes, or promotes them, and a dry-run action
episode does not establish gameplay effectiveness. `.atm10-memory/` is ignored
local product data; do not commit personal queries or captured play history.

## M6.19 rollout records

The public intent -> plan -> dry-run chain is now package-owned. These intents
remain canonical:

- `open_quest_book`;
- `check_inventory_tool`;
- `open_world_map`.

Each intent produces deterministic plan and action artifacts correlated by
`intent_id` and `trace_id`. The executor contract always reports
`dry_run=true` and `executed=false`; it never emits keyboard or mouse input.

## Windows session and capture checks

The pure contracts can be checked on any development host:

```powershell
python -m pytest -q `
  tests/test_atm10_session_probe_adapters.py `
  tests/test_windows_capture.py `
  tests/test_windows_product_edge_contract.py
```

`atm10_agent.perception.windows_capture.capture_screen_image` is Windows-only
at the use site:

- an ATM10 window handle uses Pillow window capture;
- explicit monitor or region capture prefers DXcam/DXGI;
- a DXcam failure falls back to Pillow and records `backend_errors`;
- logical/native dimension changes are recorded through `raw_width`,
  `raw_height`, and `resized_from`.

Live Windows acceptance is separate from these deterministic tests and must
record the selected ATM10 window/session, capture source, screenshot metadata,
explicit audio posture, turn trace, and dry-run action result.

With an ATM10 world open and its window in the foreground:

```powershell
python -m pip install -e ".[windows]"
$revision = git rev-parse HEAD
$acceptance = atm10 windows-acceptance `
  --repo-root . `
  --source-revision $revision `
  --settle-seconds 5 `
  --evidence-dir runs\windows-live-acceptance `
  --state-dir .atm10-state\windows-live-acceptance | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) {
  throw "ATM10 Windows live acceptance did not pass"
}
atm10 verify-windows-acceptance `
  $acceptance.receipt `
  --source-revision $revision `
  --max-age-hours 24
if ($LASTEXITCODE -ne 0) {
  throw "ATM10 Windows evidence bundle did not verify"
}
```

After starting the command, return focus to ATM10 during the five-second
settling window. The collector does not change foreground focus itself.

The collector writes a `windows_live_acceptance_v2` receipt, local screenshot,
and hashed turn artifacts under the ignored evidence directory. It verifies
Windows 11, PowerShell 7, source revision, ATM10 window
identity/foreground posture, capture intersection, a DXcam-first capture with
explicit Pillow fallback, live-image consumption, cited response, turn trace
correlation, `dry_run=true`, and `executed=false`. Until push-to-talk is
exercised by this lane, the receipt passes only with
`audio.mode=degraded_no_audio`, `degraded=true`, and an explicit warning.

The second command recomputes semantics and hashes from the complete receipt
directory, requires the exact source revision, and rejects evidence older than
24 hours. It is a consistency verifier, not independent physical-host
attestation. Keep the entire receipt directory together when moving evidence
between trusted machines. Screenshots can contain private on-screen material
and must not be committed.

## Focused data and provider tools

The remaining `scripts/` directory contains maintainer tools, not another
application. Common source-owned tools include:

```powershell
python -m scripts.discover_instance --runs-dir runs\instance-discovery
python -m scripts.normalize_ftbquests --help
python -m scripts.retrieve_demo --help
python -m scripts.kag_build_baseline --help
python -m scripts.kag_query_demo --help
python -m scripts.openvino_diag --help
```

A degraded hybrid run may write `stressor_receipt.json` beside its normal run
artifacts. Its bounded meaning is defined in
`docs/ANTIFRAGILITY_FIRST_WAVE.md`; the receipt records degradation and never
authorizes mutation.

Neo4j examples must use an operator-provided local credential:

```powershell
$env:NEO4J_PASSWORD = "<set-local-neo4j-password>"
```

No active command uses `ATM10_SERVICE_TOKEN`; the old local HTTP service plane
has been retired.

## Repository validation

```powershell
python -m scripts.validate_local_evals
python -m scripts.generate_decision_indexes --check
python -m scripts.validate_decision_records
python -m scripts.validate_nested_agents
python -m pytest
```

Release validation additionally builds an sdist and wheel, installs the wheel
without dependencies outside the checkout, runs `atm10 doctor`, and executes
the deterministic turn, replay, and `companion-core` eval:

```powershell
python -m build
python -m scripts.verify_release --dist-dir dist
```

The generated `dist/release_verification.json` records artifact hashes,
dependency metadata, and command-result hashes. It proves only the
dependency-free core; optional providers and live Windows capture remain
separate gates. `pylock.toml` is the resolved core lock: because core has no
third-party dependencies, it contains only the local `atm10-agent` package.

## Troubleshooting

If `atm10` is not found, reactivate the virtual environment and reinstall the
package. If an optional provider import fails, install only its declared
extra; do not add it to the core.

If capture fails:

1. confirm Windows 11 and the `windows` extra;
2. verify the ATM10 window is visible and not minimized;
3. inspect `backend_errors` before treating Pillow fallback as full DXcam
   success;
4. keep live evidence distinct from deterministic unit-test evidence.

Do not bypass `docs/intake/donor-ledger.json`, add sibling checkout
requirements, or restore the retired control plane to repair an optional
provider.
