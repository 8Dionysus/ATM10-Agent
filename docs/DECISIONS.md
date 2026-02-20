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
* Для повышения retrieval relevance принят двухэтапный поиск: first-stage candidate retrieval + second-stage rerank; в CLI добавлены `--candidate-k` и `--reranker` (`none|qwen3`) с baseline по умолчанию `none`.
* Специализированный rerank выбран через семейство `Qwen3-Reranker`; стартовая целевая модель для rollout — `Qwen/Qwen3-Reranker-0.6B` (опционально, без обязательного добавления heavy deps в baseline).
* Зафиксирована EOL-политика через `.gitattributes`: source/docs/config по LF, Windows scripts (`*.ps1`, `*.bat`, `*.cmd`) по CRLF для стабильных diff и меньшего шума.
* Для настройки retrieval defaults добавлен reproducible benchmark `scripts/eval_retrieval.py` (Recall@k, MRR@k, hit-rate) с артефактами в `runs/<timestamp>/`; подбор `topk/candidate_k/reranker` теперь делается по метрикам, а не по ручным примерам.
* Интеграция `Qwen3-Reranker` выровнена с официальным scoring-flow (yes/no logits через CausalLM prompt), чтобы избежать некорректного режима `SequenceClassification` и получать валидный rerank score.
* В first-stage tokenization добавлен split по `_` (с сохранением исходного токена), чтобы запросы вида `metallurgic infuser` корректно матчились с `metallurgic_infuser`.
* По grid-eval на реальном ATM10 `chapters/*` (`runs/20260220_m2_calibration_none/`) зафиксированы production defaults:
  `topk=5`, `candidate_k=50`, `reranker=none`; для `topk>=3` метрики совпали, `topk=1` хуже по Recall/hit-rate.
* Для `qwen3` добавлен runtime-переключатель `torch|openvino` и device-параметр (`AUTO|CPU|GPU|NPU`) в retrieval/eval CLI, чтобы ускорять rerank на Intel GPU/NPU через `torch.compile(..., backend="openvino")` без изменения baseline `reranker=none`.
* SNBT signal extraction для Phase B улучшен: в ingestion учитываются не только quoted, но и unquoted значения ключей (`id/type/dimension/structure/filename/...`), что повышает recall по квестам в `chapters/*`.
* Для first-stage retrieval в `chapters/*` принят field-weighted scoring (`title/text/tags`) + stopword filtering: это снижает ложные совпадения по служебным словам (`and/the/...`) и поднимает релевантную главу при запросах по модам (например, `ars nouveau`).
