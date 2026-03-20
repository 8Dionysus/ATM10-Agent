# atm10-agent

Local game companion for ATM10 (Windows 11 + PowerShell 7): perception (screen/HUD), memory (RAG/KAG), safe automation (dry-run), voice.

## Quick links (canonical documents)

- `TODO.md` — execution plan (`Now/Next/Blocked/Done`).
- `PLANS.md` — goals, milestones, DoD, risks.
- `docs/RUNBOOK.md` — runnable commands and operational profiles.
- `docs/DECISIONS.md` — architecture decisions.
- `docs/SESSION_2026-03-13.md` — current session snapshot.
- `docs/SOURCE_OF_TRUTH.md` — document roles.

## Quickstart (Phase A smoke)

```powershell
cd D:\atm10-agent
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
python scripts/phase_a_smoke.py
python -m pytest
```

## Dependency profiles

```powershell
# Base runtime + test tools
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Voice optional profile
pip install -r requirements-voice.txt

# LLM optional profile
pip install -r requirements-llm.txt

# Export optional profile
pip install -r requirements-export.txt

# Dependency audit tooling
pip install -r requirements-audit.txt
python scripts/dependency_audit.py --runs-dir runs --policy report_only --with-security-scan true
```

## Current status (as of 2026-03-13)

- `python -m pytest` green (see CI and `docs/SESSION_2026-03-13.md` for the current snapshot).
- Active ASR path: `whisper_genai`; `qwen_asr` is archived/recoverable opt-in.
- KAG Neo4j nightly guardrail path is active: `build -> sync -> eval(sample+hard) -> guardrail-check -> trend snapshot`.
- Trend snapshot includes rolling-baseline, severity-policy (`signal_only|fail_nightly`) and calibration-aware thresholds (`latency warn=5.0`, `critical=15.0`).
- Gateway SLA path is extended with a trend-snapshot layer: `gateway_sla_summary_v1` history -> `gateway_sla_trend_snapshot_v1`.
- Gateway strict nightly path is active: the nightly workflow publishes `readiness/governance/progress/transition/remediation/integrity`, while `pytest.yml` stays `signal_only`.
- Remediation snapshot is integrated into nightly: source-of-truth for triage is `runs/nightly-gateway-sla-remediation/remediation_summary.json`.
- Integrity snapshot is integrated into nightly: machine-readable verdict for telemetry/dual-write/UTC guardrail is `runs/nightly-gateway-sla-integrity/integrity_summary.json`.
- Local fallback `G2` triage loop refreshed stale summaries on `2026-03-12T21:53:16Z`: `manual_nightly=accounted`, `remaining_for_window=11`, `remaining_for_streak=3`, `integrity_status=clean`.
- There is now a single local operator-pass helper: `scripts/run_gateway_sla_operating_cycle.py`. It reuses fresh same-UTC latest summaries and does not spend a new accounted run if the snapshot is already current.
- Streamlit operator panel shows the `G2 operating cycle` snapshot as the primary triage surface in `Latest Metrics`, while `fail_nightly progress/remediation/integrity` remain supporting drilldown views.
- `Safe Actions` in Streamlit remain smoke-only and do not run the `G2 operating cycle` helper.
- The automation safe loop has been extended: `intent_type=open_world_map` was added and completed through checklist `M6.19`.

## Where to look for details

- Detailed runs/results and chronology: `docs/SESSION_*.md`.
- Full runnable command set: `docs/RUNBOOK.md`.
- Archived/recoverable tracks: `docs/ARCHIVED_TRACKS.md`.

## License

TBD.
