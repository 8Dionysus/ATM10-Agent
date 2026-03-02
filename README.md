# atm10-agent

Локальный game companion для ATM10 (Windows 11 + PowerShell 7): perception (screen/HUD), memory (RAG/KAG), safe automation (dry-run), voice.

## Быстрые ссылки (каноничные документы)

- `TODO.md` — execution-план (`Now/Next/Blocked/Done`).
- `PLANS.md` — цели, milestones, DoD, риски.
- `docs/RUNBOOK.md` — runnable команды и операционные профили.
- `docs/DECISIONS.md` — архитектурные решения.
- `docs/SESSION_2026-03-02.md` — текущий session snapshot.
- `docs/SOURCE_OF_TRUTH.md` — роли документов.

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

## Current status (as of 2026-03-02)

- `python -m pytest` green (см. CI и `docs/SESSION_2026-03-02.md` для актуального snapshot).
- Active ASR path: `whisper_genai`; `qwen_asr` — archived/recoverable opt-in.
- KAG Neo4j nightly guardrail path активен: `build -> sync -> eval(sample+hard) -> guardrail-check -> trend snapshot`.
- Trend snapshot включает rolling-baseline, severity-policy (`signal_only|fail_nightly`) и calibration-aware thresholds (`latency warn=5.0`, `critical=15.0`).
- Gateway SLA path расширен trend snapshot слоем: `gateway_sla_summary_v1` history -> `gateway_sla_trend_snapshot_v1`.
- Gateway `fail_nightly` rollout (`master_available`) остается staged: readiness + governance + progress работают в nightly, без hard-gate в `pytest` smoke.
- Gateway transition/bootstrap слой (`release_only`) не считается активным в default branch до `planned_resync`.

## Где смотреть детали

- Детальные run/result и хронология: `docs/SESSION_*.md`.
- Полный runnable набор команд: `docs/RUNBOOK.md`.
- Архивные/recoverable треки: `docs/ARCHIVED_TRACKS.md`.

## License

TBD.
