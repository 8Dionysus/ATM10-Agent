# MANIFEST.md

Актуально на: 2026-02-24

## Snapshot

- Проект: `atm10-agent`
- Target platform: Windows 11 + PowerShell 7
- Target Python: 3.11+ (проверено на 3.12.10)
- Текущий status tests: `186 passed` (`python -m pytest`)

## Active capabilities

- Phase A: `scripts/phase_a_smoke.py` (screenshot -> run artifacts).
- Phase B retrieval: `normalize -> retrieve -> eval` + profile layer `baseline|ov_production`.
- KAG: file baseline + Neo4j (`build -> sync -> query -> eval`).
- KAG nightly guardrail: `.github/workflows/kag-neo4j-guardrail-nightly.yml`.
- Trend snapshot: `scripts/kag_guardrail_trend_snapshot.py` (rolling-baseline + severity flags + `critical_policy`).
- Automation: dry-run stack (`automation_dry_run`, `intent_to_automation_plan`, `automation_intent_chain_smoke`, `check_automation_smoke_contract`).
- CI core smoke summaries: `scripts/collect_smoke_run_summary.py` (`phase_a_smoke|retrieve_demo|eval_retrieval` -> `smoke_summary.json`).

## Canonical docs

- Execution plan: `TODO.md`
- Goals/milestones: `PLANS.md`
- Runnable commands: `docs/RUNBOOK.md`
- Architecture decisions: `docs/DECISIONS.md`
- Session history: `docs/SESSION_2026-02-24.md`
- Doc roles/policy: `docs/SOURCE_OF_TRUTH.md`
- Archived tracks: `docs/ARCHIVED_TRACKS.md`

## Data/commit policy (short)

Never commit:

- `models/**`
- `data/**` dumps
- `runs/**`
- `.codex/**/logs/**`
- secrets/tokens
