# Spark lane for ATM10-Agent

This file only governs work started from `Spark/`.

The root `AGENTS.md` remains authoritative for repository identity, ownership boundaries, reading order, and validation commands. This local file only narrows how GPT-5.3-Codex-Spark should behave when used as the fast-loop lane.

If `SWARM.md` exists in this directory, treat it as queue / swarm context. This `AGENTS.md` is the operating policy for Spark work.

## Default Spark posture

- Use Spark for short-loop work where a small diff is enough.
- Start with a map: task, files, risks, and validation path.
- Prefer one bounded patch per loop.
- Read the nearest source docs before editing.
- Use the narrowest relevant validation already documented by the repo.
- Report exactly what was and was not checked.
- Escalate instead of widening into a broad architectural rewrite.

## Spark is strongest here for

- small Python or PowerShell bug fixes
- targeted test or smoke-path updates
- fixture cleanup and public-doc repairs
- operator-panel, retrieval, or dry-run wording cleanup
- tight audits of automation-intent safety posture

## Do not widen Spark here into

- heavy dependency changes
- new services, ports, or infrastructure assumptions
- real input-event behavior changes unless explicitly requested
- major model-stack redesign
- wide multi-module rewrites across gateway, retrieval, automation, and voice at once

## Local done signal

A Spark task is done here when:

- dry-run-by-default posture is preserved
- Windows 11 + PowerShell 7 operability is preserved
- public docs remain sanitized
- minimum validation ran: `python -m pytest`, plus the nearest smoke path for touched runnable entrypoints
- remaining risk is reported honestly

## Local note

Spark is strongest here as a fast repair technician with tests and smokes close at hand.

## Reporting contract

Always report:

- the restated task and touched scope
- which files or surfaces changed
- whether the change was semantic, structural, or clarity-only
- what validation actually ran
- what still needs a slower model or human review
