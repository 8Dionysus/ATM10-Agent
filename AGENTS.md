# AGENTS.md — rules of engagement (Codex / coding agents)

Этот файл — **single source of truth** для coding agents (включая Codex): как работать в репозитории, какие команды запускать, какие **boundaries** соблюдать, и что считается **Definition of Done (DoD)**.

Принцип: **small, reviewable diffs**. Минимум магии, максимум **reproducibility**.

---

## TL;DR

1. Делай изменения маленькими (ориентир: <= ~200 LOC diff, если возможно).
2. Перед правками: короткий **plan** + список файлов, которые тронешь.
3. После правок: запусти **tests** или добавь хотя бы 1 **smoke test**.
4. Любые изменения dependencies / tooling — **Ask first**.
5. Любые важные архитектурные решения — фиксируй в `docs/DECISIONS.md` (когда файл будет готов).

---

## Repo commands (PowerShell 7)

Рекомендуется открывать PowerShell в корне репо. Пример пути: `D:\atm10-agent`.

### Activate venv

```powershell
cd D:\atm10-agent
.\.venv\Scripts\Activate.ps1
```

### Install dependencies

```powershell
python -m pip install -U pip
pip install -r requirements.txt
```

### Run (Phase A smoke)

```powershell
python scripts/phase_a_smoke.py
```

### Run tests

```powershell
python -m pytest
```

---

## Working style (как делать изменения)

### Before coding (обязательно)

* Переформулируй задачу в 3–7 bullets как **executable plan**.
* Скажи, какие файлы планируешь изменить/создать.
* Отдельно перечисли риски (Windows paths, permissions, зависимости).

### While coding

* Используй `pathlib` вместо ручных путей.
* Предпочитай lightweight deps.
* Логи и artifacts — в `runs/<timestamp>/`.

### After coding (обязательно)

* Запусти `python -m pytest`.
* Если тестов нет — добавь минимум 1 test, который проверяет ключевой результат (artifact file/folder, успешный exit code, базовая нормализация).
* Если изменились команды или setup — обнови `docs/RUNBOOK.md` (когда файл будет готов). До этого — оставь заметку в TODO или комментарий в PR/commit message.

---

## Boundaries (Always / Ask first / Never)

### Always

* Всегда сохраняй **artifacts** (screenshots/logs/traces) в `runs/<timestamp>/`.
* Всегда делай изменения так, чтобы они были runnable на Windows 11 + PowerShell 7.
* Всегда добавляй/обновляй tests, если меняешь поведение.

### Ask first (нужен явный запрос/подтверждение)

* Менять `requirements.txt` (кроме минимального добавления pytest/необходимого для текущей задачи).
* Добавлять новые heavy dependencies или фреймворки “про запас”.
* Добавлять новые сервисы (например, Neo4j) или менять инфраструктуру (Docker compose, ports и т.п.).
* Делать любые действия, которые меняют состояние игры (automation: keyboard/mouse), beyond safe локальных smoke-проверок.
* Скачивать большие модели/датасеты или добавлять файлы > 10 MB в репозиторий.

### Never

* Никогда не коммить: `models/`, большие дампы данных, `runs/`, секреты (API keys), токены, приватные логи.
* Никогда не отключай tests или не “обходи” их.
* Никогда не запускай destructive commands (rm -r, форматирование, изменение системных настроек).

---

## Data & files policy

### Do not commit

* `models/**`
* `data/**` (дампы/вики/квесты — обсуждается отдельно)
* `runs/**`
* `.codex/logs/**`
* Любые бинарники и большие артефакты
* Любые секреты/токены

### Preferred locations

* Raw input: `data/ftbquests_raw/`
* Normalized docs: `data/ftbquests_norm/` (JSONL)
* Runtime artifacts: `runs/<timestamp>/`
* Temporary files: `runs/<timestamp>/tmp/`

---

## Definition of Done (DoD) по фазам

### Phase A — Vision loop (screenshot → VLM stub → output)

Goal: оживить dev loop без зависания на моделях.

DoD:

* `scripts/phase_a_smoke.py` существует и запускается.
* Скрипт:

  * создаёт `runs/<timestamp>/`
  * сохраняет screenshot как PNG
  * пишет `run.json` (metadata: timestamp, mode, paths)
  * вызывает VLM через interface (пока stub) и пишет `response.json`
* Есть минимум 1 pytest, который проверяет, что `runs/<timestamp>/` и `run.json` создаются.
* `python -m pytest` проходит.

### Phase B — Memory (RAG)

Goal: retrieval-backed ответы по локальным источникам.

DoD:

* Есть ingest script (например, `scripts/ingest_qdrant.py`) с runnable CLI.
* Нормализация данных в JSONL (например, квесты/гайды).
* Поиск возвращает top-k chunks + citations (id/source/path).
* Tests: минимум 1 test на нормализацию (fixture) и 1 test на retrieval (можно in-memory stub).

### Phase C — Voice (ASR/TTS)

Goal: voice in/out как опция, не блокирующая core.

DoD:

* Есть отдельные entrypoints (`scripts/asr_demo.py`, `scripts/tts_demo.py`).
* Отказоустойчивость: если нет audio device — graceful error.
* Tests: минимум 1 test на “import + CLI help + no crash”.

---

## Coding conventions

* Python 3.11 target.
* Никаких “магических” глобальных констант путей; всё через env vars / config / discovery.
* Логи: `logging` module (print допустим в demos/smoke).
* Структуры данных: JSON serializable (для run artifacts и trace).

---

## Commit policy (git hygiene)

* Коммиты маленькие и понятные: `phase-a: add smoke runner`, `rag: add ingest stub`.
* Если решение архитектурное — 1–3 bullets в `docs/DECISIONS.md` (когда файл будет готов).

---

## If the conversation gets long

* Сжимай контекст через `/compact`, но сохраняй:

  * текущую фазу (A/B/C),
  * активные файлы/команды,
  * DoD и boundaries.
