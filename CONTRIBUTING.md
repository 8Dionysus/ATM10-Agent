# Contributing to ATM10-Agent

Thank you for contributing.

## What belongs here

Good contributions:
- scripts, source modules, tests, and fixtures
- public-safe docs for setup, runbook, and source-of-truth surfaces
- gateway, retrieval, KAG, voice, operator-panel, and safe-automation improvements
- validation and smoke coverage that keeps the local-first product reproducible

Bad contributions:
- committed `runs/**`, private logs, or workstation-local artifacts
- secrets, tokens, or hardcoded credentials
- real input events enabled by default
- giant binaries, model payloads, or data drops that do not belong in git
- public docs with workstation-specific paths or unsanitized service detail

## Before opening a PR

Please make sure:
- Windows 11 + PowerShell 7 operability remains intact
- automation stays dry-run by default unless the change explicitly requires otherwise
- public docs use sanitized placeholders such as `<repo-root>`
- dependency weight, service auth, and artifact-policy changes are called out clearly

Recommended local setup and validation:

```powershell
cd <repo-root>
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pytest
```

If you touch a runnable entrypoint, also run the nearest documented smoke path.
Examples:

```powershell
python scripts/phase_a_smoke.py
python scripts/automation_intent_chain_smoke.py --intent-json tests/fixtures/intent_open_quest_book.json --runs-dir runs\smoke-intent
```

## Preferred PR scope

Prefer:
- 1 focused product or runtime change per PR
- or 1 focused test or smoke-path improvement
- or 1 focused public-docs correction

## Review criteria

PRs are reviewed for:
- reproducibility
- safety posture
- public-doc hygiene
- validation quality
- clarity about user-facing contract changes

## Security

Do not use public issues or pull requests for leaks, credentials, or sensitive operational detail.
Use the process in `SECURITY.md`.
