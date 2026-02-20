# DECISIONS

## 2026-02-19

* Phase A smoke использует `DeterministicStubVLM` через интерфейс `VLMClient`, чтобы держать loop engine-agnostic и не блокироваться на модели.
* Скриншот в smoke-runner сохраняется как валидный placeholder PNG без внешних зависимостей; реальный capture будет подменен позже без изменения artifact contract.
* Для Phase B зафиксирован JSONL doc contract: `id`, `source`, `title`, `text`, `tags`, `created_at`; добавлен tiny fixture dataset для тестов.
* В ingest `ftbquests` стартовая итерация поддерживала только JSON-файлы; это решение позже superseded SNBT fallback-веткой (см. решения от 2026-02-20).

## 2026-02-20

* Для completion M2 выбран `in-memory retrieval` как first step без Docker/Qdrant: это закрывает `top-k + citations` и оставляет API-границу для последующей интеграции Qdrant.
* `scripts/retrieve_demo.py` пишет artifacts в `runs/<timestamp>/` (`run.json`, `retrieval_results.json`) для воспроизводимости и отладки.
* Qdrant интеграция добавлена как optional backend через REST API (без новых Python dependencies): `scripts/ingest_qdrant.py` + `scripts/retrieve_demo.py --backend qdrant`.
* В нормализации квестов добавлен lightweight fallback для `.snbt`: индексируем файл как документ без полного SNBT-парсера, чтобы обеспечить рабочий retrieval baseline на реальных ATM10 данных.
* Ingest в Qdrant сделан идемпотентным для сценария "collection already exists" (HTTP 409): pipeline продолжает upsert и не падает.
* Для снижения retrieval-noise в baseline ingestion по умолчанию исключает `lang/**` и `reward_tables/**` из индекса; основной фокус индекса — квестовые главы/структуры, а не локализации и reward tables.
* Phase B baseline validated e2e на локальном ATM10 + Qdrant (`normalize -> ingest -> retrieve`) с рабочими top-k + citations.
* Для hardware-accelerated inference baseline добавлен OpenVINO (`openvino==2025.4.1`) и зафиксирован диагностический workflow в `docs/RUNBOOK.md` с artifact-отчетом в `runs/<timestamp>-openvino/`.
