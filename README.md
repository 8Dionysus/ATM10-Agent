# atm10-agent

Локальный **game companion** агент для ATM10: практичный ассистент, который умеет *видеть* игру (screenshot), *вспоминать* знания (RAG), и *отвечать* (text/voice). Проект ориентирован на **Windows 11 + PowerShell 7** и на разработку через Codex workflow (small diffs, reproducible commands).

## Как устроена документация репозитория

* `README.md` — для людей: что это и как запустить.
* `AGENTS.md` — для coding agents: commands, boundaries, стиль, Definition of Done (DoD).
* `TODO.md` — боевой backlog.
* `PLANS.md` — milestones и общий план.
* `docs/RUNBOOK.md` и `docs/DECISIONS.md` — reference docs по запуску и архитектурным решениям.
* `docs/QWEN3_MODEL_STACK.md` — зафиксированный стек Qwen3 + OpenVINO readiness/conversion policy.
* `docs/SESSION_2026-02-20.md` — краткий session snapshot по ключевым результатам.

---

## Quickstart (Phase A smoke)

Цель: доказать, что dev loop работает end-to-end **без** скачивания тяжёлых моделей.

1. Создай venv (Python >= 3.11, проверено на 3.12.10):

```powershell
cd D:\atm10-agent
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

2. Установи dependencies (runtime + dev):

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

3. Запусти Phase A smoke:

```powershell
python scripts/phase_a_smoke.py
```

4. Запусти tests:

```powershell
python -m pytest
```

---

## Current status (2026-02-20)

* `python -m pytest` green (`68 passed`).
* Phase A smoke работает и пишет run artifacts.
* Phase B baseline работает end-to-end:
  * нормализация FTB Quests (`.json` + `.snbt`) в `data/ftbquests_norm/quests.jsonl`
  * ingest в Qdrant
  * retrieval с top-k + citations
  * staged retrieval (`candidate-k` + optional `Qwen3-Reranker-0.6B`)
  * eval benchmark (`scripts/eval_retrieval.py`) с метриками Recall@k / MRR@k
* По grid-eval на реальном ATM10 (`runs/20260220_m2_calibration_none/`) зафиксированы defaults:
  `topk=5`, `candidate_k=50`, `reranker=none`.
* Для `chapters/*` усилен ingest и ranking:
  * SNBT extraction поддерживает quoted + unquoted значения (`id/type/dimension/structure/filename/...`)
  * first-stage scoring стал field-weighted (`title/text/tags`) + stopword filtering
  * на eval-наборе `runs/20260220_m2_baseline/eval_cases_atm10_chapters.jsonl`
    достигнуто `Recall@5=1.0000`, `MRR@5=1.0000`, `hit-rate@5=1.0000`
    (artifact: `runs/20260220_132946/`).
* `qwen3` можно запускать через `torch` или `openvino` runtime (`--reranker-runtime`, `--reranker-device`);
  для Windows добавлен wrapper `scripts/run_qwen3_openvino.ps1`.
* `Qwen3-VL-4B-Instruct` успешно конвертирован в OpenVINO IR через custom path
  (`scripts/export_qwen3_custom_openvino.py`, artifact: `runs/20260220_150028-qwen3-custom-export/`).
* `Qwen3-ASR-0.6B` пока остается в блокере текущего export flow (`qwen3_asr` не распознается в `transformers`).
* Для Phase C активный runnable path:
  * `scripts/asr_demo.py` (audio file / microphone -> `transcription.json`)
  * `scripts/voice_runtime_service.py` (long-lived HTTP service)
  * `scripts/voice_runtime_client.py` (fast CLI client)
  * runtime layer: `src/agent_core/io_voice.py`
* `Qwen3-TTS` деактивирован в active stack (остался только как historical reference в артефактах).
* Для снижения шума по умолчанию из индекса исключаются `lang/**` и `reward_tables/**`.
* EOL policy зафиксирована в `.gitattributes` (LF для code/docs, CRLF для Windows scripts).

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

### Phase A — Vision loop (done baseline)

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

**Активный voice path: ASR на Qwen3**

* push-to-talk -> transcribe
* voice не ломает core (Phase A/B работают без voice)
* operational path: `qwen-asr` + `voice_runtime_service/client` для low-latency ASR
* `Qwen3-TTS` path исключен из active roadmap; для озвучки нужен отдельный fast-fallback runtime

Установка voice runtime (дополнительно к `requirements.txt`):

```powershell
python -m pip install "qwen-asr==0.0.6"
```

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
* `src/rag/` — ingestion, normalization, vector store adapters
* `scripts/` — runnable entry points (smoke runs, ingest jobs)
* `tests/` — pytest suite
* `docs/` — RUNBOOK/DECISIONS
* `.codex/` — Codex project config и logs (локально)

---

## Models (baseline + why)

На старте важно иметь **baseline**, который гарантированно работает, а затем — спокойно swap-ать engines без переписывания capture/RAG/logging.

Рекомендация: Phase A делаем engine-agnostic (VLM за interface). Основной целевой стек зафиксирован на `Qwen3` с политикой `OpenVINO-first` (см. `docs/QWEN3_MODEL_STACK.md`).

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
