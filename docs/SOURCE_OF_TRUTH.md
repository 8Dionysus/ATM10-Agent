# SOURCE_OF_TRUTH.md — atm10-agent

Этот файл фиксирует роли документов проекта, чтобы убрать дубли и разнобой.

## Canonical Roles

* `README.md`
  * Короткий human-facing entrypoint.
  * Только high-level статус + ссылки на каноничные документы.
  * Не хранит длинные списки run IDs и исторические метрики.

* `MANIFEST.md`
  * Короткий machine/human snapshot репозитория (актуальная дата, capabilities, ссылки).
  * Без детальной хронологии; детали держим в `docs/SESSION_*.md`.

* `TODO.md`
  * Пошаговый execution-план.
  * Формат: `Now`, `Next`, `Blocked`, `Done this week`.
  * Ограничение: WIP limit = 3.

* `PLANS.md`
  * Цели, milestones, DoD, ограничения и риски.
  * Без длинной хронологии run artifacts.

* `docs/SESSION_YYYY-MM-DD.md`
  * Подробная хронология изменений, запусков, метрик и артефактов.
  * Это место для «длинной истории».
  * Weekly выжимка — по шаблону `docs/SESSION_WEEKLY_TEMPLATE.md`.

* `docs/DECISIONS.md`
  * Архитектурные решения и policy-изменения.
  * Формат: 1–3 bullets на значимое решение.

* `docs/RUNBOOK.md`
  * Runnable команды, операционные профили, quickstart для запуска.

* `docs/ARCHIVED_TRACKS.md`
  * Archived/recoverable направления и условия re-open.

## Update Rules

* Изменили поведение/архитектуру -> обнови `docs/DECISIONS.md`.
* Изменили команды/setup -> обнови `docs/RUNBOOK.md`.
* Есть важный run/result -> добавь в `docs/SESSION_*.md`.
* Активные шаги обновляй только в `TODO.md`.
* Цели/DoD обновляй только в `PLANS.md`.

## What Not To Store Everywhere

* Счетчики вида `N passed` не дублировать во всех файлах одновременно.
  Предпочтение:
  * Истина для текущего состояния — CI + последний `docs/SESSION_*.md`.
* Длинные списки run IDs не держать в `TODO.md`.
