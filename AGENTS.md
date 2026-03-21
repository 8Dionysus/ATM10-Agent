# AGENTS.md — rules of engagement (Codex / coding agents)

This file is the **single source of truth** for coding agents (including Codex): how to work in the repository, which commands to run, which **boundaries** to respect, and what counts as **Definition of Done (DoD)**.

Principle: **small, reviewable diffs**. Minimum magic, maximum **reproducibility**.

---

## TL;DR

1. Make small changes (target: <= ~200 LOC diff when possible).
2. Before editing: provide a short **plan** + the list of files you will touch.
3. After editing: run **tests** or add at least 1 **smoke test**.
4. Any dependency / tooling changes: **Ask first**.
5. Any important architecture decision: record it in local `docs/DECISIONS.md`.

---

## Repo commands (PowerShell 7)

It is recommended to open PowerShell in the repo root. Use your local clone path as `<repo-root>`.

### Activate venv

```powershell
cd <repo-root>
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

## Working style (how to make changes)

### Before coding (required)

* Restate the task in 3-7 bullets as an **executable plan**.
* Say which files you plan to modify/create.
* List risks separately (Windows paths, permissions, dependencies).

### While coding

* Use `pathlib` instead of manual paths.
* Prefer lightweight dependencies.
* Logs and artifacts go to `runs/<timestamp>/`.

### After coding (required)

* Run `python -m pytest`.
* If there are no tests, add at least 1 test that validates the key result (artifact file/folder, successful exit code, baseline normalization).
* If commands or setup changed, update `docs/RUNBOOK.md`.

---

## Boundaries (Always / Ask first / Never)

### Always

* Always save **artifacts** (screenshots/logs/traces) to `runs/<timestamp>/`.
* Always make changes runnable on Windows 11 + PowerShell 7.
* Always add/update tests when behavior changes.

### Ask first (requires explicit request/confirmation)

* Change `requirements.txt` (except minimal additions like pytest or something strictly necessary for the current task).
* Add new heavy dependencies or "just in case" frameworks.
* Add new services (for example, Neo4j) or change infrastructure (Docker compose, ports, etc.).
* Perform any actions that change game state (automation: keyboard/mouse) beyond safe local smoke checks.
* Download large models/datasets or add files > 10 MB to the repository.

### Never

* Never commit: `models/`, large data dumps, `runs/`, secrets (API keys), tokens, private logs.
* Never disable tests or "work around" them.
* Never run destructive commands (rm -r, formatting disks, changing system settings).

---

## Data & files policy

### Do not commit

* `models/**`
* `data/**` (dumps/wiki/quests — discussed separately)
* `runs/**`
* `.codex/**/logs/**`
* Any binaries and large artifacts
* Any secrets/tokens

### Preferred locations

* Raw input: `data/ftbquests_raw/`
* Normalized docs: `data/ftbquests_norm/` (JSONL)
* Runtime artifacts: `runs/<timestamp>/`
* Temporary files: `runs/<timestamp>/tmp/`
* Local maintainer planning/docs scratch area: `TODO.md`, `PLANS.md`, `docs/internal/**`, local `docs/SESSION_*.md`, and local PR/release coordination docs (ignored in the public repo)

---

## Definition of Done (DoD) by phase

### Phase A — Vision loop (screenshot → VLM stub → output)

Goal: bring the dev loop to life without getting blocked on models.

DoD:

* `scripts/phase_a_smoke.py` exists and runs.
* The script:
  * creates `runs/<timestamp>/`
  * saves screenshot as PNG
  * writes `run.json` (metadata: timestamp, mode, paths)
  * calls VLM through the interface (stub for now) and writes `response.json`
* There is at least 1 pytest that checks `runs/<timestamp>/` and `run.json` are created.
* `python -m pytest` passes.

### Phase B — Memory (RAG)

Goal: retrieval-backed answers over local sources.

DoD:

* There is an ingest script (for example `scripts/ingest_qdrant.py`) with a runnable CLI.
* Data is normalized to JSONL (for example quests/guides).
* Search returns top-k chunks + citations (id/source/path).
* Tests: at least 1 normalization test (fixture) and 1 retrieval test (an in-memory stub is fine).

### Phase C — Voice (ASR/TTS)

Goal: voice input/output as an option that does not block the core.

DoD:

* There are separate entrypoints (`scripts/asr_demo.py`, `scripts/tts_demo.py`).
* Fault tolerance: if there is no audio device, return a graceful error.
* Tests: at least 1 test for “import + CLI help + no crash”.

---

## Coding conventions

* Python >= 3.11 target (tested on 3.12.10).
* No "magic" global path constants; use env vars / config / discovery.
* Logs: `logging` module (`print` is acceptable in demos/smoke).
* Data structures: JSON serializable (for run artifacts and trace).
* LF/CRLF warnings on Windows are expected; fix policy through `.gitattributes` and/or git config, and reflect the decision in public docs (`ROADMAP.md`/`docs/SOURCE_OF_TRUTH.md`/`docs/RUNBOOK.md`) and in local `TODO.md` when relevant.

---

## Commit policy (git hygiene)

* Commits should be small and clear: `phase-a: add smoke runner`, `rag: add ingest stub`.
* If a decision is architectural, add 1-3 bullets to local `docs/DECISIONS.md`.

---

## If the conversation gets long

* Compress context via `/compact`, but preserve:
  * current phase (A/B/C),
  * active files/commands,
  * DoD and boundaries.
