# Spark Swarm Recipe — ATM10-Agent

Рекомендуемый путь назначения: `Spark/SWARM.md`

## Для чего этот рой
Используй Spark здесь для одного узкого seam за раз: `phase_a_smoke`, `gateway_operator`, `kag_guardrail`, `retrieval`, `dry_run_automation` или `voice_wiring`. Этот рой должен усиливать покрытие, smoke/contract paths и reviewability, не расширяя dry-run границы и не ломая Windows 11 + PowerShell 7 совместимость.

## Читать перед стартом
- `AGENTS.md`
- `README.md`
- `MANIFEST.md`
- `docs/RUNBOOK.md`
- `docs/SOURCE_OF_TRUTH.md`

## Форма роя
- **Coordinator**: выбирает ровно один seam, формирует план, распределяет дорожки, сам по умолчанию не пишет код
- **Scout**: картографирует точные файлы, тесты, риски Windows/paths/deps/automation safety; правок не делает
- **Builder**: делает минимальный diff по одному lane
- **Verifier**: запускает реальные команды и проверяет артефакты
- **Boundary Keeper**: следит за dry-run safety, small diff discipline и синхронизацией `docs/RUNBOOK.md` при изменении команд

## Параллельные дорожки
- Lane A: целевой код / script fix
- Lane B: targeted tests / smoke / contract coverage
- Lane C: artifact contract или doc sync
- Не запускай больше одного пишущего агента на одну и ту же семью файлов.

## Allowed
- tighten `pytest` coverage around changed behavior
- добавить 1 smoke или contract test, если поведение поменялось
- чинить artifact path assumptions вокруг `runs/<timestamp>/`, `run.json`, `response.json`
- чинить gateway/operator/nightly wiring без перестройки архитектуры
- усиливать safe loop только в границах smoke-only posture

## Forbidden
- менять `requirements*.txt`, порты, сервисы или инфру без явного запроса
- добавлять тяжёлые зависимости
- выполнять реальные game-state actions за пределами safe local smoke checks
- выключать тесты или обходить их
- нарушать small-diff policy из `AGENTS.md`

## Launch packet для координатора
```text
We are working in ATM10-Agent with a one-repo one-swarm setup.
Pick exactly one seam:
- phase_a_smoke
- gateway_operator
- kag_guardrail
- retrieval
- dry_run_automation
- voice_wiring

First return:
1. a 5-8 bullet executable plan
2. exact files to touch
3. risks
4. which lane each agent owns

Split the swarm:
- Scout: file/test/doc map only, no edits
- Builder: minimal diff
- Verifier: run commands and report actual results
- Boundary Keeper: anti-scope, Windows + PowerShell 7, dry-run safety, RUNBOOK sync

Stop and report instead of improvising if dependencies, ports, services, or real automation actions would need to change.
```

## Промпт для Scout
```text
Map only. Do not edit.
Return:
- exact files most likely involved
- current tests touching the seam
- commands that should be run
- risks: Windows paths, dependencies, automation safety, artifact locations
- whether docs/RUNBOOK.md or MANIFEST.md are likely affected
```

## Промпт для Builder
```text
Make the smallest reviewable change for the chosen seam.
Rules:
- preserve Windows 11 + PowerShell 7 compatibility
- preserve runs/<timestamp>/ artifact discipline
- do not widen from smoke-only to real actions
- if behavior changes, add or update tests
Return:
- files changed
- what behavior changed
- what still remains uncovered
```

## Промпт для Verifier
```text
Run real commands only. Do not claim checks you did not run.
Required default check:
- python -m pytest
If the seam touched Phase A / artifact lifecycle, also run:
- python scripts/phase_a_smoke.py
Report:
- commands run
- pass/fail
- artifact paths created
- any regressions or flaky edges
```

## Промпт для Boundary Keeper
```text
Review boundaries only.
Check:
- no hidden dependency or infra change
- no widening beyond dry-run safe posture
- docs/RUNBOOK.md updated if commands or setup changed
- small, reviewable diff
- no forbidden committed artifacts (`runs/**`, secrets, large binaries)
```

## Verify
```bash
python -m pytest
python scripts/phase_a_smoke.py   # only when the Phase A / artifact path was touched
```

## Done when
- есть план, список файлов и отдельный список рисков
- изменён один seam, а не полрепо
- тесты добавлены/обновлены для изменённого поведения
- команды реально запущены и результаты зафиксированы
- dry-run safety и Windows/PowerShell 7 совместимость сохранены

## Handoff
Если затронуты evaluation-like claims или reusable workflows, следующий ход, скорее всего, пойдёт в `aoa-evals` или `aoa-skills`.
