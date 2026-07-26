# AGENTS.md

Local guidance for `src/` in `ATM10-Agent`.

Read the root `AGENTS.md` first. This file only adds local rules for source modules.

## Scope

This directory contains the single installable `atm10_agent` product package.
`pyproject.toml` and the `atm10` CLI own package discovery and composition;
repository-path injection is forbidden.

Nearest-file precedence applies here:

- `src/atm10_agent/agent_core/AGENTS.md`
- `src/atm10_agent/rag/AGENTS.md`
- `src/atm10_agent/kag/AGENTS.md`
- `src/atm10_agent/hybrid/AGENTS.md`

When a deeper file exists, follow that deeper file for work inside that subtree.

## Local contract

- Keep module imports cheap and side-effect light. Do not require live services, local models, game windows, or hardware devices just to import a module.
- Prefer config or env driven paths, URLs, and credentials over hardcoded values.
- Preserve Windows 11 + PowerShell 7 operability and public-safe portability.
- Keep shared types, artifact shapes, and return contracts explicit. If a source change affects a script or test surface, update both in the same diff.
- Prefer small helpers and targeted seams over broad rewrites across `src/`.

## Change rules

- Put domain-specific logic in the owning package instead of leaking it across packages.
- Product orchestration enters through `atm10_agent.app.CompanionApp`; optional
  gateways, UIs, stores, voice, or hardware adapters may not create a second
  product composition root.
- Keep optional dependency handling graceful. Missing voice, OpenVINO, Neo4j, or Qdrant extras should fail clearly at the use site, not at import time.
- Do not hide semantic contract changes behind refactors or formatting-only wording.

## Validate

At minimum:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pytest
```

If behavior changes cross the package boundary, run the nearest smoke or contract path from `scripts/` too.
