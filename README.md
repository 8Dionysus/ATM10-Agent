# atm10-agent

Локальный **game companion** агент для ATM10: практичный ассистент, который умеет *видеть* игру (screenshot), *вспоминать* знания (RAG), и *отвечать* (text/voice). Проект ориентирован на **Windows 11 + PowerShell 7** и на разработку через Codex workflow (small diffs, reproducible commands).

## Как устроена документация репозитория

* `README.md` — для людей: что это и как запустить.
* `AGENTS.md` — для coding agents: commands, boundaries, стиль, Definition of Done (DoD).
* `TODO.md` — боевой backlog.
* `PLANS.md` — milestones и общий план.
* `docs/RUNBOOK.md` и `docs/DECISIONS.md` — будут заполняться позже (через Codex).

---

## Quickstart (Phase A smoke)

Цель: доказать, что dev loop работает end-to-end **без** скачивания тяжёлых моделей.

1. Создай venv (Python 3.11 рекомендован):

```powershell
cd D:\atm10-agent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

2. Установи dependencies:

```powershell
pip install -r requirements.txt
```

3. Запусти Phase A smoke:

```powershell
python scripts/phase_a_smoke.py
```

4. Запусти tests:

```powershell
python -m pytest
```

Примечание: если `requirements.txt` или `scripts/phase_a_smoke.py` ещё не созданы — см. `TODO.md` (P0/P1) и `PLANS.md` (M0/M1).

---

## Configuration (env vars)

Пути к Minecraft/инстансу **не хардкодим**. Используем env vars (и/или discovery script позже):

* `MINECRAFT_DIR` — корень `.minecraft` (пример: `C:\Users\Admin\AppData\Roaming\.minecraft`)
* `ATM10_DIR` — папка инстанса ATM10 (пример: `...\versions\All the Mods 10 - ATM10 All the Mods 10-5.2`)

Пример (PowerShell):

```powershell
$env:MINECRAFT_DIR="C:\Users\Admin\AppData\Roaming\.minecraft"
$env:ATM10_DIR="C:\Users\Admin\AppData\Roaming\.minecraft\versions\All the Mods 10 - ATM10 All the Mods 10-5.2"
```

---

## Roadmap

### Phase A — Vision loop (сейчас)

**Screenshot → VLM interface (stub) → console output + artifacts**

Definition of Done:

* создаётся `runs/<timestamp>/`
* сохраняется `screenshot.png`, `run.json`, `response.json`
* `python -m pytest` проходит

### Phase B — Memory (RAG)

**Ingest quest/wiki data → vector store (Qdrant) → retrieval-backed ответы**

* нормализация источников в JSONL
* retrieval возвращает top-k chunks + citations (id/source/path)

### Phase C — Voice (опционально)

**ASR (Whisper) + TTS (lightweight)**

* push-to-talk → transcribe → answer → speak
* voice не ломает core (Phase A/B должны работать без него)

---

## Architecture (one-screen mental model)

**Perception** (screen capture / HUD text)
→ **Interpretation** (VLM: “what do I see / what matters?”)
→ **Recall** (RAG: quests + guides + recipes)
→ **Action** (answer, plan, optional hotkeys later)
→ **Trace** (logs + artifacts for debugging)

---

## Repo map

* `src/agent_core/` — agent loop orchestration (perception→reason→act)
* `src/minecraft_io/` — screen capture, hotkeys, UI helpers
* `src/rag/` — ingestion, normalization, vector store adapters
* `scripts/` — runnable entry points (smoke runs, ingest jobs)
* `tests/` — pytest suite
* `docs/` — RUNBOOK/DECISIONS (будут заполнены позже)
* `.codex/` — Codex project config и logs (локально)

---

## Models (baseline + why)

На старте важно иметь **baseline**, который гарантированно работает, а затем — спокойно swap-ать engines без переписывания capture/RAG/logging.

Рекомендация: Phase A делаем engine-agnostic (VLM за interface). Конкретную модель/движок фиксируем в RUNBOOK/config позже.

---

## Data (что куда класть)

Рекомендуемые локальные папки (не коммитим):

* `data/ftbquests_raw/` — сырьё квестов (SNBT/JSON-like)
* `data/ftbquests_norm/` — нормализованные записи (JSONL)
* `data/wiki/` — guides/notes/scraped pages (опционально)
* `models/` — model artifacts (never commit)
* `runs/` — run artifacts (screenshots, logs, traces)

---

## Troubleshooting (Windows)

* PowerShell execution policy может блокировать `Activate.ps1`: разреши локальные скрипты или запускай Python через `.venv\Scripts\python.exe`.
* Long paths: держи workspace ближе к корню диска (пример: `D:\atm10-agent`) и используй `pathlib`.
* Docker ports: если Phase B поднимает Qdrant — проверь, что порты свободны.

---

## Safety / fair play note

Если добавишь automation (hotkeys/mouse), держи это в singleplayer/local и уважай правила серверов. Проект задуман как assistive companion, а не как multiplayer exploit tool.

---

## License

TBD.