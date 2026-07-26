# ATM10-Agent audit route

Read `AGENTS.md`, the nearest nested `AGENTS.md`, and
`docs/autonomy/README.md` before architecture or dependency work.

## Owner boundary

`ATM10-Agent` owns one installable companion loop, its provider interfaces,
Windows product-edge adapters, dry-run safety, traces, evals, public docs, and
repository checks. It does not own AoA doctrine, sibling repositories, or OS
Abyss runtime authority, and none of those surfaces may be required.

## Review-critical changes

- composition-root or turn-contract changes;
- any route that could emit keyboard, mouse, or destructive input;
- core/optional dependency movement;
- Windows session or capture behavior;
- trace/state/eval evidence boundaries;
- public commands, workflows, and support claims;
- downloads, services, ports, credentials, or large artifacts.

## Invariants

- `atm10_agent` is the only product package;
- product code never imports `scripts.*` or injects repository paths;
- action stays dry-run with `executed=false`;
- missing optional providers degrade at the use site;
- mutable state and append-only traces stay distinct;
- donor intake stays closed until standalone and Windows gates are green.

## Verify

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m scripts.validate_local_evals
python -m scripts.generate_decision_indexes --check
python -m scripts.validate_decision_records
python -m scripts.validate_nested_agents
python -m pytest
atm10 eval --suite companion-core --runs-dir runs\eval --state-dir .atm10-state\eval --reports-dir eval-results
```

Only report commands that actually ran. Keep live Windows evidence,
deterministic test evidence, and documentation claims explicitly separate.

## Audit report

State the owner surface, semantic change, safety/dependency effect, validation
run, unverified paths, residual risk, and the exact claim limit.
