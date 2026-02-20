# DECISIONS

## 2026-02-19

* Phase A smoke использует `DeterministicStubVLM` через интерфейс `VLMClient`, чтобы держать loop engine-agnostic и не блокироваться на модели.
* Скриншот в smoke-runner сохраняется как валидный placeholder PNG без внешних зависимостей; реальный capture будет подменен позже без изменения artifact contract.
* Для Phase B зафиксирован JSONL doc contract: `id`, `source`, `title`, `text`, `tags`, `created_at`; добавлен tiny fixture dataset для тестов.
* В ingest `ftbquests` текущая итерация поддерживает JSON-файлы; unsupported/parse errors пишутся в `runs/<timestamp>/ingest_errors.jsonl`, чтобы не останавливать весь pipeline.
